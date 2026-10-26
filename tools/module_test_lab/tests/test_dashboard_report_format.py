"""Regression tests for display-only report sorting and floating point formatting."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard_report_v7 import parse_report_csv


class ReportFormatTests(unittest.TestCase):
    def test_v7_sorted_by_rank_and_delay_rounded(self):
        raw = ('impact_threshold_mps2,hold_ms,success,failure,rank,'
               'early_false_detections,mean_success_delay_s\n'
               '12.0,300.0,5,1,3,0,0.9800000000000001\n'
               '12.0,0.0,5,1,1,0,0.6799999999999999\n'
               '14.0,0.0,5,1,2,0,0.9800000000000001\n')
        out = parse_report_csv(raw.encode(), 'landing_optimization_v7.csv')
        lines = out['report_text'].splitlines()
        data = [x for x in lines if ' | ' in x and x[0].isdigit()]
        self.assertEqual(len(data), 3)
        self.assertTrue(data[0].startswith('1 | 12 | 0 | 5 | 1 | 0 | 0.68'))
        self.assertTrue(data[1].startswith('2 | 14 | 0 | 5 | 1 | 0 | 0.98'))
        self.assertTrue(data[2].startswith('3 | 12 | 300 | 5 | 1 | 0 | 0.98'))
        self.assertNotIn('0.6799999999999999', out['report_text'])

    def test_v6_still_supported(self):
        raw = b'scenario_key,before_status,after_status,comparison,before_delay_s\nnormal,fail,pass,better,0.9999999999999\n'
        out = parse_report_csv(raw, 'landing_comparison_v6.csv')
        self.assertIn('v6 C++', out['report_text'])
        self.assertIn('normal', out['report_text'])
        self.assertIn('1.00', out['report_text'])

    def test_v7_cases_preserve_input_order(self):
        raw = ('impact_threshold_mps2,hold_ms,scenario_key,status,delay_s\n'
               '12,300,second,成功,0.10000000000000001\n'
               '12,300,first,成功,0.25\n')
        out = parse_report_csv(raw.encode(), 'landing_optimization_cases_v7.csv')
        self.assertLess(out['report_text'].index('second'), out['report_text'].index('first'))
        self.assertIn('0.10', out['report_text'])

    def test_other_csv_untouched(self):
        raw = b'time_ms,imu_z_mps2\n0,9.8\n'
        self.assertIsNone(parse_report_csv(raw, 'sensor.csv'))


if __name__ == '__main__':
    unittest.main()
