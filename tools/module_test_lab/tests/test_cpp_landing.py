"""Offline integration tests: compile a host C++ algorithm and evaluate its CSV output."""
from pathlib import Path
import shutil
import tempfile
import unittest

from cpp_landing_runner import DEMO_SOURCE, read_sensor_csv, run_landing_cpp


@unittest.skipUnless(shutil.which("g++"), "g++ is needed for host-C++ tests")
class CppLandingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv = Path(self.tmp.name) / "sensors.csv"

    def make_csv(self, *, truth=True, early=False, flag=1):
        header = "time_ms,imu_z_mps2,pressure_pa,landing_detected"
        if truth:
            header += ",truth_contact"
        lines = [header]
        for i in range(161):
            ms = i * 100
            acc = 30 if (i == (30 if early else 100)) else 9.81
            columns = [str(ms), str(acc), "101000", str(flag)]
            if truth:
                columns.append("1" if i >= 100 else "0")
            lines.append(",".join(columns))
        self.csv.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_demo_compiles_and_detects_three_seconds_after_impact(self):
        self.make_csv()
        result = run_landing_cpp(self.csv, DEMO_SOURCE)
        self.assertEqual(result.summary["status"], "成功")
        self.assertAlmostEqual(result.summary["detected_time_s"], 13.0)
        self.assertAlmostEqual(result.summary["delay_s"], 3.0)
        self.assertEqual(result.log.rows[0]["landing_detected"], False)
        self.assertEqual(result.log.rows[-1]["landing_detected"], True)
        self.assertEqual(result.summary["log_rows"], 161)
        self.assertEqual(len(result.source_sha256), 64)

    def test_original_landing_detected_ignored(self):
        self.make_csv(flag=1)
        res = run_landing_cpp(self.csv, DEMO_SOURCE)
        self.assertEqual(res.summary["detected_time_s"], 13)
        self.assertFalse(res.summary["starts_detected"])

    def test_early_false_positive_detected(self):
        self.make_csv(early=True)
        res = run_landing_cpp(self.csv, DEMO_SOURCE)
        self.assertEqual(res.summary["status"], "失敗")
        self.assertAlmostEqual(res.summary["delay_s"], -4)

    def test_no_ground_truth_is_undetermined(self):
        self.make_csv(truth=False)
        res = run_landing_cpp(self.csv, DEMO_SOURCE)
        self.assertEqual(res.summary["status"], "未判定")
        self.assertIsNone(res.summary["true_contact_s"])
        res = run_landing_cpp(self.csv, DEMO_SOURCE, manual_truth_s=10)
        self.assertEqual(res.summary["status"], "成功")

    def test_raw_sensor_csv_without_landing_detected(self):
        self.csv.write_text(
            "time_s,imu_z_mps2,pressure_pa,truth_contact\n"
            "0,9.81,101000,0\n10,30.0,101050,1\n"
            "13,9.81,101050,1\n16,9.81,101050,1\n", encoding="utf-8")
        res = run_landing_cpp(self.csv, DEMO_SOURCE)
        self.assertEqual(res.summary["status"], "成功")
        self.assertEqual(res.summary["detected_time_s"], 13)

    def test_invalid_sensor_data_rejected(self):
        bad = (
            "time_ms,imu_z_mps2\n0,9\n0,30\n",
            "time_ms,imu_z_mps2\n0,nan\n",
            "time_ms,pressure_pa\n0,1\n",
            "time_ms,imu_z_mps2,truth_contact\n0,9,what\n",
            "time_ms,imu_z_mps2\n-1,9\n",
        )
        for text in bad:
            with self.subTest(text=text):
                self.csv.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_sensor_csv(self.csv)

    def test_invalid_cpp_compile_error(self):
        self.make_csv()
        bad = Path(self.tmp.name) / "invalid.cpp"
        bad.write_text("this is not C++", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "コンパイル"):
            run_landing_cpp(self.csv, bad)

    def test_reject_non_cpp_source(self):
        self.make_csv()
        bad = Path(self.tmp.name) / "program.ino"
        bad.write_text("void setup() {}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, ".cpp"):
            run_landing_cpp(self.csv, bad)

    def test_no_detection_when_missing_impact(self):
        self.make_csv()
        text = self.csv.read_text().replace(",30,", ",9.81,")
        self.csv.write_text(text)
        res = run_landing_cpp(self.csv, DEMO_SOURCE, allowed_delay_s=5)
        self.assertEqual(res.summary["status"], "失敗")
        self.assertIsNone(res.summary["detected_time_s"])


if __name__ == "__main__":
    unittest.main()
