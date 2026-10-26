"""v7 regression tests (no Qt dependency)."""
import csv
import hashlib
import io
import math
from pathlib import Path
import shutil
import sys
import unittest
from tempfile import TemporaryDirectory

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from landing_optimizer import (
    DEMO_TUNABLE, optimize, parse_values, make_optimization_csv,
    make_optimization_cases_csv,
)
from dashboard_data import read_trace
from records import new_record


class ParseTests(unittest.TestCase):
    def test_parse_valid(self):
        self.assertEqual(parse_values('12, 14.5,18',name='閾値',minimum=1,maximum=100), (12.,14.5,18.))

    def test_parse_invalid(self):
        for txt in ('','NaN','12,,18','18,18','0','101','not number','1,' ):
            with self.subTest(txt=txt),self.assertRaises(ValueError):
                parse_values(txt,name='閾値',minimum=1,maximum=100)

    def test_bad_grid(self):
        with self.assertRaises(ValueError):optimize(DEMO_TUNABLE,(12,)*5,(0,300,700,1000))
        with self.assertRaises(ValueError):optimize(DEMO_TUNABLE,(math.nan,),(300,))

    def test_dashboard_recognizes_v6_summary_as_report(self):
        with TemporaryDirectory() as td:
            root=Path(td); rec=new_record(mode='外部シミュレーション')
            folder=root/rec['id']; folder.mkdir()
            path=folder/'landing_comparison_v6.csv'
            path.write_text('scenario_key,before_status,after_status,comparison\nnormal,失敗,成功,改善\n',encoding='utf-8')
            rec['attachments']=[{'name':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]
            data=read_trace(rec,root)
            self.assertFalse(data['trace'])
            self.assertIn('比較レポート',data['message'])
            self.assertIn('normal',data['report_text'])
            self.assertNotIn('time_s または',data['message'])

    def test_dashboard_recognizes_v7_summary_as_report(self):
        with TemporaryDirectory() as td:
            root=Path(td); rec=new_record(mode='外部シミュレーション')
            folder=root/rec['id']; folder.mkdir()
            path=folder/'landing_optimization_v7.csv'
            path.write_text('impact_threshold_mps2,hold_ms,success,failure,rank\n12,300,5,1,1\n',encoding='utf-8')
            rec['attachments']=[{'name':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}]
            data=read_trace(rec,root)
            self.assertIn('パラメータ',data['message'])
            self.assertIn('12',data['report_text'])


@unittest.skipUnless(shutil.which('g++'),'g++ unavailable')
class CppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.opt=optimize(DEMO_TUNABLE,(12.0,18.0),(0.0,300.0))

    def test_runs_all_8_for_each_candidate(self):
        self.assertEqual(len(self.opt.candidates),4)
        for c in self.opt.candidates:
            self.assertEqual(len(c.outcomes),8)
            self.assertEqual(c.counts['入力エラー'],1)
            self.assertEqual(c.counts['未判定'],1)
            self.assertEqual(c.counts['実行エラー'],0)

    def test_expected_parameter_effect(self):
        by={(c.threshold,c.hold_ms):c for c in self.opt.candidates}
        low=by[(12.0,300.0)]; high=by[(18.0,300.0)]
        self.assertGreater(low.counts['成功'],high.counts['成功'])
        self.assertEqual(self.opt.best.threshold,12.0)

    def test_delay_and_detail(self):
        winner=self.opt.best
        self.assertIsNotNone(winner.mean_delay_s)
        self.assertGreaterEqual(winner.mean_delay_s,0)
        self.assertEqual(len({o.case.key for o in winner.outcomes}),8)

    def test_csv_coverage_and_sha(self):
        rows=list(csv.DictReader(io.StringIO(make_optimization_csv(self.opt))))
        self.assertEqual(len(rows),4)
        self.assertEqual(len(rows[0]['source_sha256']),64)
        details=list(csv.DictReader(io.StringIO(make_optimization_cases_csv(self.opt))))
        self.assertEqual(len(details),32)

    def test_compiles_only_parameterized_code(self):
        from cpp_landing_runner import DEMO_SOURCE
        with self.assertRaises(ValueError) as raised:
            optimize(DEMO_SOURCE,(12.0,),(300.0,))
        self.assertIn('コンパイル',str(raised.exception))

if __name__=='__main__':unittest.main()
