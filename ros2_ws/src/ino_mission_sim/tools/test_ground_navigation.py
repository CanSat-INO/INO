"""Regress the actual stop/photo starvation found in Gazebo course trials."""
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock
from tf2_ros import TransformException
from ground_navigation import GroundNavigation


class NavigationTimingTests(unittest.TestCase):
    def state(self,phase,done=False):
        buffer=Mock();buffer.lookup_transform.side_effect=TransformException('no new transform')
        return NS(tf_buffer=buffer,started=0.,odom=object(),done=done,phase=phase,reason='',
            stop_since=10.,last_mapped=11.,odom_stamp=18.,map_ready=True,
            cfg=dict(duration_s=360,max_sensor_age_s=.8),last_status=20.,command_pub=Mock(),
            get_clock=lambda:NS(now=lambda:NS(nanoseconds=20_000_000_000)))

    def test_sensor_backlog_does_not_discard_already_stopped_photo(self):
        state=self.state('photograph');GroundNavigation.tick(state)
        self.assertEqual(10.,state.stop_since);self.assertEqual(11.,state.last_mapped)
        self.assertEqual('photograph',state.phase)
        self.assertEqual(0.,state.command_pub.publish.call_args.args[0].linear.x)

    def test_stale_odometry_during_drive_stops_and_requires_new_photo(self):
        state=self.state('drive');GroundNavigation.tick(state)
        self.assertEqual(20.,state.stop_since);self.assertEqual('photograph',state.phase)
        self.assertEqual(0.,state.command_pub.publish.call_args.args[0].linear.x)

    def test_finished_goal_is_preserved_when_shutdown_messages_lag(self):
        state=self.state('goal',done=True);GroundNavigation.tick(state)
        self.assertEqual('goal',state.phase);self.assertEqual(10.,state.stop_since)


if __name__=='__main__':unittest.main()
