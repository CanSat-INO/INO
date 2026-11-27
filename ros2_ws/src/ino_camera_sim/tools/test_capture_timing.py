"""Ensure sequential capture selects real frames without forging timestamps."""
import unittest
import rclpy
from sensor_msgs.msg import Image,CameraInfo
from geometry_msgs.msg import Twist
from capture_gate import CaptureGate
from design_config import load

class CaptureTimingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):rclpy.init(args=['--ros-args','-r','__node:=capture_timing_verification'])
    @classmethod
    def tearDownClass(cls):rclpy.try_shutdown()

    def frame(self,node,t):
        for side in ('left','right'):
            for kind,cls in [('image',Image),('camera_info',CameraInfo)]:
                m=cls();m.header.stamp.sec=int(t);m.header.stamp.nanosec=round((t-int(t))*1e9)
                node.receive((side,kind),m)

    def test_skew_rounds_up_to_available_real_frame(self):
        cfg=load(overrides=['capture.mode=sequential','capture.skew_s=0.15'])
        node=CaptureGate(cfg);node.stopped_at=0.;received=[];node.emit=received.append
        try:
            for t in [1.,1.1,1.2]:self.frame(node,t)
            self.assertEqual(len(received),1)
            self.assertEqual(received[0][('left','image')].header.stamp.sec,1)
            self.assertEqual(received[0][('left','image')].header.stamp.nanosec,0)
            self.assertEqual(received[0][('right','image')].header.stamp.nanosec,200000000)
        finally:node.destroy_node()

    def test_motion_cancels_pending_stereo_pair(self):
        node=CaptureGate(load(overrides=['capture.mode=sequential']));node.stopped_at=0.;received=[];node.emit=received.append
        try:
            self.frame(node,1.)
            command=Twist();command.linear.x=.04;node.command(command)
            self.frame(node,1.1)
            self.assertEqual(received,[])
        finally:node.destroy_node()

    def test_zero_skew_uses_same_actual_frame(self):
        node=CaptureGate(load(overrides=['capture.mode=sequential','capture.skew_s=0']));node.stopped_at=0.;received=[];node.emit=received.append
        try:
            self.frame(node,1.)
            self.assertEqual(len(received),1)
            self.assertEqual(received[0][('left','image')].header.stamp,received[0][('right','image')].header.stamp)
        finally:node.destroy_node()

if __name__=='__main__':unittest.main()
