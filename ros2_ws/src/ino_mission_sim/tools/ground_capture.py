"""Ground-only camera gate: wait for zero command AND stable virtual IMU."""
import argparse
from collections import deque
import math
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu
from capture_gate import CaptureGate
from design_config import load


class CaptureStability:
    """Reject drift/rocking without treating contact-acceleration spikes as motion.

    A camera frame must additionally coincide with a quiet angular-rate sample.
    All thresholds are provisional; the truth evaluator is independent.
    """
    def __init__(self):self.samples=deque(maxlen=80)

    def update(self,t,acceleration,angular,quaternion):
        if self.samples and t<self.samples[-1][0]:self.samples.clear()
        self.samples.append((t,acceleration,angular,quaternion))
        while self.samples and self.samples[0][0]<t-.45:self.samples.popleft()

    def stable(self,now):
        samples=self.samples
        if len(samples)<10 or now-samples[-1][0]<-.01 or now-samples[-1][0]>.15 or samples[-1][0]-samples[0][0]<.35:return False
        n=len(samples);acc=[sum(s[1][i] for s in samples)/n for i in range(3)]
        angular=[sum(s[2][i] for s in samples)/n for i in range(3)]
        norm=lambda x:math.sqrt(sum(v*v for v in x))
        if abs(norm(acc)-9.8)>.15 or norm(angular)>.01:return False
        reference=samples[-1][3]
        for sample in samples:
            q=sample[3];dot=abs(sum(a*b for a,b in zip(reference,q)))
            if 2*math.acos(min(1.,dot))>.005:return False
        return True

    def quiet_at(self,t):
        if not self.samples:return False
        sample=min(self.samples,key=lambda s:abs(s[0]-t))
        return abs(sample[0]-t)<=.005 and math.sqrt(sum(v*v for v in sample[2]))<.015


class GroundCaptureGate(CaptureGate):
    def __init__(self,cfg):
        super().__init__(cfg);self.stability=CaptureStability()
        self.imu_sub=self.create_subscription(Imu,'/ground/imu',self.imu,qos_profile_sensor_data)

    def imu(self,msg):
        now=msg.header.stamp.sec+msg.header.stamp.nanosec*1e-9
        w=msg.angular_velocity;a=msg.linear_acceleration
        q=msg.orientation
        self.stability.update(now,(a.x,a.y,a.z),(w.x,w.y,w.z),(q.x,q.y,q.z,q.w))

    def stable(self):
        now=self.get_clock().now().nanoseconds*1e-9
        return self.stopped_at is not None and self.stability.stable(now)

    def receive(self,key,msg):
        stamp=msg.header.stamp.sec+msg.header.stamp.nanosec*1e-9
        if not self.stable() or not self.stability.quiet_at(stamp):return
        super().receive(key,msg)

    def publish_pair(self,frame):
        stamp=frame[('left','image')].header.stamp
        if self.stable() and self.stability.quiet_at(stamp.sec+stamp.nanosec*1e-9):super().publish_pair(frame)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--config',required=True);args,ros=a.parse_known_args()
    rclpy.init(args=ros);n=GroundCaptureGate(load(args.config))
    try:rclpy.spin(n)
    except KeyboardInterrupt:pass
    finally:n.destroy_node();rclpy.try_shutdown()
