"""REGULUS HP203Bシリアルログの読み取り専用解析。"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
from statistics import fmean

MAX_LOG_BYTES = 1024 * 1024
MAX_LINES = 50000

PATTERN = re.compile(
    r"^pressure=(\S+)\s+hPa\s+"
    r"temperature=(\S+)\s+C\s+"
    r"altitude=(\S+)\s+m\s*$"
)

FIELDS = ("pressure_hpa", "temperature_c", "altitude_m")


def parse_baro_text(text: str) -> dict:
    if len(text.encode("utf-8")) > MAX_LOG_BYTES:
        raise ValueError("ログが1MiBを超えています")

    lines = text.splitlines()
    if len(lines) > MAX_LINES:
        raise ValueError("ログの行数が上限を超えています")

    samples = []
    read_failures = 0
    initialization_failures = 0
    malformed_samples = 0
    invalid_values = 0
    ignored_lines = 0

    for raw in lines:
        line = raw.strip()

        if "HP203B initialization failed" in line:
            initialization_failures += 1
            continue

        if "HP203B read failed" in line:
            read_failures += 1
            continue

        if not line.startswith("pressure="):
            if line:
                ignored_lines += 1
            continue

        match = PATTERN.fullmatch(line)
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

        pressure, temperature, altitude = values

        # 明らかに物理的に成立しない値を除外
        if pressure <= 0 or temperature < -273.15:
            invalid_values += 1
            continue

        samples.append(dict(zip(FIELDS, values)))

    statistics = {}

    for key in FIELDS:
        if not samples:
            break

        numbers = [sample[key] for sample in samples]
        statistics[key] = {
            "min": round(min(numbers), 6),
            "max": round(max(numbers), 6),
            "mean": round(fmean(numbers), 6),
        }

    altitude_change = None
    altitude_range = None

    if samples:
        altitudes = [s["altitude_m"] for s in samples]
        altitude_change = round(
            altitudes[-1] - altitudes[0], 6
        )
        altitude_range = round(
            max(altitudes) - min(altitudes), 6
        )

    has_warning = any((
        read_failures,
        initialization_failures,
        malformed_samples,
        invalid_values,
    ))

    if not samples:
        status = "NO_VALID_SAMPLES"
    elif has_warning:
        status = "WARNING"
    else:
        status = "PARSED"

    return {
        "status": status,
        "sample_count": len(samples),
        "read_failures": read_failures,
        "initialization_failures": initialization_failures,
        "malformed_samples": malformed_samples,
        "invalid_values": invalid_values,
        "ignored_lines": ignored_lines,
        "statistics": statistics,
        "altitude_change_m": altitude_change,
        "altitude_range_m": altitude_range,
        "samples": samples,
        "limitations": [
            "時刻がないため高度変化速度は計算不可",
            "高度変化量は最後の測定値から最初の測定値を引いた値",
            "統計値だけではセンサー精度を判定できない",
            "実機のHP203Bの正常動作を保証する試験ではない",
        ],
    }


def read_baro_log(path: str | Path) -> dict:
    source = Path(path).expanduser()

    if not source.is_file():
        raise ValueError("ログファイルが見つかりません")

    if source.stat().st_size > MAX_LOG_BYTES:
        raise ValueError("ログが1MiBを超えています")

    text = source.read_text(encoding="utf-8-sig")
    return parse_baro_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("logfile")
    args = parser.parse_args()

    report = read_baro_log(args.logfile)
    report.pop("samples", None)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
