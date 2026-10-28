"""v14 host-only checks for trusted, portable C++ decision logic.

Do not supply arbitrary/untrusted code: g++ and the native executable are NOT
sandboxed. This does not compile .ino firmware, exercise GPIO or prove hardware safety.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / 'cpp_module' / 'controller_contract.h'
RUNNER = ROOT / 'cpp_module' / 'host_runner.cpp'
EXAMPLE = ROOT / 'v14_host_examples' / 'example_adapter.cpp'
DEFAULT_CASES = ROOT / 'v14_host_examples' / 'sample_cases.csv'
COLUMNS = ('case_id', 'module', 'command', 'landed', 'expected')
MAX_CASES = 400


class HostValidationError(RuntimeError):
    """Source, compilation or host execution could not be validated."""


@dataclass(frozen=True)
class Case:
    case_id: str
    module: int
    command: int
    landed: int
    expected: int


@dataclass(frozen=True)
class CaseResult:
    case: Case
    actual: int

    @property
    def passed(self) -> bool:
        return self.actual == self.case.expected


@dataclass(frozen=True)
class SuiteResult:
    source: str
    cases_file: str
    source_sha256: str
    cases_sha256: str
    manifest_sha256: str
    dependencies: tuple[tuple[str, str], ...]
    results: tuple[CaseResult, ...]
    compile_log: str
    elapsed_seconds: float

    @property
    def passed(self) -> int:
        return sum(x.passed for x in self.results)

    @property
    def status(self) -> str:
        return 'PASS' if self.passed == len(self.results) else 'FAIL'


def validate_source(source: str | Path) -> Path:
    candidate = Path(source).expanduser().resolve()
    if not candidate.is_file():
        raise HostValidationError('C++ソースが見つかりません。')
    if candidate.suffix.lower() != '.cpp':
        raise HostValidationError('PC検証用の .cpp アダプターを選択してください。.inoは直接実行できません。')
    if candidate.stat().st_size > 300_000:
        raise HostValidationError('C++ソースは300KB以下にしてください。')
    return candidate


def load_cases(path: str | Path) -> tuple[Case, ...]:
    target = Path(path).expanduser().resolve()
    if not target.is_file() or target.suffix.lower() != '.csv':
        raise HostValidationError('試験条件CSV（.csv）を選択してください。')
    if target.stat().st_size > 150_000:
        raise HostValidationError('試験条件CSVは150KB以下にしてください。')
    try:
        with target.open('r', encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None or set(reader.fieldnames) != set(COLUMNS):
                raise HostValidationError('CSVの列は case_id,module,command,landed,expected にしてください。')
            cases = []
            seen = set()
            for row_num, row in enumerate(reader, start=2):
                if row_num > MAX_CASES + 1:
                    raise HostValidationError(f'試験ケースは{MAX_CASES}件までです。')
                if None in row or any(v is None for v in row.values()):
                    raise HostValidationError(f'CSV {row_num}行目: 列数が違います。')
                label = row['case_id'].strip()
                if not label or len(label) > 80 or label in seen or label[0] in '=+@-\t\r':
                    raise HostValidationError(f'CSV {row_num}行目: case_idの重複または不正な値です。')
                seen.add(label)
                try:
                    mod = int(row['module'].strip())
                    cmd = int(row['command'].strip())
                    landed = int(row['landed'].strip())
                    expected = int(row['expected'].strip())
                except ValueError as exc:
                    raise HostValidationError(f'CSV {row_num}行目: 整数で指定してください。') from exc
                if mod not in (1, 2, 3) or cmd not in (1, 2, 3, 4) or landed not in (0, 1) or expected not in (-1, 0, 1):
                    raise HostValidationError(f'CSV {row_num}行目: module=1..3, command=1..4, landed=0/1, expected=-1/0/1です。')
                cases.append(Case(label, mod, cmd, landed, expected))
    except UnicodeError as exc:
        raise HostValidationError('CSVはUTF-8で保存してください。') from exc
    if not cases:
        raise HostValidationError('試験ケースがありません。')
    return tuple(cases)


def _dependencies(dep_path: Path, source: Path) -> tuple[tuple[str, str], ...]:
    """Collect compiler-reported local includes for reproducibility, not security."""
    raw = dep_path.read_text(encoding='utf-8', errors='replace').replace('\\\n', ' ')
    if ':' not in raw:
        raise HostValidationError('コンパイラの依存ファイル一覧が不正です。')
    names = shlex.split(raw.split(':', 1)[1])
    paths = {source, RUNNER, CONTRACT}
    paths.update(Path(n).resolve() for n in names)
    output = []
    for path in sorted(paths, key=lambda p: str(p)):
        if not path.is_file():
            raise HostValidationError(f'実行中に依存ファイルが消えました: {path.name}')
        output.append((str(path), sha256(path.read_bytes()).hexdigest()))
    return tuple(output)


def run_host_suite(source: str | Path, cases_file: str | Path, *, compile_timeout: float = 25.0,
                   run_timeout: float = 5.0) -> SuiteResult:
    path = validate_source(source)
    cases_path = Path(cases_file).expanduser().resolve()
    cases = load_cases(cases_path)
    compiler = shutil.which('g++')
    if not compiler:
        raise HostValidationError('g++が見つかりません。Ubuntuで sudo apt install g++ を実行してください。')
    if not (CONTRACT.is_file() and RUNNER.is_file()):
        raise HostValidationError('既存のv10 C++共通契約・ランナーがありません。')
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix='cansat_v14_host_') as tmp:
        binary = Path(tmp) / 'host_check'
        dep_file = Path(tmp) / 'deps.d'
        # The chosen CPP may include portable policy headers (including headers
        # shared with the team's .ino) beside the selected source file.
        args = [compiler, '-std=c++17', '-O0', '-Wall', '-Wextra', '-MMD', '-MF', str(dep_file),
                '-I', str(CONTRACT.parent), '-I', str(path.parent),
                str(RUNNER), str(path), '-o', str(binary)]
        try:
            built = subprocess.run(args, capture_output=True, text=True, check=False,
                                   timeout=compile_timeout, cwd=str(path.parent))
        except subprocess.TimeoutExpired as exc:
            raise HostValidationError('C++コンパイルがタイムアウトしました。') from exc
        except OSError as exc:
            raise HostValidationError(f'コンパイラ起動失敗: {exc}') from exc
        log = (built.stdout + built.stderr)[-6000:]
        if built.returncode != 0:
            raise HostValidationError(f'C++コンパイル失敗 (exit={built.returncode}):\n{log}')
        dep_info = _dependencies(dep_file, path)
        stdin = ''.join(f'{c.module} {c.command} {c.landed}\n' for c in cases)
        try:
            output = subprocess.run([str(binary)], input=stdin, text=True, capture_output=True,
                                    check=False, timeout=run_timeout, cwd=str(path.parent))
        except subprocess.TimeoutExpired as exc:
            raise HostValidationError('ホスト用C++の実行がタイムアウトしました。') from exc
        except OSError as exc:
            raise HostValidationError(f'ホスト用C++を実行できません: {exc}') from exc
        if output.returncode:
            raise HostValidationError(f'ホスト用C++が異常終了しました (exit={output.returncode}):\n{output.stderr[-2000:]}')
        lines = output.stdout.splitlines()
        if len(lines) != len(cases) or any(line.strip() not in ('-1', '0', '1') for line in lines):
            raise HostValidationError('不正なC++出力。各ケースについて1行ずつ -1 / 0 / 1 のみ返してください。')
    tests_hash = sha256(cases_path.read_bytes()).hexdigest()
    src_hash = sha256(path.read_bytes()).hexdigest()
    manifest = json.dumps({'deps': dep_info, 'cases': tests_hash}, ensure_ascii=False,
                          separators=(',', ':'), sort_keys=True).encode('utf-8')
    return SuiteResult(str(path), str(cases_path), src_hash, tests_hash,
                       sha256(manifest).hexdigest(), dep_info,
                       tuple(CaseResult(case, int(answer.strip())) for case, answer in zip(cases, lines)),
                       log, round(time.monotonic() - started, 3))


def as_dict(run: SuiteResult) -> dict:
    return {
        'tool': 'CanSat Module Test Lab v14 / host C++',
        'scope': 'host decision logic only; not Arduino firmware, ESP32 or hardware verification',
        'status': run.status, 'passed': run.passed, 'total': len(run.results),
        'source': run.source, 'cases_file': run.cases_file,
        'source_sha256': run.source_sha256, 'cases_sha256': run.cases_sha256,
        'manifest_sha256': run.manifest_sha256,
        'dependencies': [{'path': path, 'sha256': digest} for path, digest in run.dependencies],
        'elapsed_seconds': run.elapsed_seconds, 'compile_log': run.compile_log,
        'cases': [dict(case_id=r.case.case_id, module=r.case.module, command=r.case.command,
                       landed=r.case.landed, expected=r.case.expected, actual=r.actual,
                       result='PASS' if r.passed else 'FAIL') for r in run.results],
    }


def export_report(run: SuiteResult, filename: str | Path) -> Path:
    """Save only after explicit GUI user action; never upload or mutate test data."""
    target = Path(filename).expanduser()
    if target.suffix.lower() not in ('.csv', '.json'):
        raise HostValidationError('レポートは.csv または.jsonにしてください。')
    if target.suffix.lower() == '.json':
        payload = json.dumps(as_dict(run), ensure_ascii=False, indent=2) + '\n'
    else:
        stream = io.StringIO(newline='')
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(('case_id', 'module', 'command', 'landed', 'expected', 'actual', 'result',
                         'source_sha256', 'cases_sha256', 'manifest_sha256'))
        for result in run.results:
            c = result.case
            writer.writerow((c.case_id, c.module, c.command, c.landed, c.expected, result.actual,
                             'PASS' if result.passed else 'FAIL', run.source_sha256,
                             run.cases_sha256, run.manifest_sha256))
        payload = stream.getvalue()
    target.write_text(payload, encoding='utf-8-sig' if target.suffix.lower() == '.csv' else 'utf-8')
    return target
