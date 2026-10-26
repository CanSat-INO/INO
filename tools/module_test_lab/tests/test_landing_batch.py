"""Offline batch scenario tests. No GitHub writes or ledger changes."""
from pathlib import Path
import csv
import io
import shutil
import tempfile
import unittest

from cpp_landing_runner import read_sensor_csv, DEMO_SOURCE
from landing_batch import CASES, make_case_csv, run_batch, make_summary_csv


class LandingBatchPureTests(unittest.TestCase):
    def test_all_eight_cases_exist(self):
        self.assertEqual(len(CASES), 8)
        self.assertEqual(len({s.key for s in CASES}), 8)

    def test_determinism(self):
        self.assertEqual(make_case_csv('noise'), make_case_csv('noise'))
        self.assertNotEqual(make_case_csv('normal'), make_case_csv('noise'))

    def test_contact_truth_and_early_shock(self):
        text = make_case_csv('early_shock')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.csv';p.write_text(text)
            data=read_sensor_csv(p)
            self.assertEqual(data.true_contact_s,10.0)
            self.assertGreater(data.rows[50]['imu_z_mps2'],30)
            self.assertGreater(data.rows[100]['imu_z_mps2'],30)

    def test_missing_truth_remains_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.csv';p.write_text(make_case_csv('no_truth'))
            data=read_sensor_csv(p)
            self.assertIsNone(data.true_contact_s)

    def test_invalid_imu_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.csv';p.write_text(make_case_csv('invalid_imu'))
            with self.assertRaises(ValueError):
                read_sensor_csv(p)

    def test_dropout_removes_a_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.csv';p.write_text(make_case_csv('dropout'))
            data=read_sensor_csv(p)
            self.assertEqual(len(data.rows),160)
            self.assertNotIn(10000,{x['time_ms'] for x in data.rows})

    def test_rejects_bad_parameters(self):
        for value in (-1.0, float('nan'), float('inf'), 601.0):
            with self.assertRaises(ValueError):
                run_batch(DEMO_SOURCE, allowed_delay_s=value)
        with self.assertRaises(ValueError):
            make_case_csv('not_a_case')
        with self.assertRaises(ValueError):
            run_batch(DEMO_SOURCE,case_keys=('normal','normal'))
        with self.assertRaises(ValueError):
            run_batch(DEMO_SOURCE,case_keys=())
        with self.assertRaises(ValueError):
            run_batch('/tmp/fake.ino')


@unittest.skipUnless(shutil.which('g++'), 'g++ is required')
class LandingBatchCppTests(unittest.TestCase):
    def test_detected_normal_and_precontact_failure(self):
        report=run_batch(DEMO_SOURCE,case_keys=('normal','early_shock','gentle','no_truth','invalid_imu'))
        self.assertEqual([r.status for r in report.outcomes],
                         ['成功','失敗','失敗','未判定','入力エラー'])
        self.assertAlmostEqual(report.outcomes[0].summary['detected_time_s'],13.0)
        self.assertAlmostEqual(report.outcomes[1].summary['detected_time_s'],8.0)
        self.assertIsNone(report.outcomes[2].summary['detected_time_s'])
        self.assertEqual(report.counts['入力エラー'],1)

    def test_summary_csv_readable_and_per_case(self):
        report=run_batch(DEMO_SOURCE,case_keys=('normal','invalid_imu'))
        rows=list(csv.DictReader(io.StringIO(make_summary_csv(report))))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['scenario_key'],'normal')
        self.assertEqual(rows[1]['status'],'入力エラー')

if __name__ == '__main__':
    unittest.main()
