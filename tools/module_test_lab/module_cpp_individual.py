"""v10: compile and run three independent, *trusted* host C++ modules.

This is not ESP32/Arduino firmware, hardware-in-loop, or physical CAN validation.
C++ execution is not sandboxed. Use ONLY source files you trust.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import shutil
import subprocess
import tempfile

from module_network import Result, simulate

BASE = Path(__file__).resolve().parent
CONTRACT = BASE / 'cpp_module' / 'controller_contract.h'
RUNNER = BASE / 'cpp_module' / 'host_runner.cpp'
ROLES = ('Main', 'CAM', 'Drive')
# key, module-id, command-id, landed, expected when required for safety check
CASES = {
    'Main': (
        ('main_landing', 1, 1, 1, None),
        ('main_before_landing', 1, 1, 0, 0),
        ('main_unknown_stop', 1, 4, 1, -1),
    ),
    'CAM': (
        ('cam_capture', 2, 3, 1, None),
        ('cam_unknown_move', 2, 2, 1, -1),
    ),
    'Drive': (
        ('drive_move', 3, 2, 1, None),
        ('drive_stop', 3, 4, 1, None),
        ('drive_unknown_capture', 3, 3, 1, -1),
    ),
}


class IndividualCppError(RuntimeError):
    pass


@dataclass(frozen=True)
class Decision:
    key: str
    module: int
    command: int
    landed: int
    value: int  # -1=unsupported, 0=deny, 1=accept
    expected: int | None

    @property
    def safety_check(self) -> str:
        if self.expected is None:
            return '判断結果'
        return '適合' if self.value == self.expected else '要確認'


@dataclass(frozen=True)
class ModuleRun:
    role: str
    source: str
    sha256: str
    decisions: tuple[Decision, ...]
    compile_log: str


@dataclass(frozen=True)
class BundleRun:
    modules: tuple[ModuleRun, ...]
    cpp_policy: dict[str, bool]
    simulation: Result
    provenance_sha256: str

    @property
    def source_notes(self) -> str:
        return '\n'.join(f'{r.role}: {Path(r.source).name} SHA256={r.sha256}' for r in self.modules)


def _validate_source(source: str | Path) -> Path:
    path = Path(source).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() != '.cpp':
        raise IndividualCppError('存在するPC向け .cpp ファイルを指定してください。')
    if path.stat().st_size > 300_000:
        raise IndividualCppError('ソースは300KB以下にしてください。')
    return path


def run_module(role: str, source: str | Path, *, compile_timeout: float = 20.0,
               run_timeout: float = 3.0) -> ModuleRun:
    if role not in CASES:
        raise ValueError(f'不明なモジュール: {role}')
    path = _validate_source(source)
    compiler = shutil.which('g++')
    if not compiler:
        raise IndividualCppError('g++ がありません。PC用C++コンパイラを用意してください。')
    if not RUNNER.is_file() or not CONTRACT.is_file():
        raise IndividualCppError('v8.2のC++共通契約ファイルがありません。')
    with tempfile.TemporaryDirectory(prefix='cansat_v10_cpp_') as directory:
        binary = Path(directory) / 'module_test'
        cmd = [compiler, '-std=c++17', '-O0', '-Wall', '-Wextra',
               '-I', str(CONTRACT.parent), '-I', str(path.parent),
               str(RUNNER), str(path), '-o', str(binary)]
        try:
            compiled = subprocess.run(cmd, capture_output=True, text=True,
                                      check=False, timeout=compile_timeout)
        except subprocess.TimeoutExpired as exc:
            raise IndividualCppError(f'{role}: コンパイルが時間切れです。') from exc
        except OSError as exc:
            raise IndividualCppError(f'{role}: コンパイラを起動できません: {exc}') from exc
        log = (compiled.stdout + compiled.stderr)[-4000:]
        if compiled.returncode:
            raise IndividualCppError(f'{role}: コンパイル失敗:\n{log}')
        lines = CASES[role]
        stdin = ''.join(f'{module} {command} {landed}\n'
                        for _, module, command, landed, _ in lines)
        try:
            proc = subprocess.run([str(binary)], input=stdin,
                                  capture_output=True, text=True, check=False,
                                  timeout=run_timeout)
        except subprocess.TimeoutExpired as exc:
            raise IndividualCppError(f'{role}: 実行が時間切れです。') from exc
        except OSError as exc:
            raise IndividualCppError(f'{role}: 実行できません: {exc}') from exc
        if proc.returncode:
            raise IndividualCppError(f'{role}: C++異常終了 (exit={proc.returncode}):\n{proc.stderr[-1500:]}')
        outputs = proc.stdout.splitlines()
        if len(outputs) != len(lines) or any(x.strip() not in ('-1','0','1') for x in outputs):
            raise IndividualCppError(f'{role}: 不正な出力です。標準出力には各要求への-1/0/1だけを返してください。')
        answers = tuple(Decision(label, module, cmd, landed, int(value.strip()), expected)
                        for (label,module,cmd,landed,expected),value in zip(lines,outputs))
    return ModuleRun(role, str(path), hashlib.sha256(path.read_bytes()).hexdigest(), answers, log)


def combine_modules(modules: tuple[ModuleRun, ...], scenario_key: str = 'normal') -> BundleRun:
    if len(modules) != 3 or tuple(r.role for r in modules) != ROLES:
        raise ValueError('Main、CAM、Driveの順に3モジュールの結果が必要です。')
    outputs = {case.key: case.value for run in modules for case in run.decisions}
    needed = ('main_landing', 'cam_capture', 'drive_move', 'drive_stop')
    if any(outputs.get(key) not in (0,1) for key in needed):
        raise IndividualCppError('既知のC++判断は0（拒否）か1（許可）を返してください。')
    policy = {key: outputs[key] == 1 for key in needed}
    simulation = simulate(scenario_key, cpp_policy=policy)
    hashes = '\n'.join(f'{m.role}:{m.sha256}' for m in modules)
    provenance = hashlib.sha256(hashes.encode('ascii')).hexdigest()
    return BundleRun(modules, policy, simulation, provenance)


def run_three_modules(sources: dict[str, str | Path], scenario_key: str = 'normal') -> BundleRun:
    if set(sources) != set(ROLES):
        raise ValueError('Main・CAM・Driveの3ファイルを指定してください。')
    return combine_modules(tuple(run_module(role, sources[role]) for role in ROLES), scenario_key)
