"""Offline, CSV-only CanSat sensor log analysis (v15).

No hardware connections, Arduino execution, web or ROS dependencies.
Time gaps and abrupt changes are *review candidates*, not a hardware diagnosis.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import csv
import io
import json
import math
import re
import statistics
import unicodedata
from typing import Iterable

MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_ROWS = 50_000
MAX_COLUMNS = 80
MAX_SIGNALS = 40

# Normalized headers, in priority order. Never silently assume unlabeled milliseconds.
TIME_MS = {"time_ms", "timestamp_ms", "elapsed_ms", "t_ms", "millis", "時間ms", "経過時間ms", "時刻ms"}
TIME_SEC = {"time_s", "timestamp_s", "elapsed_s", "t_s", "time", "t", "seconds", "秒", "時間s", "経過秒"}
TIME_ISO = {"datetime", "date_time", "iso_time", "timestamp_iso", "日時", "計測日時", "記録時刻"}

ALIASES = {
    "accel_x_mps2": ("ax", "accel_x", "acc_x", "acceleration_x", "加速度x", "加速度x_mps2"),
    "accel_y_mps2": ("ay", "accel_y", "acc_y", "acceleration_y", "加速度y", "加速度y_mps2"),
    "accel_z_mps2": ("az", "accel_z", "acc_z", "acceleration_z", "加速度z", "加速度z_mps2"),
    "accel_norm_mps2": ("accel_mps2", "accel_norm", "acceleration", "合成加速度", "加速度ノルム"),
    "gyro_x_dps": ("gx", "gyro_x", "角速度x"),
    "gyro_y_dps": ("gy", "gyro_y", "角速度y"),
    "gyro_z_dps": ("gz", "gyro_z", "角速度z"),
    "pressure_pa": ("pressure", "baro_pa", "気圧pa"),
    "pressure_hpa": ("baro_hpa", "気圧hpa"),
    "temperature_c": ("temp_c", "temperature", "temp", "気温", "温度", "気温c", "温度c"),
    "humidity_pct": ("humidity", "rh", "湿度", "湿度pct"),
    "altitude_m": ("altitude", "height_m", "高度", "高度m"),
    "latitude_deg": ("latitude", "lat", "緯度"),
    "longitude_deg": ("longitude", "lon", "lng", "経度"),
    "speed_mps": ("speed", "速度", "速さ"),
    "red_ratio": ("red_occupancy", "red_fraction", "赤占有率", "赤点有率"),
    "motor_pwm": ("pwm", "motor_output", "モーターpwm"),
    "gnss_fix": ("gps_fix", "fix", "測位状態"),
}
UNITS = {
    "accel_x_mps2": "m/s²", "accel_y_mps2": "m/s²", "accel_z_mps2": "m/s²", "accel_norm_mps2": "m/s²",
    "gyro_x_dps": "°/s", "gyro_y_dps": "°/s", "gyro_z_dps": "°/s",
    "pressure_pa": "Pa", "pressure_hpa": "hPa", "temperature_c": "°C",
    "humidity_pct": "%", "altitude_m": "m", "latitude_deg": "°", "longitude_deg": "°",
    "speed_mps": "m/s", "red_ratio": "0–1", "motor_pwm": "PWM値", "gnss_fix": "0/1",
}
MISSING = {"", "-", "--", "nan", "null", "none", "n/a", "na"}


def _norm(text: str) -> str:
    text = unicodedata.normalize('NFKC', text.strip()).casefold()
    text = text.replace(' ', '_').replace('-', '_').replace('(', '_').replace(')', '').replace('[', '_').replace(']', '')
    return re.sub(r'_+', '_', text).strip('_')

_CANON = {_norm(key): key for key in ALIASES}
for _key, _alternatives in ALIASES.items():
    for _a in _alternatives:
        _CANON[_norm(_a)] = _key


@dataclass(frozen=True)
class ChannelStats:
    name: str
    unit: str
    count: int
    missing: int
    minimum: float | None
    maximum: float | None
    mean: float | None


@dataclass(frozen=True)
class SensorLog:
    source_name: str
    source_sha256: str
    encoding: str
    time_kind: str
    times: tuple[float, ...]
    signals: dict[str, tuple[float | None, ...]]
    units: dict[str, str]
    issues: tuple[str, ...]

    @property
    def row_count(self) -> int:
        return len(self.times)


def _parse_number(raw: str, header: str, line: int) -> float | None:
    s = str(raw).strip()
    if s.casefold() in MISSING:
        return None
    try:
        result = float(s)
    except ValueError as exc:
        raise ValueError(f'{line}行目の「{header}」は数値ではありません: {s[:40]}') from exc
    if not math.isfinite(result):
        raise ValueError(f'{line}行目の「{header}」は有限の数値を入力してください。')
    return result


def _time_parser(field: str):
    normalized = _norm(field)
    if normalized in {_norm(x) for x in TIME_MS}:
        return 'ms'
    if normalized in {_norm(x) for x in TIME_SEC}:
        return 's'
    if normalized in {_norm(x) for x in TIME_ISO}:
        return 'iso'
    return None


def _read_text(path: Path) -> tuple[str, str, str]:
    if not path.is_file():
        raise ValueError('CSVファイルが見つかりません。')
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f'CSVの上限は{MAX_FILE_BYTES // 1024 // 1024}MBです。')
    raw = path.read_bytes()
    if b'\x00' in raw:
        raise ValueError('バイナリ形式のファイルは読み込めません。')
    for encoding in ('utf-8-sig', 'cp932'):
        try:
            return raw.decode(encoding), encoding, sha256(raw).hexdigest()
        except UnicodeDecodeError:
            pass
    raise ValueError('文字コードはUTF-8またはWindows日本語(CP932)を使用してください。')


def read_sensor_csv(path: str | Path) -> SensorLog:
    path = Path(path)
    text, encoding, digest = _read_text(path)
    try:
        reader = csv.reader(io.StringIO(text, newline=''), strict=True)
        headers = next(reader, None)
        if not headers or not any(h.strip() for h in headers):
            raise ValueError('CSVのヘッダーがありません。')
        headers = [h.strip() for h in headers]
        if len(headers) > MAX_COLUMNS:
            raise ValueError(f'列数は{MAX_COLUMNS}以下にしてください。')
        if any(not h for h in headers) or len(set(_norm(h) for h in headers)) != len(headers):
            raise ValueError('空欄または重複した列名があります。')
        time_candidates = [(index, _time_parser(h)) for index, h in enumerate(headers) if _time_parser(h)]
        if len(time_candidates) > 1:
            raise ValueError('時間列が複数あります。time_sまたはtime_msを1列だけ指定してください。')
        time_index, time_kind = time_candidates[0] if time_candidates else (None, 'sample')
        rows = []
        for i, row in enumerate(reader, start=2):
            if not row or not any(v.strip() for v in row):
                continue
            if len(row) != len(headers):
                raise ValueError(f'{i}行目: 列数が一致しません（期待{len(headers)}列、実際{len(row)}列）。')
            rows.append(row)
            if len(rows) > MAX_ROWS:
                raise ValueError(f'CSVは最大{MAX_ROWS}データ行までです。')
    except csv.Error as exc:
        raise ValueError(f'CSV形式が正しくありません: {exc}') from exc
    if not rows:
        raise ValueError('CSVにデータ行がありません。')

    if time_kind == 'sample':
        times = tuple(float(i) for i in range(len(rows)))
    else:
        parsed_times = []
        for line, row in enumerate(rows, start=2):
            entry = row[time_index].strip()
            if time_kind == 'iso':
                try:
                    point = datetime.fromisoformat(entry.replace('Z', '+00:00')).timestamp()
                except (ValueError, OverflowError) as exc:
                    raise ValueError(f'{line}行目の日時を解釈できません: {entry[:40]}') from exc
            else:
                point = _parse_number(entry, headers[time_index], line)
                if point is None:
                    raise ValueError(f'{line}行目の時間が空欄です。')
                if time_kind == 'ms':
                    point /= 1000.0
            if not math.isfinite(point):
                raise ValueError(f'{line}行目の時間が無効です。')
            parsed_times.append(point)
        offset = parsed_times[0]
        times = tuple(t - offset for t in parsed_times)  # Display elapsed time, preserve intervals.

    signals: dict[str, tuple[float | None, ...]] = {}
    units: dict[str, str] = {}
    issues: list[str] = []
    for index, header in enumerate(headers):
        if index == time_index:
            continue
        canonical = _CANON.get(_norm(header), header)
        if canonical in signals:
            raise ValueError(f'「{header}」と別の列が同じ信号名「{canonical}」になります。片方を削除してください。')
        data = [r[index].strip() for r in rows]
        valid_entries = [val for val in data if val.casefold() not in MISSING]
        if not valid_entries:
            # Keep a recognized missing-only signal, so the report exposes failed sensors.
            if canonical not in UNITS:
                continue
        elif canonical not in UNITS:
            numeric_ratio = sum(_is_finite_number(v) for v in valid_entries) / len(valid_entries)
            if numeric_ratio < 0.9:
                continue  # Text label / notes column, not a numeric measurement.
        parsed = tuple(_parse_number(v, header, line) for line, v in enumerate(data, start=2))
        signals[canonical] = parsed
        units[canonical] = UNITS.get(canonical, '（元CSVの単位）')
        if len(signals) > MAX_SIGNALS:
            raise ValueError(f'数値の信号列は最大{MAX_SIGNALS}列までです。')
    if not signals:
        raise ValueError('利用できる数値信号列がありません。列名とデータを確認してください。')
    if time_kind == 'sample':
        issues.append('時間列がないため、横軸はサンプル番号です（秒ではありません）。')
    return SensorLog(path.name, digest, encoding, time_kind, times, signals, units, tuple(issues))


def _is_finite_number(text: str) -> bool:
    try:
        return math.isfinite(float(text))
    except ValueError:
        return False


def stats_for(log: SensorLog) -> list[ChannelStats]:
    result = []
    for name, data in log.signals.items():
        values = [v for v in data if v is not None]
        result.append(ChannelStats(name, log.units[name], len(values), len(data) - len(values),
                                   min(values) if values else None,
                                   max(values) if values else None,
                                   statistics.fmean(values) if values else None))
    return result


def quality_report(log: SensorLog, *, gap_factor: float = 3.0) -> list[str]:
    if not 1.0 < gap_factor <= 1000:
        raise ValueError('時間ギャップの倍率は1より大きく1000以下にしてください。')
    reports = list(log.issues)
    if log.time_kind != 'sample':
        intervals = [b - a for a, b in zip(log.times, log.times[1:])]
        duplicates = sum(d == 0 for d in intervals)
        reverse = sum(d < 0 for d in intervals)
        if duplicates:
            reports.append(f'時間が重複した箇所：{duplicates}件')
        if reverse:
            reports.append(f'時間が逆行した箇所：{reverse}件（元CSV順）')
        positives = [d for d in intervals if d > 0]
        if len(positives) >= 3:
            typical = statistics.median(positives)
            gaps = sum(d > typical * gap_factor for d in positives)
            if gaps:
                reports.append(f'測定間隔が中央値の{gap_factor:g}倍を超える箇所：{gaps}件（欠測候補）')
    for item in stats_for(log):
        if item.missing:
            reports.append(f'{item.name}: 欠損{item.missing}/{log.row_count}行')
        if item.count == 0:
            reports.append(f'{item.name}: 有効な値がありません')
    for name, low, high in (("latitude_deg", -90, 90), ("longitude_deg", -180, 180),
                            ("humidity_pct", 0, 100), ("red_ratio", 0, 1)):
        if name in log.signals:
            invalid = sum(v is not None and not (low <= v <= high) for v in log.signals[name])
            if invalid:
                reports.append(f'{name}: 一般的な値域[{low},{high}]の外に{invalid}件（単位・形式を確認）')
    if not reports:
        reports.append('基本チェックで欠損・時間異常・値域外は検出されませんでした（実機の正常性は保証しません）。')
    return reports


def summary_dict(log: SensorLog) -> dict:
    return {
        'schema': 'cansat-sensor-summary-v15',
        'source_file': log.source_name,
        'source_sha256': log.source_sha256,
        'encoding': log.encoding,
        'time_axis': {'sample': 'sample_index', 's': 'elapsed_seconds', 'ms': 'elapsed_seconds', 'iso': 'elapsed_seconds'}[log.time_kind],
        'rows': log.row_count,
        'duration': (log.times[-1] - log.times[0]) if log.time_kind != 'sample' else None,
        'channels': [vars(item) for item in stats_for(log)],
        'data_quality_notes': quality_report(log),
        'interpretation': 'CSV品質確認のみ。異常候補は故障判定ではなく、測定・機体・コードの正常性を保証しません。',
    }


def _spreadsheet_safe(value: str) -> str:
    # Avoid CSV formula execution in Excel, including whitespace-prefixed formulas.
    if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r')):
        return "'" + value
    return value


def export_summary(log: SensorLog, path: str | Path) -> None:
    path = Path(path)
    summary = summary_dict(log)
    if path.suffix.lower() == '.json':
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    elif path.suffix.lower() == '.csv':
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['signal', 'unit', 'count', 'missing', 'min', 'max', 'mean', 'source_sha256'])
            for item in stats_for(log):
                writer.writerow([_spreadsheet_safe(item.name), _spreadsheet_safe(item.unit), item.count,
                                 item.missing, item.minimum, item.maximum, item.mean, log.source_sha256])
    else:
        raise ValueError('解析レポートの保存形式は.csvまたは.jsonのみ対応しています。')
