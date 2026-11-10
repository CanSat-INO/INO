import csv
import io
import unittest

from module_network import SCENARIOS, simulate, make_log_csv


class ModuleNetworkTests(unittest.TestCase):
    def test_scenario_count_and_uniqueness(self):
        self.assertEqual(len(SCENARIOS),8)
        self.assertEqual(len({s.key for s in SCENARIOS}),8)

    def test_normal_complete(self):
        r=simulate('normal')
        self.assertEqual((r.evaluation,r.main_state,r.cam_state,r.drive_state),
                         ('成功','FINISHED','DONE','STOPPED'))
        self.assertEqual((r.loss_count,r.timeout_count),(0,0))

    def test_normal_command_order(self):
        commands=[e.message.split('(')[0] for e in simulate('normal').events
                  if e.event=='送信' and e.source=='Main']
        self.assertEqual(commands,['MOVE','CAPTURE','STOP'])

    def test_drop_move(self):
        r=simulate('drop_drive_cmd')
        self.assertEqual(r.evaluation,'失敗')
        self.assertEqual(r.loss_count,1)
        self.assertEqual(r.timeout_count,1)
        self.assertEqual(r.drive_state,'STOPPED')
        self.assertFalse(any(e.message.startswith('CAPTURE') for e in r.events))

    def test_drop_drive_ack_emergency_stop(self):
        r=simulate('drop_drive_ack')
        self.assertEqual(r.evaluation,'失敗')
        self.assertEqual(r.drive_state,'STOPPED')
        self.assertTrue(any(e.event=='タイムアウト' for e in r.events))

    def test_drop_cam_ack(self):
        r=simulate('drop_cam_ack')
        self.assertEqual(r.evaluation,'失敗')
        self.assertEqual((r.main_state,r.drive_state),('FAULT','STOPPED'))

    def test_slow_cam_ack_is_ignored_after_timeout(self):
        r=simulate('slow_cam_ack')
        self.assertEqual(r.evaluation,'失敗')
        self.assertTrue(any(e.event=='無視' for e in r.events))
        self.assertEqual(r.timeout_count,1)

    def test_cam_rejection(self):
        r=simulate('cam_reject')
        self.assertEqual((r.evaluation,r.cam_state,r.drive_state),('失敗','FAULT','STOPPED'))
        self.assertEqual(r.timeout_count,0)

    def test_stop_ack_loss(self):
        r=simulate('drop_stop_ack')
        self.assertEqual((r.evaluation,r.drive_state),('失敗','STOPPED'))
        self.assertGreaterEqual(r.timeout_count,1)

    def test_no_landing_does_not_move(self):
        r=simulate('no_landing')
        self.assertEqual(r.evaluation,'未判定')
        self.assertEqual(r.drive_state,'IDLE')
        self.assertFalse(any(e.source=='Main' and e.event=='送信' for e in r.events))

    def test_unknown_scenario(self):
        with self.assertRaises(ValueError):
            simulate('missing')

    def test_deterministic(self):
        for s in SCENARIOS:
            self.assertEqual(simulate(s.key),simulate(s.key))

    def test_timestamp_non_decreasing(self):
        for s in SCENARIOS:
            ts=[e.time_ms for e in simulate(s.key).events]
            self.assertEqual(ts,sorted(ts),s.key)

    def test_csv_export(self):
        r=simulate('normal')
        rows=list(csv.DictReader(io.StringIO(make_log_csv(r))))
        self.assertEqual(len(rows),len(r.events))
        self.assertEqual(rows[0]['scenario'],'normal')
        self.assertIn('time_ms',rows[0])


if __name__ == '__main__':
    unittest.main()
