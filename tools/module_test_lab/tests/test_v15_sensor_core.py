"""v15 sensor CSV parser and summary, independent of Qt."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v15_sensor_core import read_sensor_csv, quality_report, stats_for, summary_dict, export_summary
from navigation_search_v13_5 import matches_search


class SensorCSVTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'log.csv'

    def write(self, contents, encoding='utf-8'):
        self.path.write_text(contents, encoding=encoding)
        return read_sensor_csv(self.path)

    def test_all_sample_types_load(self):
        samples = Path(__file__).resolve().parents[1] / 'v15_samples'
        for f in samples.glob('*.csv'):
            with self.subTest(f=f.name):
                log = read_sensor_csv(f)
                self.assertGreater(log.row_count, 50)
                self.assertTrue(log.signals)
                self.assertEqual(len(log.source_sha256), 64)
                self.assertEqual(len(log.times), log.row_count)
                self.assertEqual(len(stats_for(log)), len(log.signals))
        self.assertEqual(len(list(samples.glob('*.csv'))), 5)

    def test_time_conversion_and_canonical_names(self):
        log = self.write('time_ms,ax,gyro_z_dps\n1000,1,2\n1100,2,3\n1200,3,4\n')
        self.assertAlmostEqual(log.times[1], .1)
        self.assertIn('accel_x_mps2', log.signals)
        self.assertEqual(stats_for(log)[0].mean, 2)

    def test_sample_index_no_time(self):
        log = self.write('ax,notes\n1,start\n2,next\n')
        self.assertEqual(log.time_kind, 'sample')
        self.assertEqual(log.times, (0., 1.))
        self.assertIn('サンプル番号', quality_report(log)[0])

    def test_iso_time(self):
        log = self.write('datetime,temp_c\n2026-10-27T14:00:00+09:00,21\n2026-10-27T14:00:02+09:00,22\n')
        self.assertEqual(log.times, (0., 2.))

    def test_missing_and_range_notes(self):
        log = self.write('time_s,latitude_deg,red_ratio\n0,35.0,0.3\n1,,0.5\n2,95.0,1.2\n')
        self.assertEqual(stats_for(log)[0].missing, 1)
        notes = quality_report(log)
        self.assertTrue(any('欠損' in x for x in notes))
        self.assertTrue(any('latitude_deg' in x for x in notes))
        self.assertTrue(any('red_ratio' in x for x in notes))

    def test_time_reversal_gap_duplicates(self):
        log = self.write('time_s,ax\n0,1\n1,2\n2,3\n12,4\n12,5\n11,6\n13,7\n')
        notes = quality_report(log)
        self.assertTrue(any('重複' in n for n in notes))
        self.assertTrue(any('逆行' in n for n in notes))
        self.assertTrue(any('測定間隔' in n for n in notes))

    def test_cp932(self):
        log = self.write('時間ms,温度\n0,24\n250,25\n', encoding='cp932')
        self.assertEqual(log.encoding, 'cp932')
        self.assertEqual(log.times, (0., .25))
        self.assertIn('temperature_c', log.signals)

    def test_bad_data_rejected(self):
        for bad in [
            'time_s,ax\n0,abc\n',
            'time_s,ax\n0,inf\n',
            'time_s,ax\n0,2,3\n',
            'time_s,time_ms,ax\n0,0,1\n',
            'time_s,ax,AX\n0,1,2\n',
            'time_s,ax,accel_x_mps2\n0,1,2\n',
            'time_s,comment\n0,OK\n',
            'time_s,ax\n,1\n',
        ]:
            with self.subTest(bad=bad):
                self.path.write_text(bad, encoding='utf-8')
                with self.assertRaises(ValueError):
                    read_sensor_csv(self.path)

    def test_too_large_file(self):
        with self.path.open('wb') as fd:
            fd.truncate(12 * 1024 * 1024 + 1)
        with self.assertRaisesRegex(ValueError, '上限'):
            read_sensor_csv(self.path)

    def test_unknown_numeric_column(self):
        log = self.write('time_s,independent_unknown,phase\n0,4,landing\n1,6,drive\n')
        self.assertEqual(log.signals['independent_unknown'], (4., 6.))
        self.assertNotIn('phase', log.signals)

    def test_report_csv_json(self):
        log = self.write('time_s,ax\n0,1\n1,2\n')
        report = summary_dict(log)
        self.assertEqual(report['rows'], 2)
        target = Path(self.temp.name) / 'summary.json'
        export_summary(log, target)
        self.assertEqual(json.loads(target.read_text())['schema'], 'cansat-sensor-summary-v15')
        target2 = Path(self.temp.name) / 'summary.csv'
        export_summary(log, target2)
        with target2.open(encoding='utf-8-sig', newline='') as file:
            rows = list(csv.DictReader(file))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['count'], '2')
        with self.assertRaises(ValueError):
            export_summary(log, Path(self.temp.name) / 'data.exe')

    def test_navigation_keywords(self):
        name = 'センサー実験・ログ解析'
        for term in ('GPS', 'GNSS', 'BNO055', 'IMU', '気圧', 'モーター', 'CAM', 'CSV', 'センサー'):
            with self.subTest(term=term):
                self.assertTrue(matches_search(name, '共通基盤', term))


if __name__ == '__main__':
    unittest.main()
