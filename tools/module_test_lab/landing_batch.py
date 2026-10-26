"""Deterministic, offline, opt-in batch scenarios for trusted host C++ landing logic.

No hardware, ROS2, network, or existing record mutations. The caller explicitly
selects a trusted C++ source for the existing cpp_landing_runner.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import io
import math
from pathlib import Path
import random
import tempfile

from cpp_landing_runner import CppResult, run_landing_cpp, read_sensor_csv


@dataclass(frozen=True)
class BatchCase:
    key: str
    title: str
    description: str


CASES = (
    BatchCase('normal', '正常着地', '10秒の着地で強い加速度ピーク'),
    BatchCase('noise', 'センサーノイズ', 'ランダムなIMU測定ノイズを追加（固定シード）'),
    BatchCase('early_shock', '着地前の衝撃', '5秒に非着地衝撃、10秒に実際の着地'),
    BatchCase('gentle', '弱い着地', '10秒の衝撃が小さく、検知しづらい条件'),
    BatchCase('delayed_impact', '衝撃の遅れ', '10秒に接地、強いIMUピークは13秒'),
    BatchCase('dropout', '着地時の欠損', '10秒のIMUサンプルを欠損させた条件'),
    BatchCase('no_truth', '正解時刻なし', 'IMUデータはあるが接地の正解ラベルがない'),
    BatchCase('invalid_imu', '不正な入力値', 'IMUデータに空欄があるCSV（入力エラー確認）'),
)
CASES_BY_KEY = {case.key: case for case in CASES}
MAX_CASES = 12


@dataclass(frozen=True)
class BatchOutcome:
    case: BatchCase
    input_csv: str
    result: CppResult | None
    status: str
    reason: str

    @property
    def summary(self) -> dict:
        return self.result.summary if self.result is not None else {}


@dataclass(frozen=True)
class BatchRun:
    source: str
    tolerance_s: float
    outcomes: tuple[BatchOutcome, ...]

    @property
    def counts(self) -> dict:
        labels = ('成功', '失敗', '未判定', '入力エラー', '実行エラー')
        return {label: sum(item.status == label for item in self.outcomes) for label in labels}


def make_case_csv(case_key: str, *, seed: int = 20261026) -> str:
    """Return synthetic CSV with sampled truth, not a claim of actual sensor accuracy."""
    if case_key not in CASES_BY_KEY:
        raise ValueError(f'未知の試験ケース: {case_key}')
    rng = random.Random(seed)
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, lineterminator='\n')
    header = ['time_ms', 'imu_z_mps2', 'pressure_pa']
    if case_key != 'no_truth':
        header.append('truth_contact')
    writer.writerow(header)
    for i in range(161):
        # 0--16s, 100ms/sample. Contact is 10s except no_truth.
        if case_key == 'dropout' and i == 100:
            continue  # A plausible missing sample, not an invalid CSV value.
        acceleration = 9.81 + rng.uniform(-0.13, 0.13)
        if case_key == 'noise':
            acceleration += rng.uniform(-2.5, 2.5)
        if i == 100 and case_key in ('normal', 'noise', 'no_truth', 'invalid_imu'):
            acceleration = 38.6
        elif i == 50 and case_key == 'early_shock':
            acceleration = 38.6
        elif i == 100 and case_key == 'early_shock':
            acceleration = 38.6
        elif i == 100 and case_key == 'gentle':
            acceleration = 15.0
        elif i == 130 and case_key == 'delayed_impact':
            acceleration = 38.6
        # In no_truth there is deliberately no contact-time reference.
        # Small drift in pressure; plateaus after the contact for visualization.
        pressure = 100991.6 + min(i, 100) / 100.0 * 137.0
        a_cell = '' if case_key == 'invalid_imu' and i == 60 else f'{acceleration:.5f}'
        row = [str(i * 100), a_cell, f'{pressure:.3f}']
        if case_key != 'no_truth':
            row.append('1' if i >= 100 else '0')
        writer.writerow(row)
    return buffer.getvalue()


def run_batch(source_path: str | Path, *, allowed_delay_s: float = 5.0,
              case_keys: tuple[str, ...] | None = None) -> BatchRun:
    """Run the existing host C++ evaluator per condition; never invoke network.

    The C++ is built and executed by the existing tool and MUST be trusted local
    source. Each scenario is isolated by the existing C++ runner's reset semantics.
    """
    if not math.isfinite(allowed_delay_s) or not 0 <= allowed_delay_s <= 600:
        raise ValueError('許容遅延は0～600秒の有限数にしてください。')
    keys = tuple(case_keys) if case_keys is not None else tuple(c.key for c in CASES)
    if not keys or len(keys) > MAX_CASES or len(set(keys)) != len(keys):
        raise ValueError('試験ケースは重複なしで1～12件までにしてください。')
    if any(key not in CASES_BY_KEY for key in keys):
        raise ValueError('未定義の試験ケースが含まれます。')
    source = Path(source_path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != '.cpp':
        raise ValueError('信頼できるローカルの.cppコードを選択してください。')
    outcomes = []
    with tempfile.TemporaryDirectory(prefix='cansat-landing-batch-') as temp:
        for case_key in keys:
            scenario = CASES_BY_KEY[case_key]
            contents = make_case_csv(case_key)
            input_path = Path(temp) / f'{case_key}.csv'
            input_path.write_text(contents, encoding='utf-8')
            if case_key == 'invalid_imu':
                # An invalid input is an expected parser error, not an algorithm failure.
                try:
                    read_sensor_csv(input_path)
                except ValueError as exc:
                    outcomes.append(BatchOutcome(scenario, contents, None,
                                                 '入力エラー', str(exc)))
                else:
                    outcomes.append(BatchOutcome(scenario, contents, None,
                                                 '実行エラー', '不正なCSVが検証を通過しました。'))
                continue
            try:
                result = run_landing_cpp(input_path, source,
                                         allowed_delay_s=allowed_delay_s)
            except (ValueError, OSError) as exc:
                outcomes.append(BatchOutcome(scenario, contents, None,
                                             '実行エラー', str(exc)))
                # Compilation failure usually affects every case; stop early instead of repeated calls.
                if 'コンパイル' in str(exc):
                    break
            else:
                outcomes.append(BatchOutcome(scenario, contents, result,
                                             result.summary['status'],
                                             result.summary['reason']))
    return BatchRun(str(source), allowed_delay_s, tuple(outcomes))


def make_summary_csv(run: BatchRun) -> str:
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(['scenario_key', 'scenario_name', 'status', 'true_contact_s',
                     'detected_time_s', 'delay_s', 'allowed_delay_s', 'reason'])
    for item in run.outcomes:
        summary = item.summary
        writer.writerow([item.case.key, item.case.title, item.status,
                         summary.get('true_contact_s'), summary.get('detected_time_s'),
                         summary.get('delay_s'), run.tolerance_s, item.reason])
    return buffer.getvalue()
