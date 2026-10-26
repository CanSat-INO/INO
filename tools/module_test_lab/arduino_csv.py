"""Read and evaluate Arduino-style landing CSV logs (no firmware execution).

The CSV contains *observed* outputs of a separately run Arduino/host test.
Ground truth must come from truth_contact in CSV or a human-entered value.
An absence of truth never becomes a fabricated pass or fail.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
import io
import math
from pathlib import Path

MAX_CSV_BYTES = 900 * 1024  # Fits the existing GitHub attachment limit.
MAX_ROWS = 100_000


@dataclass(frozen=True)
class Log:
    rows: tuple[dict, ...]
    source_name: str
    has_truth_column: bool
    detected_time_s: float | None
    truth_time_s: float | None
    starts_detected: bool
    rising_events: tuple[float, ...]


def _finite_float(raw: str | None, column: str, line: int, *, required: bool) -> float | None:
    raw = "" if raw is None else str(raw).strip()
    if not raw:
        if required:
            raise ValueError(f"{line}行目: {column} が空欄です。")
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{line}行目: {column} は数値で入力してください。") from exc
    if not math.isfinite(value):
        raise ValueError(f"{line}行目: {column} は有限の数値にしてください。")
    return value


def _flag(raw: str | None, column: str, line: int) -> bool:
    word = str(raw if raw is not None else "").strip().lower()
    if word in ("1", "true", "yes"):
        return True
    if word in ("0", "false", "no"):
        return False
    raise ValueError(f"{line}行目: {column} は 0/1 (true/false) にしてください。")


def read_csv(path: str | Path) -> Log:
    """Load a small untrusted UTF-8 CSV, never execute its content."""
    src = Path(path)
    if not src.is_file():
        raise ValueError("CSVファイルが見つかりません。")
    size = src.stat().st_size
    if size > MAX_CSV_BYTES:
        raise ValueError(f"CSVが大きすぎます（上限{MAX_CSV_BYTES // 1024} KiB、GitHub共有用）。")
    try:
        content = src.read_bytes().decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("CSVはUTF-8で保存してください。") from exc
    return parse_csv_text(content, source_name=src.name)


def parse_csv_text(content: str, source_name: str = "input.csv") -> Log:
    if len(content.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValueError("CSVが大きすぎます。")
    reader = csv.DictReader(io.StringIO(content))
    headers = reader.fieldnames or []
    if len(headers) != len(set(headers)) or any(not h for h in headers):
        raise ValueError("CSVの列名に重複または空欄があります。")
    if not ("time_ms" in headers or "time_s" in headers):
        raise ValueError("CSVに time_ms または time_s 列が必要です。")
    if "landing_detected" not in headers:
        raise ValueError("CSVに landing_detected 列が必要です。")
    if len(headers) > 40:
        raise ValueError("CSVの列数が多すぎます。")
    has_truth = "truth_contact" in headers
    tkey = "time_ms" if "time_ms" in headers else "time_s"
    rows = []
    contact = None
    detected = None
    rising = []
    last_t = None
    previous_detected = False
    starts_detected = False
    try:
        for index, item in enumerate(reader):
            line = index + 2
            if index >= MAX_ROWS:
                raise ValueError("CSVの行数が上限を超えました。")
            if None in item:  # excess values beyond the header
                raise ValueError(f"{line}行目: 余分な列があります。")
            t = _finite_float(item.get(tkey), tkey, line, required=True)
            assert t is not None
            if tkey == "time_ms":
                t /= 1000.0
            if t < 0 or (last_t is not None and t <= last_t):
                raise ValueError(f"{line}行目: 時刻は0以上で、前の行より大きくしてください。")
            last_t = t
            flag = _flag(item.get("landing_detected"), "landing_detected", line)
            truth = _flag(item.get("truth_contact"), "truth_contact", line) if has_truth else None
            imu = _finite_float(item.get("imu_z_mps2"), "imu_z_mps2", line, required=False)
            press = _finite_float(item.get("pressure_pa"), "pressure_pa", line, required=False)
            if contact is None and truth is True:
                contact = t
            if index == 0 and flag:
                starts_detected = True
            if flag and not previous_detected:
                rising.append(t)
                if detected is None:
                    detected = t
            previous_detected = flag
            rows.append({"time_s": t, "imu_z_mps2": imu,
                         "pressure_pa": press, "landing_detected": flag,
                         "truth_contact": truth})
    except csv.Error as exc:
        raise ValueError(f"CSVの書式が不正です: {exc}") from exc
    if not rows:
        raise ValueError("CSVにデータ行がありません。")
    # Exact time is only sampled: first 'true' timestamp, not necessarily physical instant.
    return Log(tuple(rows), source_name, has_truth, detected, contact,
               starts_detected, tuple(rising))


def analyze(log: Log, *, expected_time_s: float | None = None,
            allowed_delay_s: float = 5.0) -> dict:
    """Evaluate first reported detection. Truth is explicit, never inferred from IMU."""
    if not math.isfinite(allowed_delay_s) or allowed_delay_s < 0:
        raise ValueError("許容遅延は0以上の有限の値にしてください。")
    if expected_time_s is not None and (not math.isfinite(expected_time_s) or expected_time_s < 0):
        raise ValueError("真の接地時刻は0以上の有限の値にしてください。")
    contact = expected_time_s if expected_time_s is not None else log.truth_time_s
    detected = log.detected_time_s
    delay = None if contact is None or detected is None else detected-contact
    if contact is None:
        status = "未判定"
        reason = "接地の正解時刻がありません。CSVのtruth_contact列か手入力で指定してください。"
    elif log.starts_detected:
        status = "未判定"
        reason = "記録開始時点で着地検知済みです。検知した瞬間を特定できません。"
    elif contact < log.rows[0]["time_s"] or contact > log.rows[-1]["time_s"]:
        status = "未判定"
        reason = "正解の接地時刻がCSVの記録範囲外にあります。"
    elif detected is None:
        if log.rows[-1]["time_s"] < contact + allowed_delay_s:
            status = "未判定"
            reason = "検知なし。ただし接地後の観測が許容遅延まで継続していません。"
        else:
            status = "失敗"
            reason = "許容遅延の終了まで記録しましたが、着地が検知されませんでした。"
    elif delay < 0:
        status = "失敗"
        reason = "実際の接地前に着地を検知しています（早期誤判定）。"
    elif delay > allowed_delay_s:
        status = "失敗"
        reason = "着地検知が許容遅延を超えました。"
    else:
        status = "成功"
        reason = "記録された着地検知時刻が許容範囲内です。"
    return {"status": status, "reason": reason,
            "true_contact_s": contact,
            "detected_time_s": detected,
            "delay_s": None if delay is None else round(delay, 6),
            "allowed_delay_s": allowed_delay_s,
            "log_rows": len(log.rows),
            "extra_detection_events": max(0, len(log.rising_events)-1),
            "starts_detected": log.starts_detected}
