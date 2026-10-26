"""v6 regression tests: status transitions, evidence, deterministic comparison and CSV."""
from __future__ import annotations

import csv
import io
from pathlib import Path
import shutil
import unittest

from cpp_landing_runner import DEMO_SOURCE
from landing_batch import BatchOutcome, CASES_BY_KEY
from landing_compare import compare_sources, diagnose, make_comparison_csv, _change, _excel_safe

DEMO_V2=DEMO_SOURCE.with_name('example_detector_v2.cpp')


class PureCompareTests(unittest.TestCase):
    def dummy(self, status):
        return BatchOutcome(CASES_BY_KEY['normal'],'',None,status,'sample')

    def test_only_definite_success_fail_changes_count(self):
        self.assertEqual(_change(self.dummy('失敗'),self.dummy('成功')),'改善')
        self.assertEqual(_change(self.dummy('成功'),self.dummy('失敗')),'悪化')
        self.assertEqual(_change(self.dummy('失敗'),self.dummy('失敗')),'同判定')
        for status in ('入力エラー','実行エラー','未判定'):
            self.assertEqual(_change(self.dummy('成功'),self.dummy(status)),'比較対象外')
            self.assertEqual(_change(self.dummy(status),self.dummy('失敗')),'比較対象外')

    def test_error_diagnosis_does_not_claim_algorithm_fault(self):
        d=diagnose(self.dummy('入力エラー'),5)
        self.assertIn('C++は実行されていません',d.as_text())
        self.assertIn('入力CSV',d.as_text())

    def test_csv_formula_safety(self):
        for v in ('=1+2','+SUM(A1)',' -1','@cmd','\t=SUM(A2)'):
            self.assertTrue(_excel_safe(v).startswith("'"))
        self.assertEqual(_excel_safe('normal'),'normal')

    def test_reject_bad_parameters(self):
        for t in (-1.0,601.0,float('nan')):
            with self.assertRaises(ValueError):
                compare_sources(DEMO_SOURCE,DEMO_V2,allowed_delay_s=t)


@unittest.skipUnless(shutil.which('g++'),'g++ required')
class CppCompareTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.comp=compare_sources(DEMO_SOURCE,DEMO_V2)

    def test_all_eight_same_order_and_generated_inputs(self):
        self.assertEqual(len(self.comp.cases),8)
        for c in self.comp.cases:
            self.assertEqual(c.before.input_csv,c.after.input_csv)
        self.assertEqual(self.comp.before.counts['成功'],2)
        self.assertEqual(self.comp.after.counts['成功'],5)

    def test_early_shock_and_gentle_improve(self):
        items={c.key:c for c in self.comp.cases}
        for key in ('early_shock','gentle','delayed_impact'):
            self.assertEqual(items[key].change,'改善')
            self.assertEqual(items[key].before.status,'失敗')
            self.assertEqual(items[key].after.status,'成功')
        self.assertEqual(items['invalid_imu'].change,'比較対象外')
        self.assertEqual(items['no_truth'].change,'比較対象外')
        self.assertEqual(self.comp.changes['悪化'],0)

    def test_evidence_based_diagnostics(self):
        c=next(c for c in self.comp.cases if c.key=='early_shock')
        d=diagnose(c.before,5)
        self.assertIn('接地前の誤検知',d.as_text())
        self.assertIn('直接の原因とは限りません',d.as_text())
        success=diagnose(c.after,5)
        self.assertIn('許容範囲内',success.as_text())

    def test_summary_csv_and_code_sha(self):
        lines=list(csv.DictReader(io.StringIO(make_comparison_csv(self.comp))))
        self.assertEqual(len(lines),8)
        self.assertEqual(lines[0]['scenario_key'],'normal')
        self.assertEqual(len(lines[0]['before_sha256']),64)
        self.assertEqual(lines[2]['comparison'],'改善')
        self.assertEqual(lines[7]['comparison'],'比較対象外')

    def test_summary_covers_all_cases(self):
        self.assertIn('改善3',self.comp.summary_text())
        self.assertIn('悪化0',self.comp.summary_text())


if __name__=='__main__':
    unittest.main()
