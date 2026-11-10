"""v8.2 bridge + logical virtual bus integration tests."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from cpp_module_bridge import run_cpp_decisions, CppModuleError, CPP_DIR
from module_network import SCENARIOS, simulate

SAMPLE = CPP_DIR / 'example_module_controller.cpp'
REJECT_CAM = CPP_DIR / 'example_reject_cam.cpp'


class ModuleCppBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.allow = run_cpp_decisions(SAMPLE).decisions
        cls.reject_cam = run_cpp_decisions(REJECT_CAM).decisions

    def test_sample_allows(self):
        self.assertEqual(len(self.allow), 4)
        self.assertTrue(all(self.allow.values()))

    def test_reject_cam_is_specific(self):
        self.assertFalse(self.reject_cam['cam_capture'])
        self.assertTrue(self.reject_cam['drive_stop'])
        self.assertTrue(self.reject_cam['drive_move'])

    def test_normal_with_cpp_completes(self):
        r = simulate('normal', cpp_policy=self.allow)
        self.assertEqual((r.evaluation, r.main_state), ('成功', 'FINISHED'))
        self.assertEqual((r.cam_state, r.drive_state), ('DONE', 'STOPPED'))

    def test_all_previous_scenarios_still_execute(self):
        for scenario in SCENARIOS:
            r = simulate(scenario.key, cpp_policy=self.allow)
            self.assertEqual(r.scenario.key, scenario.key)

    def test_reject_cam_is_cpp_origin(self):
        r = simulate('normal', cpp_policy=self.reject_cam)
        self.assertEqual((r.evaluation, r.main_state), ('失敗', 'FAULT'))
        self.assertTrue(any(e.event == 'C++拒否' and e.source == 'CAM' for e in r.events))
        self.assertEqual(r.loss_count, 0)
        self.assertEqual(r.timeout_count, 0)

    def test_comms_drop_is_not_cpp_rejection(self):
        r = simulate('drop_drive_cmd', cpp_policy=self.allow)
        self.assertEqual(r.loss_count, 1)
        self.assertEqual(r.timeout_count, 1)
        self.assertFalse(any(e.event == 'C++拒否' for e in r.events))

    def test_main_blocks_move(self):
        gate = dict(self.allow, main_landing=False)
        r = simulate('normal', cpp_policy=gate)
        self.assertEqual(r.main_state, 'BLOCKED')
        self.assertTrue(any(e.event == 'C++拒否' and e.source == 'Main' for e in r.events))
        self.assertFalse(any(e.event == '送信' and e.message.startswith('MOVE') for e in r.events))

    def test_drive_rejects_move(self):
        gate = dict(self.allow, drive_move=False)
        r = simulate('normal', cpp_policy=gate)
        self.assertEqual(r.evaluation, '失敗')
        self.assertTrue(any(e.event == 'C++拒否' and e.source == 'Drive' for e in r.events))
        self.assertEqual(r.drive_state, 'STOPPED')

    def test_drive_rejects_stop(self):
        gate = dict(self.allow, drive_stop=False)
        r = simulate('normal', cpp_policy=gate)
        self.assertEqual(r.evaluation, '失敗')
        self.assertEqual(r.drive_state, 'MOVING')
        self.assertTrue(any(e.event == 'C++拒否' for e in r.events))

    def test_no_landing_does_not_move(self):
        r = simulate('no_landing', cpp_policy=self.allow)
        self.assertEqual(r.evaluation, '未判定')
        self.assertFalse(any(e.message.startswith('MOVE') for e in r.events))

    def test_old_api_unmodified(self):
        self.assertEqual(simulate('normal'), simulate('normal'))

    def test_invalid_policy_rejected(self):
        with self.assertRaises(ValueError):
            simulate('normal', cpp_policy={'main_landing': 1})

    def test_missing_cpp(self):
        with self.assertRaises(CppModuleError):
            run_cpp_decisions('/nonexistent/controller.cpp')

    def test_broken_cpp_compilation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.cpp'
            p.write_text('this is not C++', encoding='utf-8')
            with self.assertRaisesRegex(CppModuleError, 'コンパイル失敗'):
                run_cpp_decisions(p)

    def test_invalid_stdout_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad_output.cpp'
            p.write_text('''#include <iostream>
extern "C" int cansat_allow_command(int, int, int) {
 std::cout << "DEBUG" << std::endl; return 1;
}
''', encoding='utf-8')
            with self.assertRaisesRegex(CppModuleError, '応答形式'):
                run_cpp_decisions(p)

    def test_deterministic_cpp_integration(self):
        self.assertEqual(simulate('normal', cpp_policy=self.allow),
                         simulate('normal', cpp_policy=self.allow))

    def test_cpp_source_hash_stable(self):
        self.assertEqual(len(hashlib.sha256(SAMPLE.read_bytes()).hexdigest()), 64)


if __name__ == '__main__':
    unittest.main()
