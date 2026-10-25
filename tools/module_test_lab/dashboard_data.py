"""Read-only dashboard helpers for experiment ledger records.

Only existing record metrics and uploaded CSV traces are displayed; nothing is
estimated or called an actual measurement when it came from a reference model.
"""
from __future__ import annotations

import csv
import hashlib
import math
import re
from pathlib import Path

from records import ATTACHMENTS_DIR, MAX_ATTACHMENT_BYTES

_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def is_reference(record: dict) -> bool:
    return record.get("mode") == "仮想参考モデル"


def number(value):
    """Return finite float or None; booleans are not valid numeric metrics."""
    if value is None or isinstance(value, bool):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return n if math.isfinite(n) else None


def summary(records: list[dict]) -> dict:
    success = sum(r.get("status") == "成功" for r in records)
    failed = sum(r.get("status") == "失敗" for r in records)
    decided = success + failed
    return {"total": len(records), "success": success, "failed": failed,
            "undecided": len(records) - decided,
            "success_rate": (100.0 * success / decided) if decided else None,
            "reference": sum(is_reference(r) for r in records),
            "non_reference": sum(not is_reference(r) for r in records)}


def filter_records(records: list[dict], module="すべて", source="すべて", status="すべて", tester="") -> list[dict]:
    needle = tester.casefold().strip()
    out = []
    for r in records:
        if module != "すべて" and r.get("module") != module:
            continue
        if source == "参考モデルのみ" and not is_reference(r):
            continue
        if source == "参考モデル以外" and is_reference(r):
            continue
        if status != "すべて" and r.get("status", "未判定") != status:
            continue
        if needle and needle not in str(r.get("tester", "")).casefold():
            continue
        out.append(r)
    return sorted(out, key=lambda r: r.get("created_at", ""), reverse=True)


def module_summary(records: list[dict]) -> list[dict]:
    by_name = {}
    for r in records:
        by_name.setdefault(r.get("module") or "その他", []).append(r)
    return [{"module": key, **summary(value)} for key, value in sorted(by_name.items())]


def delay_points(records: list[dict], max_points=24) -> list[tuple[str, float, str]]:
    """Only records explicitly providing finite delay_s are plotted."""
    points = []
    for r in sorted(records, key=lambda r: r.get("created_at", "")):
        delay = number((r.get("metrics") or {}).get("delay_s"))
        if delay is not None:
            title = f"{str(r.get('created_at', ''))[5:16]} {str(r.get('tester') or '未入力')[:8]}"
            points.append((title, delay, str(r.get("id", ""))))
    return points[-max_points:]


def _boolean(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in ("1", "true", "yes")


def _first_float(row: dict, *keys):
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return number(row[key])
    return None


def read_trace(record: dict, attachment_root: Path | None = None) -> dict:
    """Load a verified saved CSV trace. Never reads paths from arbitrary record fields.

    Supports the reference model's time_s and suggested Arduino time_ms format.
    Returns a trace + event metadata or a descriptive reason with an empty trace.
    """
    root = Path(attachment_root) if attachment_root is not None else ATTACHMENTS_DIR
    record_id = record.get("id", "")
    if not isinstance(record_id, str) or not _ID_RE.fullmatch(record_id):
        return {"trace": [], "message": "実験IDの形式が不正です。"}
    attachments = record.get("attachments") or []
    if not isinstance(attachments, list):
        return {"trace": [], "message": "添付情報の形式が不正です。"}
    candidates = [a for a in attachments if isinstance(a, dict) and str(a.get("name", "")).lower().endswith(".csv")]
    candidates.sort(key=lambda a: a.get("name") != "virtual_sensor_trace.csv")
    if not candidates:
        return {"trace": [], "message": "CSVログの添付がありません。詳細情報は上に表示しています。"}
    problems = []
    for att in candidates:
        name = att.get("name", "")
        if (not isinstance(name, str) or not name or name in (".", "..") or
            Path(name).name != name or "/" in name or "\\" in name):
            problems.append("不正なファイル名"); continue
        path = root / record_id / name
        if not path.is_file():
            problems.append(f"{name}: ローカルに添付ファイルがありません。GitHubから取り込んでください。"); continue
        if path.stat().st_size > MAX_ATTACHMENT_BYTES:
            problems.append(f"{name}: ファイルが大きすぎます。"); continue
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != att.get("sha256"):
            problems.append(f"{name}: SHA256が一致しません（改変の可能性）。"); continue
        try:
            from io import StringIO
            reader = csv.DictReader(StringIO(content.decode("utf-8-sig")))
            fields = set(reader.fieldnames or [])
            if not ({"time_s", "time_ms"} & fields):
                problems.append(f"{name}: time_s または time_ms 列がありません。"); continue
            if not ({"imu_z_mps2", "pressure_pa"} & fields):
                problems.append(f"{name}: IMU・気圧の列がありません。"); continue
            trace = []
            detected_from_csv = None
            for i, row in enumerate(reader):
                if i >= 100000:
                    raise ValueError("行数が10万件を超えました。")
                t = _first_float(row, "time_s")
                if t is None:
                    ms = _first_float(row, "time_ms")
                    t = None if ms is None else ms / 1000.0
                if t is None or t < 0:
                    continue
                imu = _first_float(row, "imu_z_mps2")
                pressure = _first_float(row, "pressure_pa")
                if imu is None and pressure is None:
                    continue
                detected = _boolean(row.get("landing_detected", False))
                if detected and detected_from_csv is None and "landing_detected" in fields:
                    detected_from_csv = t
                trace.append({"time_s": t, "imu_z_mps2": imu,
                              "pressure_pa": pressure,
                              "truth_contact": _boolean(row.get("truth_contact", False))})
            if not trace:
                problems.append(f"{name}: グラフに表示できる有効な数値がありません。"); continue
            trace.sort(key=lambda x: x["time_s"])
            metrics = record.get("metrics") or {}
            if not isinstance(metrics, dict): metrics = {}
            contact = number(metrics.get("true_contact_s"))
            detected = number(metrics.get("detected_time_s"))
            detected_source = "保存された判定時刻" if detected is not None else ""
            if detected is None and detected_from_csv is not None:
                detected = detected_from_csv
                detected_source = "CSVの着地フラグ（最初に1になった時刻）"
            return {"trace": trace, "message": f"表示ログ: {name}（{len(trace)}点）",
                    "contact_time": contact, "detected_time": detected,
                    "detected_source": detected_source, "filename": name}
        except (UnicodeError, csv.Error, ValueError, OSError) as exc:
            problems.append(f"{name}: {exc}")
    return {"trace": [], "message": " / ".join(problems) or "対応形式のCSVがありません。"}
