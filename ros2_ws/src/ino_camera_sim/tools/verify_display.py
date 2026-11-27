"""Verify automatic SLAM startup before sending any velocity command."""
import argparse
import json
from pathlib import Path
import time
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile,DurabilityPolicy,qos_profile_sensor_data
from nav_msgs.msg import Path as PathMessage
from sensor_msgs.msg import PointCloud2
from visualization_msgs.msg import Marker
from geometry_msgs.msg import Twist
from tf2_ros import Buffer,TransformListener

parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);a=parser.parse_args()
rclpy.init();node=Node('display_verification',parameter_overrides=[rclpy.parameter.Parameter('use_sim_time',value=True)]);qos=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL)
state={'cloud_points':0,'slam_poses':0,'odom_poses':0,'marker_resource':None,'automatic_start':False}
def marker(m):
    state['marker_resource']=m.mesh_resource;state['marker_frame']=m.header.frame_id;state['marker_frame_locked']=m.frame_locked
subs=[node.create_subscription(PathMessage,'/slam/path',lambda m:state.update(slam_poses=len(m.poses),slam_frame=m.header.frame_id),qos),node.create_subscription(PathMessage,'/odom/path',lambda m:state.update(odom_poses=len(m.poses)),qos),node.create_subscription(Marker,'/robot/cad_marker',marker,qos),node.create_subscription(PointCloud2,'/cloud_map',lambda m:state.update(cloud_points=m.width*m.height),qos)]
buffer=Buffer();listener=TransformListener(buffer,node)
pub=node.create_publisher(Twist,'/cmd_vel',10)
start=None;deadline=time.monotonic()+150
try:
    while time.monotonic()<deadline:
        rclpy.spin_once(node,timeout_sec=.03)
        now=node.get_clock().now().nanoseconds/1e9
        # This node uses ROS time; enable it below before collecting data.
        state['map_to_base_tf']=buffer.can_transform('map','base_link',rclpy.time.Time())
        if start is None:
            if state['cloud_points'] and state['slam_poses'] and state['odom_poses'] and state['marker_resource'] and state['map_to_base_tf']:
                state['automatic_start']=True;start=now
                print('Automatic startup verified before any velocity command',flush=True)
            continue
        elapsed=now-start
        cmd=Twist()
        if elapsed<3:cmd.linear.x=.04
        pub.publish(cmd)
        if elapsed>=7:break
finally:
    if start is not None:
        for _ in range(10):pub.publish(Twist());rclpy.spin_once(node,timeout_sec=.02)
    node.destroy_node();rclpy.try_shutdown()
Path(a.output).write_text(json.dumps(state,indent=2));print(json.dumps(state,indent=2))
if not state['automatic_start'] or state['slam_poses']<2 or state['odom_poses']<2:raise SystemExit(1)
