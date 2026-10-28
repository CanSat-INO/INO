"""Offline paired CSV comparison. A comparison is NOT real-hardware validation.

CSV imports use v15's conservative file/encoding/numeric rules. Time is always
elapsed seconds and measurements are interpolated only inside reference support.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Optional
from v15_sensor_core import SensorLog, read_sensor_csv

MAX_RESULTS = 50_000

@dataclass(frozen=True)
class MatchPoint:
    time_s: float
    measured: float
    reference: float
    error: float

@dataclass(frozen=True)
class CompareResult:
    measured_file: str
    reference_file: str
    measured_sha256: str
    reference_sha256: str
    measured_signal: str
    reference_signal: str
    unit: str
    time_shift_s: float
    measured_valid: int
    matched: int
    coverage_fraction: float
    mae: float
    rmse: float
    bias: float
    max_abs_error: float
    points: tuple[MatchPoint, ...]


def read_log(path: str | Path) -> SensorLog:
    log = read_sensor_csv(path)
    if log.time_kind == 'sample':
        raise ValueError('比較するCSVには秒またはミリ秒の時間列（time_s / time_ms）が必要です。')
    if len(log.times) < 2:
        raise ValueError('CSVには2行以上の時刻付きデータが必要です。')
    for a, b in zip(log.times, log.times[1:]):
        if b <= a:
            raise ValueError('時刻は重複せず、厳密な昇順にしてください。')
    return log


def common_signals(measured: SensorLog, reference: SensorLog) -> list[str]:
    return sorted(set(measured.signals) & set(reference.signals))


def _series(log: SensorLog, name: str) -> tuple[tuple[float, float], ...]:
    if name not in log.signals:
        raise ValueError(f'CSVに信号列「{name}」がありません。')
    return tuple((float(t), float(v)) for t, v in zip(log.times, log.signals[name]) if v is not None)


def compare_logs(measured: SensorLog, reference: SensorLog,
                 measured_signal: str, reference_signal: str,
                 *, unit_confirmed: bool, time_shift_s: float = 0.0) -> CompareResult:
    if not unit_confirmed:
        raise ValueError('2つの信号が同じ物理量・単位であることを確認してください。')
    if not math.isfinite(time_shift_s) or abs(time_shift_s) > 86400:
        raise ValueError('時刻ずらしは±86400秒以内の有限値で指定してください。')
    if measured.time_kind == 'sample' or reference.time_kind == 'sample':
        raise ValueError('時間列のないCSVは秒単位で比較できません。')
    m = _series(measured, measured_signal)
    r = _series(reference, reference_signal)
    if len(m) < 2 or len(r) < 2:
        raise ValueError('選択した信号は、それぞれ2件以上の有効な数値が必要です。')
    if any(b[0] <= a[0] for seq in (m, r) for a, b in zip(seq, seq[1:])):
        raise ValueError('有効な信号の時刻が昇順ではありません。')
    # Reference shifted time = reference original time + time_shift_s.
    # No extrapolation; only compare measurements within the shifted reference span.
    pts: list[MatchPoint] = []
    j = 0
    eps = 1e-9
    lo, hi = r[0][0] + time_shift_s, r[-1][0] + time_shift_s
    for t, value in m:
        if t < lo - eps or t > hi + eps:
            continue
        original_t = max(r[0][0], min(r[-1][0], t - time_shift_s))
        while j + 1 < len(r) and r[j + 1][0] < original_t - eps:
            j += 1
        if j + 1 >= len(r):
            ref_value = r[-1][1]
        else:
            t0, v0 = r[j]
            t1, v1 = r[j + 1]
            fraction = min(1.0, max(0.0, (original_t - t0) / (t1 - t0)))
            ref_value = v0 + fraction * (v1 - v0)
        error = value - ref_value
        pts.append(MatchPoint(round(t, 9), value, ref_value, error))
        if len(pts) > MAX_RESULTS:
            raise ValueError('比較結果の件数上限を超えました。')
    if not pts:
        raise ValueError('時間範囲が重なっていません。時刻ずらしを調整してください。')
    errors = [p.error for p in pts]
    n = len(errors)
    unit_m = measured.units.get(measured_signal, '')
    unit_r = reference.units.get(reference_signal, '')
    unit = unit_m if unit_m == unit_r and unit_m not in ('（元CSVの単位）', '') else '利用者が確認した共通単位'
    return CompareResult(
        measured.source_name, reference.source_name,
        measured.source_sha256, reference.source_sha256,
        measured_signal, reference_signal, unit, float(time_shift_s),
        len(m), n, n/len(m), sum(abs(e) for e in errors)/n,
        math.sqrt(sum(e*e for e in errors)/n), sum(errors)/n,
        max(abs(e) for e in errors), tuple(pts),
    )


def csv_text(result: CompareResult) -> str:
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, lineterminator='\n')
    writer.writerow(['time_s', 'measured', 'reference_interpolated', 'error_measured_minus_reference'])
    for p in result.points:
        writer.writerow([format(p.time_s, '.10g'), format(p.measured, '.12g'),
                         format(p.reference, '.12g'), format(p.error, '.12g')])
    return stream.getvalue()


def report(result: CompareResult) -> dict:
    return {
        'schema_version': 'v19-offline-compare-1',
        'validation': 'not_hardware_validation',
        'reference_alignment': 'reference_time_plus_shift_s',
        'method': 'linear_interpolation_no_extrapolation',
        'measured': {'file': result.measured_file, 'sha256': result.measured_sha256,
                     'signal': result.measured_signal},
        'reference': {'file': result.reference_file, 'sha256': result.reference_sha256,
                      'signal': result.reference_signal},
        'unit': result.unit, 'time_shift_s': result.time_shift_s,
        'measured_valid_samples': result.measured_valid,
        'matched_samples': result.matched,
        'coverage_fraction': result.coverage_fraction,
        'mae': result.mae, 'rmse': result.rmse,
        'bias_measured_minus_reference': result.bias,
        'max_absolute_error': result.max_abs_error,
        'notes': ['重なる時刻だけ比較し、参考CSVを線形補間します。',
                  '時間列は各CSVの先頭を0秒とした経過時間です。',
                  '単位の一致は利用者の確認に依存します。',
                  '差が小さくても実機の正しさ・物理モデルの妥当性は保証しません。'],
    }


def save_result(result: CompareResult, path: str | Path, kind: str) -> None:
    target = Path(path)
    if kind == 'csv':
        target.write_text(csv_text(result), encoding='utf-8-sig')
    elif kind == 'json':
        target.write_text(json.dumps(report(result), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    else:
        raise ValueError('保存形式はcsvまたはjsonです。')
