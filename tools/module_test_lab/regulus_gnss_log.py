"""REGULUS GNSSログの読み取り専用解析。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re

MAX_LOG_BYTES = 1024 * 1024
MAX_LINES = 50000

SNAPSHOT = re.compile(
    r"^valid=(\S+)\s+fix=(\S+)\s+"
    r"lat=(\S+)\s+lon=(\S+)\s+"
    r"alt=(\S+)\s+m\s+sats=(\S+)\s+"
    r"age=(\S+)\s+ms\s+chars=(\S+)\s+"
    r"ok=(\S+)\s+failed=(\S+)$"
)

NMEA = re.compile(r"^\$([^*]+)\*([0-9A-Fa-f]{2})$")


def _unsigned_int(value):
    if not re.fullmatch(r"[0-9]+", value):
        raise ValueError("不正な整数値")
    return int(value)


def _parse_snapshot(match):
    values = match.groups()

    valid = _unsigned_int(values[0])
    fix = _unsigned_int(values[1])

    if valid not in (0, 1) or fix not in (0, 1):
        raise ValueError("valid/fixは0か1")

    latitude = float(values[2])
    longitude = float(values[3])
    altitude = float(values[4])

    if not all(math.isfinite(v) for v in (
        latitude, longitude, altitude
    )):
        raise ValueError("有限でない位置情報")

    if not (-90 <= latitude <= 90):
        raise ValueError("緯度が範囲外")

    if not (-180 <= longitude <= 180):
        raise ValueError("経度が範囲外")

    return {
        "valid": valid,
        "fix": fix,
        "latitude": latitude,
        "longitude": longitude,
        "altitude_m": altitude,
        "satellites": _unsigned_int(values[5]),
        "age_ms": _unsigned_int(values[6]),
        "chars": _unsigned_int(values[7]),
        "passed_checksum": _unsigned_int(values[8]),
        "failed_checksum": _unsigned_int(values[9]),
    }


def _nmea_indication(payload):
    """NMEAのGGA/RMCから測位状態の表示値だけを取得。"""
    fields = payload.split(",")
    sentence = fields[0].upper()

    if sentence.endswith("GGA") and len(fields) > 6:
        try:
            quality = _unsigned_int(fields[6])
        except ValueError:
            return "UNKNOWN"
        return "FIX_INDICATED" if quality > 0 else "NO_FIX"

    if sentence.endswith("RMC") and len(fields) > 2:
        if fields[2] == "A":
            return "FIX_INDICATED"
        if fields[2] == "V":
            return "NO_FIX"

    return "UNKNOWN"


def parse_gnss_text(text):
    if len(text.encode("utf-8")) > MAX_LOG_BYTES:
        raise ValueError("ログが1MiBを超えています")

    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        raise ValueError("ログの行数が上限を超えています")

    result = {
        "status": "NO_VALID_DATA",
        "snapshot_count": 0,
        "reported_fix_count": 0,
        "reported_no_fix_count": 0,
        "inconsistent_fix_count": 0,
        "malformed_snapshots": 0,
        "nmea_count": 0,
        "nmea_bad_checksum": 0,
        "nmea_malformed": 0,
        "nmea_fix_indications": 0,
        "nmea_no_fix_indications": 0,
        "nmea_sentence_types": {},
        "ignored_lines": 0,
        "last_snapshot": None,
        "limitations": [
            "ログの解析はGNSSの測位精度を保証しない",
            "NMEAのチェックサム正常は位置の正確さを意味しない",
            "NMEAの座標復号と軌跡解析は現段階では対象外",
            "測位状態はログに報告された値であり実機検証ではない",
            "age=0だけでは最新データと判断できない",
        ],
    }

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if line.startswith("valid="):
            match = SNAPSHOT.fullmatch(line)

            if match is None:
                result["malformed_snapshots"] += 1
                continue

            try:
                sample = _parse_snapshot(match)
            except (ValueError, OverflowError):
                result["malformed_snapshots"] += 1
                continue

            result["snapshot_count"] += 1
            result["last_snapshot"] = sample

            if sample["valid"] and sample["fix"]:
                result["reported_fix_count"] += 1
            else:
                result["reported_no_fix_count"] += 1

            if sample["fix"] and not sample["valid"]:
                result["inconsistent_fix_count"] += 1

            continue

        if line.startswith("$"):
            match = NMEA.fullmatch(line)

            if match is None:
                result["nmea_malformed"] += 1
                continue

            payload, expected_hex = match.groups()

            checksum = 0
            for char in payload:
                checksum ^= ord(char)

            if checksum != int(expected_hex, 16):
                result["nmea_bad_checksum"] += 1
                continue

            result["nmea_count"] += 1

            sentence_type = payload.split(",", 1)[0].upper()
            counts = result["nmea_sentence_types"]
            counts[sentence_type] = counts.get(sentence_type, 0) + 1

            indication = _nmea_indication(payload)

            if indication == "FIX_INDICATED":
                result["nmea_fix_indications"] += 1
            elif indication == "NO_FIX":
                result["nmea_no_fix_indications"] += 1

            continue

        result["ignored_lines"] += 1

    total = result["snapshot_count"] + result["nmea_count"]

    has_warnings = any(result[key] for key in (
        "inconsistent_fix_count",
        "malformed_snapshots",
        "nmea_bad_checksum",
        "nmea_malformed",
    ))

    if total == 0:
        result["status"] = "NO_VALID_DATA"
    elif has_warnings:
        result["status"] = "WARNING"
    else:
        result["status"] = "PARSED"

    return result


def read_gnss_log(path):
    source = Path(path).expanduser()

    if not source.is_file():
        raise ValueError("ログファイルが見つかりません")

    if source.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("ログが1MiBを超えています")

    return parse_gnss_text(
        source.read_text(encoding="utf-8-sig")
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("logfile")
    args = parser.parse_args()

    result = read_gnss_log(args.logfile)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
