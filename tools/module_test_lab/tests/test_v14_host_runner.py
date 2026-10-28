"""v14 standalone regression (no Qt required)."""
from __future__ import annotations
import csv
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from v14_host_runner import (EXAMPLE, DEFAULT_CASES, HostValidationError,
                             load_cases, run_host_suite, export_report, as_dict)


class TestHostCppV14(unittest.TestCase):
    def test_sample_cases_parse(self):
        cases = load_cases(DEFAULT_CASES)
        self.assertEqual(10, len(cases))
        self.assertEqual(10, len(set(x.case_id for x in cases)))

    @unittest.skipUnless(shutil.which('g++'), 'g++ absent')
    def test_example_compiles_and_passes(self):
        run = run_host_suite(EXAMPLE, DEFAULT_CASES)
        self.assertEqual('PASS', run.status)
        self.assertEqual(10, run.passed)
        self.assertEqual(10, len(run.results))
        self.assertEqual(64, len(run.manifest_sha256))
        self.assertTrue(any(p.endswith('portable_decision.h') for p, _ in run.dependencies))
        with tempfile.TemporaryDirectory() as d:
            for suffix in ('.json', '.csv'):
                output = export_report(run, pathlib.Path(d) / ('check' + suffix))
                self.assertTrue(output.exists())
                if suffix == '.json':
                    data = json.loads(output.read_text())
                    self.assertEqual('host decision logic only; not Arduino firmware, ESP32 or hardware verification', data['scope'])
                    self.assertEqual(10, len(data['cases']))
                else:
                    with output.open(encoding='utf-8-sig', newline='') as stream:
                        self.assertEqual(10, len(list(csv.DictReader(stream))))

    @unittest.skipUnless(shutil.which('g++'), 'g++ absent')
    def test_detects_failing_expectation(self):
        with tempfile.TemporaryDirectory() as d:
            cases = pathlib.Path(d) / 'cases.csv'
            text = DEFAULT_CASES.read_text().replace('main_airborne,1,1,0,0', 'main_airborne,1,1,0,1')
            cases.write_text(text)
            run = run_host_suite(EXAMPLE, cases)
            self.assertEqual('FAIL', run.status)
            self.assertEqual(9, run.passed)
            self.assertFalse(run.results[1].passed)

    def test_refuses_sketch_file(self):
        with tempfile.TemporaryDirectory() as d:
            source = pathlib.Path(d) / 'project.ino'
            source.write_text('void setup(){}')
            with self.assertRaisesRegex(HostValidationError, r'\.ino'):
                run_host_suite(source, DEFAULT_CASES)

    def test_invalid_csv(self):
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'cases.csv'
            for data in ('case_id,module,command,landed,expected\n',
                         'case_id,module,command,landed,expected\ntest,4,1,0,0\n',
                         'case_id,module,command,landed,expected\n=cmd,1,1,1,1\n',
                         'case_id,module,command,landed,expected\na,1,1,1,1\na,1,1,1,1\n'):
                path.write_text(data)
                with self.assertRaises(HostValidationError):
                    load_cases(path)

    @unittest.skipUnless(shutil.which('g++'), 'g++ absent')
    def test_bad_cpp_reports_compile_failure(self):
        with tempfile.TemporaryDirectory() as d:
            cpp = pathlib.Path(d) / 'bad.cpp'
            cpp.write_text('no such cpp token ;')
            with self.assertRaisesRegex(HostValidationError, 'コンパイル失敗'):
                run_host_suite(cpp, DEFAULT_CASES)

    @unittest.skipUnless(shutil.which('g++'), 'g++ absent')
    def test_invalid_native_stdout_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            cpp = pathlib.Path(d) / 'bad_output.cpp'
            cpp.write_text('#include <iostream>\nextern "C" int cansat_allow_command(int,int,int) { std::cout << "hi\\n"; return 1; }\n')
            with self.assertRaisesRegex(HostValidationError, r'不正なC\+\+出力'):
                run_host_suite(cpp, DEFAULT_CASES)

    def test_gui_launch_and_ime_unchanged(self):
        app = (ROOT / 'app.py').read_text(encoding='utf8')
        self.assertIn('from v14_host_tab import HostCppV14Tab', app)
        self.assertIn('self.build_v14_host_tab()', app)
        self.assertIn('self.build_individual_cpp_tab()', app)
        self.assertIn('self.build_experiment_management_tab()', app)
        self.assertNotIn('IBUS_USE_PORTAL=', app)

if __name__ == '__main__':
    unittest.main()
