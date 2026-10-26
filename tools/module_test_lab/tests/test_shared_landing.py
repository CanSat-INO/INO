"""Checks reuse of exactly one portable C++ algorithm from Module Test Lab."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from cpp_landing_runner import BASE, run_landing_cpp

SHARED = BASE / "cpp_landing" / "shared_landing"
ADAPTER = SHARED / "host_adapter.cpp"
HEADER = SHARED / "CanSatLandingLogic.h"


@unittest.skipUnless(shutil.which("g++"), "g++ required")
class SharedLandingLogicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shared-landing-tests-")
        self.addCleanup(self.temp.cleanup)
        self.csv = Path(self.temp.name) / "input.csv"

    def make_csv(self, *, impact_at=100, truth=True, pressure=True):
        headers = ["time_ms", "imu_z_mps2"]
        if pressure:
            headers.append("pressure_pa")
        if truth:
            headers.append("truth_contact")
        lines = [",".join(headers)]
        for i in range(161):
            data = [str(i * 100), "31.0" if i == impact_at else "9.81"]
            if pressure:
                data.append("101000")
            if truth:
                data.append("1" if i >= 100 else "0")
            lines.append(",".join(data))
        self.csv.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_host_detects_at_13s(self):
        self.make_csv()
        result = run_landing_cpp(self.csv, ADAPTER)
        self.assertEqual(result.summary["status"], "成功")
        self.assertAlmostEqual(result.summary["detected_time_s"], 13.0)
        self.assertEqual(result.source_name, "host_adapter.cpp")

    def test_no_impact_not_detected(self):
        self.make_csv(impact_at=-1)
        result = run_landing_cpp(self.csv, ADAPTER)
        self.assertIsNone(result.summary["detected_time_s"])
        self.assertEqual(result.summary["status"], "失敗")

    def test_early_event_is_reported_as_failure(self):
        self.make_csv(impact_at=30)
        result = run_landing_cpp(self.csv, ADAPTER)
        self.assertAlmostEqual(result.summary["detected_time_s"], 6.0)
        self.assertEqual(result.summary["status"], "失敗")

    def test_without_pressure_column(self):
        self.make_csv(pressure=False)
        result = run_landing_cpp(self.csv, ADAPTER)
        self.assertAlmostEqual(result.summary["detected_time_s"], 13.0)

    def test_reset_per_run(self):
        self.make_csv()
        for _ in range(2):
            result = run_landing_cpp(self.csv, ADAPTER)
            self.assertAlmostEqual(result.summary["detected_time_s"], 13.0)

    def test_header_compiles_as_standalone_cpp11(self):
        # Arduino-capable language subset; this is NOT an Arduino board build.
        source = Path(self.temp.name) / "language_test.cpp"
        executable = Path(self.temp.name) / "language_test"
        source.write_text('''
#include "CanSatLandingLogic.h"
int main() {
    CanSatLandingLogic d(LandingLogicConfig(25.0, 500.0));
    if (d.update(100, 9.81, 101325.0)) return 1;
    if (d.update(200, 30.0, 101325.0)) return 2;
    if (!d.update(700, 9.81, 101325.0)) return 3;
    d.reset();
    if (d.update(800, 9.81, 101325.0)) return 4;
    return 0;
}
''', encoding="utf-8")
        subprocess.run(["g++", "-std=c++11", "-Wall", "-Wextra", "-pedantic",
                        "-I", str(SHARED), str(source), "-o", str(executable)],
                       check=True, capture_output=True, timeout=20)
        subprocess.run([str(executable)], check=True, capture_output=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
