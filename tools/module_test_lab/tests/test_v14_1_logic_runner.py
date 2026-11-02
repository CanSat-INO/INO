"""v14.1 unit + portable native host smoke tests."""
import csv
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from v14_1_logic_runner import (
    SPECS, ModuleValidationError, examples_for, load_module_cases,
    run_module_suite, export_module_report, report_dict,
)


class ModuleRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler_ok = bool(shutil.which('g++'))

    def test_each_example_csv_loads(self):
        for module in SPECS:
            with self.subTest(module=module):
                _, csv_path = examples_for(module)
                cases = load_module_cases(module, csv_path)
                self.assertEqual(len(cases), 8)

    def test_samples_compile_and_pass(self):
        if not self.compiler_ok:
            self.skipTest('g++ required for C++ tests')
        for module in SPECS:
            with self.subTest(module=module):
                source, csv_path = examples_for(module)
                report = run_module_suite(module, source, csv_path)
                self.assertEqual((report.passed, len(report.results), report.status), (8, 8, 'PASS'))
                self.assertEqual(len(report.manifest_sha256), 64)
                self.assertGreaterEqual(len(report.dependencies), 4)

    def test_fail_is_reported_not_crashed(self):
        if not self.compiler_ok:
            self.skipTest('g++ required')
        source, orig_cases = examples_for('landing')
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / 'cases.csv'
            rows = orig_cases.read_text().splitlines()
            rows[1] = rows[1].rsplit(',', 1)[0] + ',0'
            csv_path.write_text('\n'.join(rows) + '\n')
            report = run_module_suite('landing', source, csv_path)
            self.assertEqual((report.passed, report.status), (7, 'FAIL'))
            self.assertEqual(sum(not r.passed for r in report.results), 1)
            target = Path(directory) / 'test.json'
            export_module_report(report, target)
            self.assertIn('"status": "FAIL"', target.read_text())
            export_module_report(report, Path(directory) / 'test.csv')

    def test_csv_is_strict(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.csv'
            for content in (
                'case_id,accel_mps2,gyro_dps,stable_ms,expected\na,NaN,0,600,1\n',
                'case_id,accel_mps2,gyro_dps,stable_ms,expected\na,10,0.5,600,2\n',
                'case_id,accel_mps2,gyro_dps,stable_ms,expected\na,10,0.5,600,0\na,10,0.5,600,1\n',
                'case_id,accel_mps2,gyro_dps,stable_ms,expected\na,10,0.5,600.5,0\n',
                'case_id,accel_mps2,gyro_dps,stable_ms,expected\n=x,10,0.5,600,0\n',
                'case_id,accel_mps2,gyro_dps,stable_ms,expected\na,-1,0.5,600,0\n',
                'case_id,accel_mps2,gyro_dps,stable_ms,expected\na,10,0.5,600,0,extra\n',
            ):
                with self.subTest(content=content):
                    path.write_text(content, encoding='utf-8')
                    with self.assertRaises(ModuleValidationError):
                        load_module_cases('landing', path)

    def test_missing_module(self):
        with self.assertRaises(ModuleValidationError):
            examples_for('invalid')

    def test_unsupported_extension(self):
        if not self.compiler_ok:
            self.skipTest('g++ required')
        source, cases = examples_for('cam')
        with self.assertRaises(ModuleValidationError):
            run_module_suite('cam', source.with_suffix('.ino'), cases)

    def test_report_columns(self):
        if not self.compiler_ok:
            self.skipTest('g++ required')
        source, cases = examples_for('drive')
        report = run_module_suite('drive', source, cases)
        dictionary = report_dict(report)
        self.assertEqual(dictionary['module'], 'drive')
        self.assertIn('command', dictionary['results'][0])
        with tempfile.TemporaryDirectory() as directory:
            outfile = Path(directory) / 'output.csv'
            export_module_report(report, outfile)
            with outfile.open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 8)
            self.assertEqual(rows[1]['result'], 'PASS')
            with self.assertRaises(ModuleValidationError):
                export_module_report(report, Path(directory) / 'bad.txt')


if __name__ == '__main__':
    unittest.main()
