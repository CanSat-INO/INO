"""Provisional virtual track-encoder + IMU dead reckoning; never reads truth.

The Gazebo track controller integrates belt speed, not measured ground motion.
Slip and pitch therefore cause estimation error. This is not a calibrated EKF.
"""
import copy
import math
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Imu
from geometry_msgs.msg import TransformStamped
from tf2_ros import TransformBroadcaster
from scipy.spatial.transform import Rotation


class GroundOdometry(Node):
    def __init__(self):
        super().__init__('ground_odometry')
        self.imu=None;self.last=None;self.position=[0.,0.,0.]
        self.publisher=self.create_publisher(Odometry,'/odom',20)
        self.tf=TransformBroadcaster(self)
        self.create_subscription(Imu,'/ground/imu',self.receive_imu,qos_profile_sensor_data)
        self.create_subscription(Odometry,'/ground/encoder_odom',self.encoder,20)

    def receive_imu(self,msg):self.imu=msg

    def encoder(self,msg):
        stamp=msg.header.stamp.sec+msg.header.stamp.nanosec*1e-9
        if self.imu is None:return
        imu_stamp=self.imu.header.stamp.sec+self.imu.header.stamp.nanosec*1e-9
        if abs(stamp-imu_stamp)>.3:return
        q=self.imu.orientation
        rot=Rotation.from_quat([q.x,q.y,q.z,q.w])
        dt=0. if self.last is None else max(0.,min(.15,stamp-self.last));self.last=stamp
        velocity=rot.apply([msg.twist.twist.linear.x,0.,0.])
        self.position=[p+float(v)*dt for p,v in zip(self.position,velocity)]
        out=Odometry();out.header=copy.deepcopy(msg.header);out.header.frame_id='odom';out.child_frame_id='base_link'
        out.pose.pose.position.x,out.pose.pose.position.y,out.pose.pose.position.z=self.position
        out.pose.pose.orientation=copy.deepcopy(q);out.twist=copy.deepcopy(msg.twist)
        out.twist.twist.angular=copy.deepcopy(self.imu.angular_velocity)
        for i in (0,7,14,21,28,35):out.pose.covariance[i]=.0025
        self.publisher.publish(out)
        tf=TransformStamped();tf.header=out.header;tf.child_frame_id='base_link'
        tf.transform.translation.x,tf.transform.translation.y,tf.transform.translation.z=self.position
        tf.transform.rotation=copy.deepcopy(q);self.tf.sendTransform(tf)


if __name__=='__main__':
    rclpy.init();n=GroundOdometry()
    try:rclpy.spin(n)
    except (KeyboardInterrupt, ExternalShutdownException):pass
    finally:n.destroy_node();rclpy.try_shutdown()
