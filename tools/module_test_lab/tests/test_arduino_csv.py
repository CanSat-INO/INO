"""Offline parsing and decision tests. Runs without Qt or real hardware."""
import math
import tempfile
import unittest
from pathlib import Path

from arduino_csv import MAX_CSV_BYTES, analyze, parse_csv_text, read_csv


def sample(flags=(0, 0, 1, 1), truths=(0, 1, 1, 1)):
    return ("time_ms,imu_z_mps2,pressure_pa,landing_detected,truth_contact\n" +
            "\n".join(f"{i*1000},9.81,101000,{f},{t}"
                      for i, (f, t) in enumerate(zip(flags, truths))) + "\n")


class ArduinoCsvTests(unittest.TestCase):
    def test_success_with_truth_column(self):
        log = parse_csv_text(sample())
        self.assertEqual(log.truth_time_s, 1.0)
        self.assertEqual(log.detected_time_s, 2.0)
        res = analyze(log, allowed_delay_s=2.0)
        self.assertEqual(res["status"], "成功")
        self.assertEqual(res["delay_s"], 1.0)

    def test_early_false_positive(self):
        log = parse_csv_text(sample(flags=(0, 1, 1, 1), truths=(0, 0, 1, 1)))
        self.assertEqual(analyze(log)["status"], "失敗")
        self.assertLess(analyze(log)["delay_s"], 0)

    def test_late_dectection(self):
        self.assertEqual(analyze(parse_csv_text(sample()), allowed_delay_s=0.5)["status"], "失敗")

    def test_no_detection_with_sufficient_observation(self):
        log = parse_csv_text(sample(flags=(0, 0, 0, 0)))
        self.assertEqual(analyze(log, allowed_delay_s=2.0)["status"], "失敗")

    def test_no_detection_with_short_record_is_undetermined(self):
        log = parse_csv_text(sample(flags=(0, 0, 0, 0)))
        self.assertEqual(analyze(log, allowed_delay_s=3.0)["status"], "未判定")

    def test_no_truth_is_undetermined(self):
        log = parse_csv_text("time_ms,landing_detected\n0,0\n1000,1\n")
        self.assertEqual(analyze(log)["status"], "未判定")
        self.assertIsNone(analyze(log)["true_contact_s"])

    def test_manual_truth_override(self):
        log = parse_csv_text("time_ms,landing_detected\n0,0\n1000,0\n2000,1\n")
        self.assertEqual(analyze(log, expected_time_s=1.0)["status"], "成功")

    def test_missing_required_column(self):
        with self.assertRaisesRegex(ValueError, "landing_detected"):
            parse_csv_text("time_ms,imu_z_mps2\n1,12\n")

    def test_bad_timestamps(self):
        for value in ("0", "-1", "NaN"):
            data = f"time_ms,landing_detected\n0,0\n{value},1\n"
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_csv_text(data)

    def test_invalid_flag(self):
        with self.assertRaises(ValueError):
            parse_csv_text("time_ms,landing_detected\n0,maybe\n")

    def test_first_row_already_detected(self):
        log = parse_csv_text("time_ms,landing_detected,truth_contact\n0,1,0\n1000,1,1\n")
        self.assertTrue(log.starts_detected)
        self.assertEqual(analyze(log)["status"], "未判定")

    def test_extra_events(self):
        log = parse_csv_text("time_ms,landing_detected,truth_contact\n0,0,0\n1000,1,1\n2000,0,1\n3000,1,1\n")
        self.assertEqual(analyze(log)["extra_detection_events"], 1)

    def test_utf8_bom_file(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "sample.csv"
            file.write_text(sample(), encoding="utf-8-sig")
            self.assertEqual(read_csv(file).detected_time_s, 2.0)

    def test_extra_columns_not_accepted(self):
        with self.assertRaises(ValueError):
            parse_csv_text("time_ms,landing_detected\n0,0,extra\n")

    def test_invalid_tolerance(self):
        log = parse_csv_text(sample())
        with self.assertRaises(ValueError):
            analyze(log, allowed_delay_s=math.nan)

    def test_oversized_text(self):
        with self.assertRaises(ValueError):
            parse_csv_text(" " * (MAX_CSV_BYTES + 1))


if __name__ == "__main__":
    unittest.main()
