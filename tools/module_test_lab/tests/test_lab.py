import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from landing_sim import make_trace, reference_detect, Config
import records


class LandingTests(unittest.TestCase):
    def test_normal(self):
        out = reference_detect(make_trace('normal'), Config())
        self.assertTrue(out['passed'])
        self.assertGreaterEqual(out['detected_time_s'], 10.0)

    def test_shock_does_not_trigger_prematurely(self):
        out = reference_detect(make_trace('false_shock'), Config())
        self.assertTrue(out['passed'])
        self.assertGreaterEqual(out['detected_time_s'], 10.0)

    def test_soft_failure_case(self):
        out = reference_detect(make_trace('soft'), Config())
        self.assertFalse(out['passed'])


class LedgerTests(unittest.TestCase):
    def test_roundtrip_zip_and_dedup(self):
        with TemporaryDirectory() as temp:
            tmp = Path(temp)
            data = tmp / 'database'
            with patch.object(records, 'DATA_DIR', data), \
                 patch.object(records, 'RECORDS_FILE', data / 'records.json'), \
                 patch.object(records, 'ATTACHMENTS_DIR', data / 'attachments'):
                rec = records.new_record(tester='A', scenario='通常着地')
                records.store_trace(rec, make_trace('normal'))
                records.add_record(rec)
                out = tmp / 'share.zip'
                self.assertEqual(records.export_bundle([rec['id']], out), 1)
                second = records.import_bundle(out)
                self.assertEqual(second['added'], 0)
                self.assertEqual(second['skipped'], 1)
                records.save_records([])
                # Simulate receiving bundle into a separate ledger.
                for f in (data/'attachments'/rec['id']).glob('*'):
                    f.unlink()
                imported = records.import_bundle(out)
                self.assertEqual(imported['added'], 1)
                self.assertEqual(len(records.load_records()), 1)
                self.assertTrue((data/'attachments'/rec['id']/'virtual_sensor_trace.csv').exists())


if __name__ == '__main__':
    unittest.main()
