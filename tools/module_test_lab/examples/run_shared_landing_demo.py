"""Run the shared Arduino-compatible logic via the existing host C++ runner."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from cpp_landing_runner import BASE, run_landing_cpp

csv_path = Path.home() / "cansat_module_lab_data" / "demo_virtual_landing.csv"
cpp_path = BASE / "cpp_landing" / "shared_landing" / "host_adapter.cpp"
if not csv_path.is_file():
    raise SystemExit("サンプルCSVがありません。examples/make_demo_csv.py を先に実行してください。")
result = run_landing_cpp(csv_path, cpp_path)
print("使用C++:", cpp_path)
print("判定:", result.summary["status"])
print("検知時刻:", result.summary["detected_time_s"], "s")
print("検知遅延:", result.summary["delay_s"], "s")
print("注意: 仮想サンプルです。Arduino実機の動作保証ではありません。")
