"""Generate an explicitly synthetic CSV that mimics an Arduino logging format."""
from pathlib import Path
import csv
import sys

# The installed script lives at tools/module_test_lab/examples/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from landing_sim import Config, make_trace, reference_detect

trace = make_trace("normal")
result = reference_detect(trace, Config())
detected = result["detected_time_s"]
assert detected is not None
out = Path.home() / "cansat_module_lab_data" / "demo_virtual_landing.csv"
out.parent.mkdir(parents=True, exist_ok=True)
with out.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=[
        "time_ms", "imu_z_mps2", "pressure_pa", "landing_detected", "truth_contact"])
    writer.writeheader()
    for row in trace:
        writer.writerow({
            "time_ms": round(row["time_s"] * 1000),
            "imu_z_mps2": row["imu_z_mps2"],
            "pressure_pa": "" if row["pressure_pa"] is None else row["pressure_pa"],
            "landing_detected": int(row["time_s"] >= detected),
            "truth_contact": int(row["truth_contact"]),
        })
print(f"仮想データのCSVを作成しました: {out}")
print("※実機由来のArduinoログではありません。")
