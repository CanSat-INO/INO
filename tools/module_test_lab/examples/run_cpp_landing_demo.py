"""CLI demonstration of host-C++ step function. No PySide6 required."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cpp_landing_runner import DEMO_SOURCE, run_landing_cpp

INPUT = Path.home() / "cansat_module_lab_data" / "demo_virtual_landing.csv"
if not INPUT.is_file():
    sys.exit(f"入力サンプルがありません: {INPUT}\n"
             "先に examples/make_demo_csv.py を実行してください。")
result = run_landing_cpp(INPUT, DEMO_SOURCE)
print("C++コード:", result.source_name)
print("評価:", result.summary["status"])
print("接地時刻:", result.summary["true_contact_s"], "s")
print("C++検知時刻:", result.summary["detected_time_s"], "s")
print("遅延:", result.summary["delay_s"], "s")
print("※ローカルでのテストです。実機ESP32-S3の動作保証ではありません。")
