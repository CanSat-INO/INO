"""v16 journal tests; no Qt, network or hardware needed."""
import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import records
from v16_experiment_core import (
    MODE, MODULES, PHASES, prepare_experiment, save_experiment,
    experiment_records, summary_counts, record_details, export_experiment_csv,
)


def arguments(**kw):
    x = dict(name='IMU 動作試験', module=MODULES[0], phase=PHASES[1],
             tester='A', code_version='test_v01', status='未判定')
    x.update(kw)
    return x


class TestExperimentJournal(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.patches = [
            patch.object(records, 'DATA_DIR', root / 'data'),
            patch.object(records, 'RECORDS_FILE', root / 'data' / 'records.json'),
            patch.object(records, 'ATTACHMENTS_DIR', root / 'data' / 'attachments'),
        ]
        for p in self.patches: p.start()
        self.addCleanup(lambda: [p.stop() for p in self.patches])
        self.csv = root / 'log.csv'
        self.csv.write_text('time_s,ax,gy\n0,1,2\n1,3,4\n', encoding='utf-8')
        self.code = root / 'test.ino'
        self.code.write_text('void setup() {}\nvoid loop() {}\n', encoding='utf-8')

    def test_prepare_no_save(self):
        record, att = prepare_experiment(**arguments(csv_path=self.csv, code_path=self.code))
        self.assertEqual(record['mode'], MODE)
        self.assertEqual(record['metrics']['v16']['log']['rows'], 2)
        self.assertEqual(len(att), 2)
        self.assertEqual(records.load_records(), [])

    def test_save_persists_and_hashes(self):
        saved = save_experiment(**arguments(csv_path=self.csv, code_path=self.code, hardware='BNO055'))
        self.assertEqual(len(saved['attachments']), 2)
        self.assertTrue(all(len(a['sha256']) == 64 for a in saved['attachments']))
        stored = records.load_records()[0]
        self.assertEqual(stored['metrics']['v16']['hardware'], 'BNO055')
        self.assertEqual(experiment_records()[0]['id'], saved['id'])
        for a in saved['attachments']:
            self.assertTrue((records.ATTACHMENTS_DIR / saved['id'] / a['name']).is_file())

    def test_empty_name_rejected(self):
        with self.assertRaisesRegex(ValueError, '実験名'):
            prepare_experiment(**arguments(name='   '))

    def test_enum_validation(self):
        with self.assertRaises(ValueError): prepare_experiment(**arguments(status='合格'))
        with self.assertRaises(ValueError): prepare_experiment(**arguments(phase='未知'))

    def test_invalid_csv_fails_without_writing(self):
        self.csv.write_text('x,y\nabc,def\n', encoding='utf-8')
        with self.assertRaises(ValueError): save_experiment(**arguments(csv_path=self.csv))
        self.assertEqual(records.load_records(), [])

    def test_duplicate_basenames(self):
        other = self.csv.parent / 'nested'; other.mkdir()
        same = other / 'log.csv'; same.write_text('code', encoding='utf-8')
        with self.assertRaises(ValueError): prepare_experiment(**arguments(csv_path=self.csv, code_path=same))

    def test_wrong_code_extension(self):
        with self.assertRaisesRegex(ValueError, '対応していない'):
            prepare_experiment(**arguments(code_path=self.csv))

    def test_filtered_and_counts(self):
        a = save_experiment(**arguments(name='Aの試験', status='成功'))
        b = save_experiment(**arguments(name='Bの試験', status='失敗', module=MODULES[1], phase=PHASES[2]))
        records.add_record(records.new_record(module='着地検知', scenario='他の旧記録'))
        result = experiment_records(search='Aの試験')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['id'], a['id'])
        self.assertEqual([r['id'] for r in experiment_records(module=MODULES[1])], [b['id']])
        self.assertEqual(len(experiment_records()), 2)
        self.assertEqual(summary_counts(experiment_records()), {'total':2, '成功':1, '失敗':1, '未判定':0})

    def test_export_csv_formula_injection_safe(self):
        rec = save_experiment(**arguments(name='=cmd', notes=' =SUM(1,2)'))
        output = self.csv.parent / 'report.csv'
        self.assertEqual(export_experiment_csv([rec], output), 1)
        with output.open(encoding='utf-8-sig', newline='') as f:
            rows = list(csv.reader(f))
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[1][2].startswith("'="))
        self.assertTrue(rows[1][13].startswith("'="))

    def test_metadata_details(self):
        rec = save_experiment(**arguments(code_version='x123', csv_path=self.csv))
        detail = record_details(rec)
        self.assertIn('x123', detail)
        self.assertIn('SHA256', detail)


if __name__ == '__main__':
    unittest.main()
