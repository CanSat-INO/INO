"""v10 regression: separate trusted C++ sources + virtual module decisions."""
from __future__ import annotations
import csv
import hashlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from module_network import simulate
from module_cpp_individual import (
    ROLES, CASES, IndividualCppError, run_module, run_three_modules,
    combine_modules, ModuleRun,
)
from unified_results import SOURCES, build_result_record, make_event_csv

SAMPLES = Path(__file__).resolve().parent.parent / 'cpp_module'


def samples(cam='example_cam_v10.cpp'):
    return {
        'Main': SAMPLES / 'example_main_v10.cpp',
        'CAM': SAMPLES / cam,
        'Drive': SAMPLES / 'example_drive_v10.cpp',
    }


@unittest.skipUnless(shutil.which('g++'), 'host C++ compiler unavailable')
class ModuleCppExecutionTests(unittest.TestCase):
    def test_main_decisions(self):
        report = run_module('Main', samples()['Main'])
        values = {x.key: x.value for x in report.decisions}
        self.assertEqual(values['main_landing'], 1)
        self.assertEqual(values['main_before_landing'], 0)
        self.assertEqual(values['main_unknown_stop'], -1)

    def test_cam_decisions(self):
        report = run_module('CAM', samples()['CAM'])
        self.assertEqual([x.value for x in report.decisions], [1, -1])

    def test_drive_decisions(self):
        report = run_module('Drive', samples()['Drive'])
        self.assertEqual([x.value for x in report.decisions], [1, 1, -1])

    def test_all_normal(self):
        result = run_three_modules(samples())
        self.assertEqual(result.simulation.evaluation, '成功')
        self.assertEqual(result.simulation.main_state, 'FINISHED')
        self.assertTrue(all(result.cpp_policy.values()))

    def test_cam_reject_is_logged(self):
        result = run_three_modules(samples(cam='example_cam_deny_v10.cpp'))
        self.assertEqual(result.simulation.evaluation, '失敗')
        self.assertTrue(any(x.event == 'C++拒否' for x in result.simulation.events))
        self.assertFalse(result.cpp_policy['cam_capture'])

    def test_communication_drop_distinct_from_cpp_reject(self):
        result = run_three_modules(samples(), 'drop_drive_cmd')
        self.assertEqual(result.simulation.evaluation, '失敗')
        self.assertTrue(result.simulation.loss_count >= 1)
        self.assertFalse(any(x.event == 'C++拒否' for x in result.simulation.events))

    def test_content_hash_is_sha256(self):
        x = run_module('CAM', samples()['CAM'])
        self.assertEqual(x.sha256, hashlib.sha256(Path(x.source).read_bytes()).hexdigest())

    def test_bundle_hash_stable_and_order_sensitive(self):
        a = run_three_modules(samples())
        b = combine_modules(a.modules, 'drop_cam_ack')
        self.assertEqual(a.provenance_sha256, b.provenance_sha256)
        self.assertEqual(len(a.provenance_sha256),64)

    def test_existing_v8_2_simulate_api_untouched(self):
        a = run_three_modules(samples())
        b = simulate('normal', cpp_policy=a.cpp_policy)
        self.assertEqual(a.simulation, b)

    def test_host_compilation_rejects_invalid_cpp(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'bad.cpp'
            src.write_text('int definitely_not_a_controller( {', encoding='utf-8')
            with self.assertRaisesRegex(IndividualCppError, 'コンパイル失敗'):
                run_module('CAM', src)

    def test_host_runner_rejects_stdout_noise(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'noise.cpp'
            src.write_text('#include <iostream>\n'
                           'extern "C" int cansat_allow_command(int,int,int) {'
                           'std::cout << "debug\\n"; return 1; }', encoding='utf-8')
            with self.assertRaisesRegex(IndividualCppError, '不正な出力'):
                run_module('CAM', src)

    def test_host_runner_rejects_non_boolean_known_decision(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'unsupported.cpp'
            src.write_text('extern "C" int cansat_allow_command(int,int,int) {return -1;}',
                           encoding='utf-8')
            choices = samples()
            choices['CAM'] = src
            with self.assertRaisesRegex(IndividualCppError,'既知のC\\+\\+判断'):
                run_three_modules(choices)

    def test_before_landing_warning_flag(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'unsafe_main.cpp'
            src.write_text('extern "C" int cansat_allow_command(int m,int c,int l) {'
                           '(void)l; return m==1 && c==1 ? 1 : -1; }',encoding='utf-8')
            x = run_module('Main', src)
            self.assertEqual(x.decisions[1].safety_check,'要確認')


class ValidationTests(unittest.TestCase):
    def test_unknown_module(self):
        with self.assertRaises(ValueError):
            run_module('GPS', __file__)

    def test_missing_source(self):
        with self.assertRaisesRegex(IndividualCppError, '存在する'):
            run_module('CAM', '/path/that/does/not/exist.cpp')

    def test_missing_module_in_bundle(self):
        with self.assertRaises(ValueError):
            run_three_modules({'Main': 'a.cpp'})

    def test_wrong_sequence_rejected(self):
        fake = ModuleRun('Drive','drive.cpp','a'*64,(), '')
        with self.assertRaises(ValueError):
            combine_modules((fake,fake,fake))

    def test_no_compiler(self):
        with patch('module_cpp_individual.shutil.which', return_value=None):
            with self.assertRaisesRegex(IndividualCppError,'g\\+\\+'):
                run_module('CAM', samples()['CAM'])

    def test_source_kind_available_in_v9(self):
        self.assertIn('cpp_individual', SOURCES)

    @unittest.skipUnless(shutil.which('g++'), 'host C++ compiler unavailable')
    def test_v9_record_contains_three_sources(self):
        bundle = run_three_modules(samples())
        record, csv_data = build_result_record(
            bundle.simulation, source_kind='cpp_individual',
            cpp_sha256=bundle.provenance_sha256,
            cpp_source='main_cam_drive_host_cpp', notes=bundle.source_notes)
        self.assertIn('Main:', record['notes'])
        self.assertIn('CAM:', record['notes'])
        self.assertIn('Drive:', record['notes'])
        self.assertNotIn(str(Path.home()), record['notes'])
        self.assertEqual(len(list(csv.DictReader(io.StringIO(csv_data)))),len(bundle.simulation.events))


if __name__ == '__main__':
    unittest.main()
