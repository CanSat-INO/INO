"""Execute explicitly selected, TRUSTED host-C++ landing logic against sensor CSV.

Uses the existing v4 CSV analysis; never executes a .ino file or remote attachment.
Compiler and executable run as local processes; do not select untrusted C++ source.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import math
from pathlib import Path
import shutil
import subprocess
import tempfile

from arduino_csv import MAX_CSV_BYTES, MAX_ROWS, analyze, parse_csv_text

BASE = Path(__file__).resolve().parent
API = BASE / "cpp_landing" / "landing_api.h"
RUNNER = BASE / "cpp_landing" / "runner.cpp"
DEMO_SOURCE = BASE / "cpp_landing" / "example_detector.cpp"
MAX_OUTPUT_BYTES = 2_000_000


@dataclass(frozen=True)
class SensorInput:
    rows: tuple[dict, ...]
    original_name: str
    true_contact_s: float | None


@dataclass(frozen=True)
class CppResult:
    csv_text: str
    summary: dict
    log: object
    source_sha256: str
    source_name: str
    original_name: str


def _number(raw, field, row, required=True):
    if raw is None or not str(raw).strip():
        if required:
            raise ValueError(f"{row}行目: {field} は必須です。")
        return None
    try:
        value = float(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{row}行目: {field} は数値にしてください。") from exc
    if not math.isfinite(value):
        raise ValueError(f"{row}行目: {field} は有限の数値にしてください。")
    return value


def read_sensor_csv(path: str | Path) -> SensorInput:
    src = Path(path)
    if not src.is_file():
        raise ValueError("入力CSVが見つかりません。")
    if not (0 < src.stat().st_size <= MAX_CSV_BYTES):
        raise ValueError("入力CSVは1～900KiBまでにしてください。")
    try:
        raw = src.read_bytes().decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("入力CSVはUTF-8形式にしてください。") from exc
    reader = csv.DictReader(io.StringIO(raw))
    columns = reader.fieldnames or []
    if (not columns or any(not col for col in columns) or
            len(set(columns)) != len(columns) or len(columns) > 40):
        raise ValueError("CSVヘッダーが不正です。")
    if not ("time_ms" in columns or "time_s" in columns):
        raise ValueError("time_ms または time_s 列が必要です。")
    if "imu_z_mps2" not in columns:
        raise ValueError("imu_z_mps2 列が必要です。")
    tkey = "time_ms" if "time_ms" in columns else "time_s"
    rows = []
    last_time = None
    truth_start = None
    for idx, line in enumerate(reader):
        line_no = idx + 2
        if idx >= MAX_ROWS:
            raise ValueError("CSV行数が上限を超えました。")
        if None in line:
            raise ValueError(f"{line_no}行目: 余分な列があります。")
        t = _number(line.get(tkey), tkey, line_no)
        ms = t if tkey == "time_ms" else t * 1000.0
        a = _number(line.get("imu_z_mps2"), "imu_z_mps2", line_no)
        pressure = _number(line.get("pressure_pa"), "pressure_pa", line_no, required=False)
        if ms < 0 or ms > 4_294_967_295 or (last_time is not None and ms <= last_time):
            raise ValueError(f"{line_no}行目: 時刻は0以上の昇順、32bitミリ秒範囲内にしてください。")
        last_time = ms
        raw_truth = line.get("truth_contact", "")
        if raw_truth is None or not str(raw_truth).strip():
            truth = None
        elif str(raw_truth).strip().lower() in ("1", "true", "yes"):
            truth = True
        elif str(raw_truth).strip().lower() in ("0", "false", "no"):
            truth = False
        else:
            raise ValueError(f"{line_no}行目: truth_contact は0/1にしてください。")
        if truth and truth_start is None:
            truth_start = ms / 1000.0
        rows.append({"time_ms": ms, "imu_z_mps2": a,
                     "pressure_pa": pressure, "truth_contact": truth})
    if not rows:
        raise ValueError("CSVにデータがありません。")
    return SensorInput(tuple(rows), src.name, truth_start)


def _run(command, *, input_text=None, timeout=12, label="コマンド"):
    try:
        proc = subprocess.run(
            command, input=input_text, text=True, encoding="utf-8",
            errors="replace", stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False,
        )
    except FileNotFoundError as exc:
        raise ValueError("g++ が見つかりません。sudo apt install g++ を実行してください。") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"{label}が制限時間を超えました。") from exc
    if proc.returncode:
        err = proc.stderr.strip()[-1300:]
        raise ValueError(f"{label}に失敗しました（終了コード{proc.returncode}）。\n{err}")
    if len(proc.stdout.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise ValueError(f"{label}の出力が大きすぎます。")
    return proc.stdout


def run_landing_cpp(csv_path: str | Path, source_path: str | Path,
                    *, manual_truth_s: float | None = None,
                    allowed_delay_s: float = 5.0) -> CppResult:
    """Explicitly compile and execute a trusted .cpp; caller must opt in.

    Does not use ROS2 or Arduino SDK. No arbitrary build flags / shell commands.
    """
    sensor = read_sensor_csv(csv_path)
    source = Path(source_path).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".cpp":
        raise ValueError("信頼できるローカルの .cpp ファイルを選んでください。")
    if not (0 < source.stat().st_size <= 100 * 1024):
        raise ValueError("C++コードの上限は100 KiBです。")
    if not math.isfinite(allowed_delay_s) or allowed_delay_s < 0:
        raise ValueError("許容遅延が不正です。")
    if manual_truth_s is not None and (not math.isfinite(manual_truth_s) or manual_truth_s < 0):
        raise ValueError("正解時刻が不正です。")
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="cansat-cpp-") as directory:
        program = Path(directory) / "landing_runner"
        _run(["g++", "-std=c++17", "-O1", "-Wall", "-Wextra",
              "-I", str(API.parent), str(RUNNER), str(source),
              "-o", str(program)], timeout=20, label="C++コンパイル")
        input_lines = "".join(
            f"{r['time_ms']:.10g},{r['imu_z_mps2']:.16g},"
            f"{(-1.0 if r['pressure_pa'] is None else r['pressure_pa']):.16g}\n"
            for r in sensor.rows
        )
        output = _run([str(program)], input_text=input_lines,
                      timeout=10, label="C++判定処理")
    flags = output.splitlines()
    if len(flags) != len(sensor.rows) or any(f not in ("0", "1") for f in flags):
        raise ValueError("C++出力が不正です。各入力行に0/1を1行ずつ返してください。")
    text_buffer = io.StringIO(newline="")
    writer = csv.writer(text_buffer, lineterminator="\n")
    has_truth = any(row["truth_contact"] is not None for row in sensor.rows)
    fields = ["time_ms", "imu_z_mps2", "pressure_pa", "landing_detected"]
    if has_truth:
        fields.append("truth_contact")
    writer.writerow(fields)
    for row, detected in zip(sensor.rows, flags):
        values = [
            f"{row['time_ms']:.10g}", f"{row['imu_z_mps2']:.16g}",
            "" if row["pressure_pa"] is None else f"{row['pressure_pa']:.16g}",
            detected,
        ]
        if has_truth:
            values.append(int(bool(row["truth_contact"])))
        writer.writerow(values)
    generated = text_buffer.getvalue()
    if len(generated.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValueError("出力CSVが共有ファイルの上限900KiBを超えました。入力を短くしてください。")
    log = parse_csv_text(generated, source_name="cpp_landing_output.csv")
    report = analyze(log, expected_time_s=manual_truth_s, allowed_delay_s=allowed_delay_s)
    return CppResult(generated, report, log, source_sha, source.name, sensor.original_name)
