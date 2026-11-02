"""v14.1: host-only portable C++ module-decision test runner.

CAUTION: compiles and runs user-selected native code without sandboxing. Select
only personally reviewed/trusted C++ adapters. No .ino flashing or GPIO.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
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
EXAMPLES = ROOT / 'v14_1_examples'
CONTRACT = ROOT / 'v14_1_contract.hpp'
NATIVE_RUNNER = ROOT / 'v14_1_host_runner.cpp'
MAX_CASES = 500


class ModuleValidationError(ValueError):
    """A source, CSV or execution is unsuitable for this host-only check."""


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str  # 'int' or 'float'
    minimum: Decimal
    maximum: Decimal


@dataclass(frozen=True)
class ModuleSpec:
    key: str
    title: str
    description: str
    fields: tuple[Field, ...]
    allowed_outputs: tuple[int, ...]
    output_meanings: str


def I(name: str, label: str, minimum: int, maximum: int) -> Field:
    return Field(name, label, 'int', Decimal(minimum), Decimal(maximum))


def F(name: str, label: str, minimum: str, maximum: str) -> Field:
    return Field(name, label, 'float', Decimal(minimum), Decimal(maximum))


SPECS = {
    'landing': ModuleSpec(
        'landing', '着地判定', '加速度・角速度・安定継続時間で着地の判断だけを試験',
        (F('accel_mps2', '加速度 m/s²', '0', '200'), F('gyro_dps', '角速度 °/s', '0', '2000'),
         I('stable_ms', '安定継続 ms', 0, 60000)), (0, 1), '0=未着地 / 1=着地'),
    'drive': ModuleSpec(
        'drive', 'Drive制御', '着地・走行指令・障害物・緊急停止から走行判断を試験',
        (I('landed', '着地', 0, 1), I('command', '指令', 0, 3),
         I('obstacle', '障害物', 0, 1), I('emergency_stop', '停止要求', 0, 1)),
        (0, 1, 2, 3), '0=停止 / 1=前進 / 2=左旋回 / 3=右旋回'),
    'cam': ModuleSpec(
        'cam', 'CAM判断', '対象の検出・画像内の赤占有率・水平方向のズレに対する判断を試験（画像処理自体は対象外）',
        (I('visible', '認識成功', 0, 1), F('red_ratio', '赤占有率', '0', '1'),
         F('x_offset', '左右位置[-1,1]', '-1', '1')),
        (0, 1, 2, 3, 4), '0=探索 / 1=左 / 2=右 / 3=接近 / 4=到達'),
    'main': ModuleSpec(
        'main', 'Main状態遷移', '着地・GNSS測位・カメラ検出・異常状態からフェーズを判断',
        (I('landed', '着地', 0, 1), I('gnss_fix', 'GNSS測位', 0, 1),
         I('target_visible', '対象検出', 0, 1), I('fault', '異常', 0, 1)),
        (0, 1, 2, 3, 4), '0=着地待ち / 1=GNSS待ち / 2=GPS誘導 / 3=CAM誘導 / 4=安全停止'),
}


@dataclass(frozen=True)
class TestCase:
    case_id: str
    arguments: tuple[str, ...]
    expected: int


@dataclass(frozen=True)
class TestResult:
    case: TestCase
    actual: int

    @property
    def passed(self):
        return self.actual == self.case.expected


@dataclass(frozen=True)
class ModuleReport:
    module: str
    source: str
    cases_csv: str
    source_sha256: str
    csv_sha256: str
    manifest_sha256: str
    dependencies: tuple[tuple[str, str], ...]
    results: tuple[TestResult, ...]
    compile_log: str
    elapsed_seconds: float

    @property
    def passed(self):
        return sum(item.passed for item in self.results)

    @property
    def status(self):
        return 'PASS' if self.passed == len(self.results) else 'FAIL'


def examples_for(module: str):
    if module not in SPECS:
        raise ModuleValidationError('未知のモジュールです。')
    return EXAMPLES / f'{module}_adapter.cpp', EXAMPLES / f'{module}_cases.csv'


def validate_adapter(path: str | Path) -> Path:
    file = Path(path).expanduser().resolve()
    if not file.is_file() or file.suffix.lower() != '.cpp':
        raise ModuleValidationError('信頼できるPC試験用の.cppアダプターを指定してください（.inoは不可）。')
    if file.stat().st_size > 300_000:
        raise ModuleValidationError('アダプターは300KB以内にしてください。')
    return file


def load_module_cases(module: str, path: str | Path) -> tuple[TestCase, ...]:
    spec = SPECS.get(module)
    if spec is None:
        raise ModuleValidationError('未知のモジュールです。')
    target = Path(path).expanduser().resolve()
    if not target.is_file() or target.suffix.lower() != '.csv':
        raise ModuleValidationError('UTF-8のCSVファイルを指定してください。')
    if target.stat().st_size > 175_000:
        raise ModuleValidationError('CSVは175KB以内にしてください。')
    expected_fields = ('case_id', *(f.name for f in spec.fields), 'expected')
    cases = []
    seen = set()
    try:
        with target.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(expected_fields):
                raise ModuleValidationError('CSVの列を次の順にしてください: ' + ','.join(expected_fields))
            for row_number, record in enumerate(reader, start=2):
                if len(cases) >= MAX_CASES:
                    raise ModuleValidationError(f'CSV試験は最大{MAX_CASES}件です。')
                if None in record or any(v is None for v in record.values()):
                    raise ModuleValidationError(f'{row_number}行目: 列数が不一致です。')
                case_id = record['case_id'].strip()
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', case_id) or case_id in seen:
                    raise ModuleValidationError(f'{row_number}行目: case_idが不正または重複しています。')
                seen.add(case_id)
                args = []
                for f in spec.fields:
                    raw = record[f.name].strip()
                    try:
                        number = Decimal(raw)
                    except InvalidOperation as exc:
                        raise ModuleValidationError(f'{row_number}行目: {f.name}は数値にしてください。') from exc
                    if not number.is_finite() or number < f.minimum or number > f.maximum:
                        raise ModuleValidationError(f'{row_number}行目: {f.name}が許容範囲外です。')
                    if f.kind == 'int' and number != number.to_integral_value():
                        raise ModuleValidationError(f'{row_number}行目: {f.name}は整数にしてください。')
                    args.append(str(int(number)) if f.kind == 'int' else str(number))
                try:
                    outcome = int(record['expected'].strip())
                except ValueError as exc:
                    raise ModuleValidationError(f'{row_number}行目: expectedは整数です。') from exc
                if outcome not in spec.allowed_outputs:
                    raise ModuleValidationError(f'{row_number}行目: 期待値は{spec.allowed_outputs}のいずれかです。')
                cases.append(TestCase(case_id, tuple(args), outcome))
    except UnicodeError as exc:
        raise ModuleValidationError('CSVはUTF-8で保存してください。') from exc
    if not cases:
        raise ModuleValidationError('CSVに試験ケースがありません。')
    return tuple(cases)


def _dependencies(depfiles: list[Path], required: tuple[Path, ...]):
    files = set(required)
    for dep in depfiles:
        raw = dep.read_text(encoding='utf-8', errors='replace').replace('\\\n', ' ')
        if ':' not in raw:
            raise ModuleValidationError('g++の依存ファイル情報を読み取れません。')
        for name in shlex.split(raw.split(':', 1)[1]):
            files.add(Path(name).resolve())
    result = []
    for path in sorted(files, key=lambda x: str(x)):
        if not path.is_file():
            raise ModuleValidationError('依存ファイルが実行途中で消えました。')
        result.append((str(path), sha256(path.read_bytes()).hexdigest()))
    return tuple(result)


def run_module_suite(module: str, adapter: str | Path, cases_csv: str | Path,
                     *, compile_timeout=25.0, run_timeout=5.0) -> ModuleReport:
    if module not in SPECS:
        raise ModuleValidationError('未知のモジュールです。')
    source = validate_adapter(adapter)
    tests_path = Path(cases_csv).expanduser().resolve()
    cases = load_module_cases(module, tests_path)
    compiler = shutil.which('g++')
    if not compiler:
        raise ModuleValidationError('g++がありません。Ubuntuで sudo apt install g++ を実行してください。')
    if not CONTRACT.is_file() or not NATIVE_RUNNER.is_file():
        raise ModuleValidationError('v14.1のC++契約ファイルがありません。')
    started = time.monotonic()
    compiler_log = []
    with tempfile.TemporaryDirectory(prefix='cansat_v14_1_') as folder:
        temporary = Path(folder)
        objs = []
        deps = []
        for n, input_file in enumerate((NATIVE_RUNNER, source)):
            obj = temporary / f'src{n}.o'
            dep = temporary / f'src{n}.d'
            command = [compiler, '-std=c++17', '-O0', '-Wall', '-Wextra',
                       '-D' + f'CANSAT_TARGET_{module.upper()}',
                       '-I', str(ROOT), '-I', str(source.parent),
                       '-MMD', '-MF', str(dep), '-c', str(input_file), '-o', str(obj)]
            try:
                finished = subprocess.run(command, capture_output=True, text=True,
                                          timeout=compile_timeout, cwd=source.parent, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ModuleValidationError('ホストC++コンパイルを開始または完了できませんでした。') from exc
            compiler_log.append((finished.stdout + finished.stderr)[-3000:])
            if finished.returncode != 0:
                raise ModuleValidationError('コンパイル失敗:\n' + compiler_log[-1])
            objs.append(obj)
            deps.append(dep)
        binary = temporary / 'module_check'
        try:
            linked = subprocess.run([compiler, *(str(obj) for obj in objs), '-o', str(binary)],
                                    timeout=compile_timeout, capture_output=True, text=True, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ModuleValidationError('C++リンク処理に失敗しました。') from exc
        compiler_log.append((linked.stdout + linked.stderr)[-3000:])
        if linked.returncode != 0:
            raise ModuleValidationError('リンク失敗: 選択したモジュールのcansat_*関数が定義されていますか？\n' + compiler_log[-1])
        includes = _dependencies(deps, (source, NATIVE_RUNNER, CONTRACT))
        stream = '\n'.join(' '.join((*case.arguments, *('0',) * (4-len(case.arguments)))) for case in cases) + '\n'
        try:
            executed = subprocess.run([str(binary)], input=stream, text=True, capture_output=True,
                                      timeout=run_timeout, cwd=source.parent, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ModuleValidationError('C++試験が異常終了またはタイムアウトしました。') from exc
        if executed.returncode != 0:
            raise ModuleValidationError(f'C++実行失敗 exit={executed.returncode}:\n{executed.stderr[-2000:]}')
        outputs = executed.stdout.splitlines()
        if len(outputs) != len(cases):
            raise ModuleValidationError('C++出力行数がCSVの件数と一致しません。printfデバッグ出力は削除してください。')
        actual = []
        for index, line in enumerate(outputs):
            if not re.fullmatch(r'-?\d+', line.strip()):
                raise ModuleValidationError(f'{index+1}件目のC++出力が整数ではありません。')
            answer = int(line.strip())
            if answer not in SPECS[module].allowed_outputs:
                raise ModuleValidationError(f'{index+1}件目: C++出力{answer}は定義範囲外です。')
            actual.append(answer)
    src_hash = sha256(source.read_bytes()).hexdigest()
    csv_hash = sha256(tests_path.read_bytes()).hexdigest()
    payload = json.dumps({'module': module, 'csv_sha256': csv_hash, 'includes': includes},
                         ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return ModuleReport(module, str(source), str(tests_path), src_hash, csv_hash,
                        sha256(payload).hexdigest(), includes,
                        tuple(TestResult(case, result) for case, result in zip(cases, actual)),
                        '\n'.join(x for x in compiler_log if x)[-6000:],
                        round(time.monotonic()-started, 3))


def report_dict(report: ModuleReport) -> dict:
    return {
        'tool': 'CanSat Module Test Lab v14.1 / portable C++ modules',
        'scope': 'host logic test only, not real .ino/ESP32-S3/GPIO/GNSS/camera/actuator validation',
        'module': report.module,
        'status': report.status, 'passed': report.passed, 'total': len(report.results),
        'source': report.source, 'cases_csv': report.cases_csv,
        'source_sha256': report.source_sha256, 'csv_sha256': report.csv_sha256,
        'manifest_sha256': report.manifest_sha256,
        'dependencies': [{'path': path, 'sha256': digest} for path, digest in report.dependencies],
        'compile_log': report.compile_log, 'elapsed_seconds': report.elapsed_seconds,
        'results': [dict(case_id=r.case.case_id, **{f.name: val for f, val in zip(SPECS[report.module].fields, r.case.arguments)},
                         expected=r.case.expected, actual=r.actual, result='PASS' if r.passed else 'FAIL')
                    for r in report.results],
    }


def export_module_report(report: ModuleReport, filepath: str | Path) -> Path:
    path = Path(filepath).expanduser()
    data = report_dict(report)
    if path.suffix.lower() == '.json':
        content = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
        path.write_text(content, encoding='utf-8')
    elif path.suffix.lower() == '.csv':
        buffer = io.StringIO(newline='')
        fields = ('case_id', *(f.name for f in SPECS[report.module].fields), 'expected', 'actual', 'result',
                  'manifest_sha256')
        writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        for item in data['results']:
            writer.writerow({**item, 'manifest_sha256': report.manifest_sha256})
        path.write_text(buffer.getvalue(), encoding='utf-8-sig')
    else:
        raise ModuleValidationError('結果は.csvまたは.jsonに保存してください。')
    return path
