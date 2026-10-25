import csv
import hashlib
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dashboard_data as dash
from landing_sim import make_trace
from records import new_record, store_trace
import records
from unittest.mock import patch


class DashboardDataTests(unittest.TestCase):
    def sample(self, status="成功", mode="仮想参考モデル", **kwargs):
        return new_record(status=status, mode=mode, **kwargs)

    def test_summary_distinguishes_reference_and_real(self):
        cases = [self.sample(), self.sample(status="失敗", mode="Arduino実機試験"),
                 self.sample(status="未判定", mode="外部シミュレーション")]
        s = dash.summary(cases)
        self.assertEqual((s["total"], s["success"], s["failed"], s["undecided"]), (3,1,1,1))
        self.assertEqual(s["success_rate"], 50)
        self.assertEqual((s["reference"], s["non_reference"]), (1,2))

    def test_empty_success_rate(self):
        self.assertIsNone(dash.summary([])["success_rate"])
        self.assertIsNone(dash.summary([self.sample(status="未判定")])["success_rate"])

    def test_filter_and_module_summary(self):
        records = [self.sample(tester="Alice", module="着地検知"),
                   self.sample(status="失敗", mode="Arduino実機試験", tester="Bob", module="着地検知"),
                   self.sample(module="GNSS・姿勢")]
        self.assertEqual(len(dash.filter_records(records, module="着地検知")), 2)
        self.assertEqual(len(dash.filter_records(records, source="参考モデル以外")), 1)
        self.assertEqual(len(dash.filter_records(records, tester="ali")), 1)
        self.assertEqual(len(dash.module_summary(records)), 2)

    def test_invalid_metric_and_point_order(self):
        records = [self.sample(metrics={"delay_s": None}),
                   self.sample(metrics={"delay_s": "NaN"}),
                   self.sample(metrics={"delay_s": 2.2}, created_at="2026-10-25T14:00:00"),
                   self.sample(metrics={"delay_s": 1.2}, created_at="2026-10-25T15:00:00")]
        p = dash.delay_points(records)
        self.assertEqual([x[1] for x in p], [2.2, 1.2])

    def test_virtual_trace_integrity_and_events(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)/"att"
            with patch.object(records, "ATTACHMENTS_DIR", root):
                rec = self.sample(metrics={"true_contact_s":10.0, "detected_time_s":13.0})
                store_trace(rec, make_trace("normal"))
                r = dash.read_trace(rec, root)
                self.assertGreater(len(r["trace"]), 100)
                self.assertEqual(r["contact_time"], 10.0)
                self.assertEqual(r["detected_time"], 13.0)
                self.assertEqual(r["filename"], "virtual_sensor_trace.csv")
                path = root/rec["id"]/"virtual_sensor_trace.csv"
                path.write_text("corrupt", encoding="utf-8")
                self.assertFalse(dash.read_trace(rec, root)["trace"])
                self.assertIn("SHA256", dash.read_trace(rec, root)["message"])

    def test_arduino_milliseconds_and_flag(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)/"att"
            rec = self.sample(mode="Arduino実機試験", metrics={})
            dest = root/rec["id"]/"landing.csv"
            dest.parent.mkdir(parents=True)
            with dest.open("w", encoding="utf-8-sig", newline="") as file:
                writer = csv.writer(file)
                writer.writerow(["time_ms", "imu_z_mps2", "pressure_pa", "landing_detected"])
                writer.writerows([[0, 9.8, 101000, 0], [100, 23, 101002, 0], [250, 9.8, 101003, 1]])
            rec["attachments"]=[{"name": dest.name, "sha256":hashlib.sha256(dest.read_bytes()).hexdigest()}]
            result = dash.read_trace(rec, root)
            self.assertEqual(len(result["trace"]), 3)
            self.assertAlmostEqual(result["detected_time"], .25)
            self.assertIsNone(result["contact_time"])
            self.assertIn("CSV", result["detected_source"])

    def test_missing_attachment_and_unrecognized_data(self):
        rec = self.sample()
        self.assertIn("添付がありません", dash.read_trace(rec)["message"])
        rec["id"]="bad/../../id"
        self.assertIn("不正", dash.read_trace(rec)["message"])


if __name__=="__main__":
    unittest.main()
