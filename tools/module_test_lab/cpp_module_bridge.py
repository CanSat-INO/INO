"""Compile trusted PC C++ control logic and evaluate four virtual module decisions.

Not Arduino firmware execution, hardware-in-the-loop, or real CAN traffic.
The compilation and binary execution are NOT sandboxed: use trusted C++ only.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import tempfile

BASE = Path(__file__).resolve().parent
CPP_DIR = BASE / 'cpp_module'
INPUTS = (
    ('main_landing', 1, 1, 1),
    ('drive_move', 3, 2, 1),
    ('cam_capture', 2, 3, 1),
    ('drive_stop', 3, 4, 1),
)


class CppModuleError(RuntimeError):
    """A compile error, process error, invalid output, or timeout."""


@dataclass(frozen=True)
class BridgeResult:
    source: str
    decisions: dict[str, bool]
    compiler_output: str


def run_cpp_decisions(source: str | Path, *, compile_timeout: float = 20,
                      run_timeout: float = 3) -> BridgeResult:
    path = Path(source).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != '.cpp':
        raise CppModuleError('既存の .cpp ファイルを選択してください。')
    if path.stat().st_size > 300_000:
        raise CppModuleError('C++コードが大きすぎます（上限300KB）。')
    compiler = shutil.which('g++')
    if compiler is None:
        raise CppModuleError('g++が見つかりません。PC用C++コンパイラが必要です。')
    with tempfile.TemporaryDirectory(prefix='cansat_v8_cpp_') as directory:
        executable = Path(directory) / 'cpp_module_runner'
        cmd = [compiler, '-std=c++17', '-O0', '-Wall', '-Wextra',
               '-I', str(CPP_DIR), str(CPP_DIR / 'host_runner.cpp'),
               str(path), '-o', str(executable)]
        try:
            comp = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=compile_timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise CppModuleError('C++コンパイルが時間切れになりました。') from exc
        except OSError as exc:
            raise CppModuleError(f'コンパイラを起動できません: {exc}') from exc
        compiler_output = (comp.stdout + comp.stderr)[-3500:]
        if comp.returncode:
            raise CppModuleError('C++コンパイル失敗:\n' + compiler_output)
        request = ''.join(f'{module} {command} {landed}\n'
                          for _, module, command, landed in INPUTS)
        try:
            result = subprocess.run([str(executable)], input=request,
                                    capture_output=True, text=True, timeout=run_timeout,
                                    check=False)
        except subprocess.TimeoutExpired as exc:
            raise CppModuleError('C++コードの実行が時間切れになりました。') from exc
        except OSError as exc:
            raise CppModuleError(f'C++コードを実行できません: {exc}') from exc
        if result.returncode:
            raise CppModuleError(f'C++コードが異常終了しました (exit={result.returncode}):\n'
                                 + result.stderr[-1000:])
        lines = result.stdout.splitlines()
        if len(lines) != len(INPUTS) or any(line.strip() not in ('0', '1') for line in lines):
            raise CppModuleError('C++応答形式が不正です。4行の0/1のみ返してください。'
                                 '\n標準出力にデバッグ文字列を出さないでください。')
        return BridgeResult(str(path),
                            {item[0]: line.strip() == '1'
                             for item, line in zip(INPUTS, lines)},
                            compiler_output)
