"""Regression tests for evidence-linked v8.3 virtual module fault analysis."""
import csv
import io
import unittest

from module_network import SCENARIOS, simulate
from module_fault_analysis import analyze_result, make_analysis_csv


ALLOW = dict(main_landing=True, drive_move=True, cam_capture=True, drive_stop=True)


class FaultAnalysisTests(unittest.TestCase):
    def test_all_scenarios_analyzable_without_cpp(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.key):
                result = simulate(scenario.key)
                analysis = analyze_result(result)
                self.assertEqual(analysis.scenario_key, scenario.key)
                self.assertEqual(analysis.evaluation, result.evaluation)

    def test_all_scenarios_analyzable_with_cpp(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario.key):
                result = simulate(scenario.key, cpp_policy=ALLOW)
                self.assertEqual(analyze_result(result).evaluation, result.evaluation)

    def test_normal_success_has_no_primary_event(self):
        a = analyze_result(simulate('normal', cpp_policy=ALLOW))
        self.assertIsNone(a.primary_event_index)
        self.assertFalse(a.steps)
        self.assertEqual(a.classification, '異常なし')

    def test_no_landing_undetermined_is_not_fault(self):
        a = analyze_result(simulate('no_landing', cpp_policy=ALLOW))
        self.assertIsNone(a.primary_event_index)
        self.assertEqual(a.classification, '入力なし')
        self.assertEqual(a.evaluation, '未判定')

    def test_move_drop_precedes_timeout(self):
        r = simulate('drop_drive_cmd', cpp_policy=ALLOW)
        a = analyze_result(r)
        self.assertEqual(r.events[a.primary_event_index].event, '欠落')
        self.assertEqual(a.classification, '仮想通信の欠落')
        self.assertEqual(a.steps[0].role, '発端')
        self.assertTrue(any(r.events[s.event_index].event == 'タイムアウト' for s in a.steps))

    def test_move_drop_stop_is_command_not_confirmed_stop(self):
        a = analyze_result(simulate('drop_drive_cmd', cpp_policy=ALLOW))
        self.assertTrue(any(s.role == '停止指令' for s in a.steps))
        self.assertIn('停止完了を意味せず', a.caution)

    def test_cam_rejection_scenario_is_labeled_correctly(self):
        r = simulate('cam_reject', cpp_policy=ALLOW)
        a = analyze_result(r)
        self.assertEqual(a.classification, '仮想CAM指令拒否')
        self.assertEqual(r.evaluation, '失敗')

    def test_cpp_cam_rejection_before_main_fault(self):
        denied = dict(ALLOW, cam_capture=False)
        r = simulate('normal', cpp_policy=denied)
        a = analyze_result(r)
        self.assertEqual(r.events[a.primary_event_index].event, 'C++拒否')
        self.assertEqual(a.classification, 'C++制御判断')
        self.assertEqual(a.steps[0].role, '発端')

    def test_cpp_main_denial_no_move(self):
        denied = dict(ALLOW, main_landing=False)
        r = simulate('normal', cpp_policy=denied)
        a = analyze_result(r)
        self.assertEqual(a.classification, 'C++制御判断')
        self.assertFalse(any(e.message.startswith('MOVE(') for e in r.events))

    def test_slow_cam_ack_is_delay_timeout(self):
        r = simulate('slow_cam_ack', cpp_policy=ALLOW)
        a = analyze_result(r)
        self.assertIn('遅延', a.classification)
        self.assertEqual(r.events[a.primary_event_index].event, 'タイムアウト')
        self.assertTrue(any(e.event == '無視' for e in r.events))

    def test_steps_follow_event_order(self):
        for scenario in SCENARIOS:
            a = analyze_result(simulate(scenario.key, cpp_policy=ALLOW))
            order = [s.event_index for s in a.steps]
            self.assertEqual(order, sorted(order))
            self.assertEqual(len(order), len(set(order)))

    def test_primary_flag_one_for_failure(self):
        r = simulate('drop_drive_ack', cpp_policy=ALLOW)
        a = analyze_result(r)
        rows = list(csv.DictReader(io.StringIO(make_analysis_csv(r, a))))
        self.assertEqual(len(rows), len(r.events))
        self.assertEqual(sum(row['is_primary_event'] == '1' for row in rows), 1)
        self.assertEqual(sum(row['analysis_role'] == '発端' for row in rows), 1)

    def test_no_primary_flag_for_normal(self):
        r = simulate('normal')
        a = analyze_result(r)
        rows = list(csv.DictReader(io.StringIO(make_analysis_csv(r, a))))
        self.assertTrue(all(row['is_primary_event'] == '0' for row in rows))

    def test_csv_includes_source_provenance(self):
        r = simulate('normal', cpp_policy=ALLOW)
        a = analyze_result(r)
        row = next(csv.DictReader(io.StringIO(make_analysis_csv(
            r, a, cpp_source='example.cpp', cpp_sha256='abcd'))))
        self.assertEqual(row['cpp_source'], 'example.cpp')
        self.assertEqual(row['cpp_sha256'], 'abcd')

    def test_analysis_is_deterministic(self):
        r = simulate('drop_stop_ack')
        self.assertEqual(analyze_result(r), analyze_result(r))

    def test_late_ack_does_not_become_first_cause(self):
        r = simulate('slow_cam_ack')
        a = analyze_result(r)
        self.assertNotEqual(r.events[a.primary_event_index].event, '無視')


if __name__ == '__main__':
    unittest.main()
