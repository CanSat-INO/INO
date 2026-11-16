"""REGULUS QMI8658シリアルログの読み取り専用解析。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
from statistics import fmean


MAX_LOG_BYTES = 1024 * 1024
MAX_LINES = 50000

FIELDS = ("ax", "ay", "az", "gx", "gy", "gz")

SAMPLE_PATTERN = re.compile(
    r"^A\[m/s2\]\s+(\S+)\s+(\S+)\s+(\S+)"
    r"\s+G\[dps\]\s+(\S+)\s+(\S+)\s+(\S+)\s*$"
)


def parse_imu_text(text: str) -> dict:
    """実コードのSerial.printf出力を解析する。"""

    if len(text.encode("utf-8")) > MAX_LOG_BYTES:
        raise ValueError("ログが1MiBを超えています")

    lines = text.splitlines()

    if len(lines) > MAX_LINES:
        raise ValueError("ログの行数が上限を超えています")

    samples = []
    read_failures = 0
    initialization_failures = 0
    malformed_samples = 0
    ignored_lines = 0

    for raw in lines:
        line = raw.strip()

        if "QMI8658 initialization failed" in line:
            initialization_failures += 1
            continue

        if "QMI8658 read failed" in line:
            read_failures += 1
            continue

        if not line.startswith("A[m/s2]"):
            if line:
                ignored_lines += 1
            continue

        match = SAMPLE_PATTERN.fullmatch(line)

        if match is None:
            malformed_samples += 1
            continue

        try:
            values = tuple(float(s) for s in match.groups())
        except ValueError:
            malformed_samples += 1
            continue

        if not all(math.isfinite(v) for v in values):
            malformed_samples += 1
            continue

        sample = dict(zip(FIELDS, values))

        sample["accel_norm_mps2"] = math.sqrt(
            sample["ax"] ** 2
            + sample["ay"] ** 2
            + sample["az"] ** 2
        )

        sample["gyro_norm_dps"] = math.sqrt(
            sample["gx"] ** 2
            + sample["gy"] ** 2
            + sample["gz"] ** 2
        )

        samples.append(sample)

    stats = {}

    if samples:
        for key in (
            *FIELDS,
            "accel_norm_mps2",
            "gyro_norm_dps",
        ):
            numbers = [s[key] for s in samples]

            stats[key] = {
                "min": round(min(numbers), 6),
                "max": round(max(numbers), 6),
                "mean": round(fmean(numbers), 6),
            }

    has_warnings = any((
        read_failures,
        initialization_failures,
        malformed_samples,
    ))

    if not samples:
        status = "NO_VALID_SAMPLES"
    elif has_warnings:
        status = "WARNING"
    else:
        status = "PARSED"

    return {
        "status": status,
        "sample_count": len(samples),
        "read_failures": read_failures,
        "initialization_failures": initialization_failures,
        "malformed_samples": malformed_samples,
        "ignored_lines": ignored_lines,
        "statistics": stats,
        "samples": samples,
        "limitations": [
            "時刻情報がないため測定周期と欠損間隔は判定不可",
            "数値の解析結果はセンサー精度の合格判定ではない",
            "ESP32やセンサーの実機動作は検証していない",
        ],
    }


def read_imu_log(path: str | Path) -> dict:
    source = Path(path).expanduser()

    if not source.is_file():
        raise ValueError("ログファイルが見つかりません")

    if source.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("ログが1MiBを超えています")

    text = source.read_text(encoding="utf-8-sig")
    return parse_imu_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("logfile")
    args = parser.parse_args()

    result = read_imu_log(args.logfile)

    # ターミナルでは要約のみを表示
    result = {
        key: value
        for key, value in result.items()
        if key != "samples"
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
