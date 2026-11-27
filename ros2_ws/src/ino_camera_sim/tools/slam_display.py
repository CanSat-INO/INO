"""Publish actual estimated paths and expose SLAM readiness to the settings UI."""
import argparse
import copy
import json
from pathlib import Path
import time
import rclpy
from rclpy.node import Node
from rclpy.clock import Clock,ClockType
from rclpy.qos import QoSProfile,DurabilityPolicy,qos_profile_sensor_data
from geometry_msgs.msg import PoseStamped,Twist
from nav_msgs.msg import Odometry,Path as PathMessage
from sensor_msgs.msg import Image,PointCloud2
from rtabmap_msgs.msg import RGBDImage,MapData
from visualization_msgs.msg import Marker
from design_config import load
from rviz_mesh import ensure_stl

class SlamDisplay(Node):
    def __init__(self,output,cfg):
        super().__init__('slam_display')
        self.output=Path(output)
        self.capture_mode=cfg['capture']['mode']
        qos=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.odom_pub=self.create_publisher(PathMessage,'/odom/path',qos)
        self.slam_pub=self.create_publisher(PathMessage,'/slam/path',qos)
        self.robot_pub=self.create_publisher(Marker,'/robot/cad_marker',qos)
        self.pose_pub=self.create_publisher(PoseStamped,'/slam/robot_pose',qos)
        marker=Marker();marker.header.frame_id='base_link';marker.ns='cansat';marker.id=0;marker.action=Marker.ADD;marker.frame_locked=True;marker.pose.orientation.w=1.0
        marker.color.r=.72;marker.color.g=.75;marker.color.b=.8;marker.color.a=1.0
        if cfg['robot']['shape']=='simple':
            marker.type=Marker.CUBE;marker.scale.x=.15;marker.scale.y=.18;marker.scale.z=.12;marker.pose.position.z=.09
        else:
            marker.type=Marker.MESH_RESOURCE;marker.mesh_resource=ensure_stl(cfg['robot']['shape']).as_uri();marker.mesh_use_embedded_materials=False;marker.scale.x=marker.scale.y=marker.scale.z=1.0
        # Publish the last optimized pose directly in map coordinates. A stopped
        # camera provides no live odom TF while driving; never invent fresh TF.
        marker.frame_locked=False
        self.robot_marker=marker
        self.path=PathMessage();self.count=0;self.raw_count=0;self.cloud_points=0;self.graph_count=0
        self.last_valid=None;self.lost=False;self.moving=False
        self.subs=[self.create_subscription(Odometry,'/odom',self.odom,qos_profile_sensor_data),self.create_subscription(MapData,'/mapData',self.map_data,10),self.create_subscription(RGBDImage,'/capture/rgbd_image',self.capture,10),self.create_subscription(Image,'/stereo/left/image',self.raw,qos_profile_sensor_data),self.create_subscription(PointCloud2,'/cloud_map',self.cloud,qos_profile_sensor_data),self.create_subscription(Twist,'/cmd_vel',self.command,10)]
        self.timer=self.create_timer(.5,self.status,clock=Clock(clock_type=ClockType.STEADY_TIME))

    def raw(self,msg):self.raw_count+=1
    def capture(self,msg):self.count+=1
    def cloud(self,msg):self.cloud_points=msg.width*msg.height
    def command(self,msg):self.moving=any(abs(x)>1e-5 for x in (msg.linear.x,msg.linear.y,msg.linear.z,msg.angular.x,msg.angular.y,msg.angular.z))

    def odom(self,msg):
        if not any(msg.pose.covariance) or msg.pose.covariance[0]>1:
            self.lost=self.last_valid is not None
            return
        self.last_valid=time.monotonic();self.lost=False
        if self.path.header.frame_id and self.path.header.frame_id!=msg.header.frame_id:self.path.poses=[]
        self.path.header=copy.deepcopy(msg.header)
        pose=PoseStamped();pose.header=copy.deepcopy(msg.header);pose.pose=copy.deepcopy(msg.pose.pose)
        if self.path.poses:
            last=self.path.poses[-1].pose.position;p=pose.pose.position
            # Preserve turns and movement; don't grow indefinitely while stationary.
            q0=self.path.poses[-1].pose.orientation;q=pose.pose.orientation
            if sum((a-b)**2 for a,b in zip((p.x,p.y,p.z),(last.x,last.y,last.z)))<1e-6 and abs(q.x-q0.x)+abs(q.y-q0.y)+abs(q.z-q0.z)+abs(q.w-q0.w)<.002:
                self.odom_pub.publish(self.path)
                return
        self.path.poses.append(pose)
        self.path.poses=self.path.poses[-20000:]
        self.odom_pub.publish(self.path)

    def map_data(self,msg):
        graph=msg.graph
        if not graph.poses:return
        path=PathMessage();path.header=copy.deepcopy(graph.header if graph.header.frame_id else msg.header)
        if not path.header.frame_id:return
        for _,pose in sorted(zip(graph.poses_id,graph.poses),key=lambda item:item[0]):
            stamped=PoseStamped();stamped.header=copy.deepcopy(path.header);stamped.pose=copy.deepcopy(pose);path.poses.append(stamped)
        self.graph_count=len(path.poses);self.slam_pub.publish(path)
        pose=copy.deepcopy(path.poses[-1])
        pose.header.stamp.sec=0;pose.header.stamp.nanosec=0
        self.pose_pub.publish(pose)
        marker=copy.deepcopy(self.robot_marker)
        marker.header=copy.deepcopy(pose.header)
        offset=marker.pose.position.z
        marker.pose=copy.deepcopy(pose.pose)
        q=marker.pose.orientation
        marker.pose.position.x+=offset*2*(q.x*q.z+q.w*q.y)
        marker.pose.position.y+=offset*2*(q.y*q.z-q.w*q.x)
        marker.pose.position.z+=offset*(1-2*(q.x*q.x+q.y*q.y))
        self.robot_pub.publish(marker)

    def status(self):
        if not self.raw_count:phase='カメラ描画の準備中'
        elif not self.count:phase='停止後の撮影待ち（走行中は撮影しません）'
        elif self.last_valid is None:phase='SLAM初期化中'
        elif self.lost:phase='追跡喪失：停止して視野を戻すか再起動してください'
        elif self.moving and self.capture_mode!='continuous':phase='走行中：撮影停止・最後の推定位置を表示中。kで停止すると撮影再開'
        elif self.moving:phase='走行中：連続撮影でSLAMを更新中'
        elif self.cloud_points:phase='SLAM動作中'
        else:phase='位置推定中・地図生成待ち'
        state={'phase':phase,'raw_images':self.raw_count,'captured_pairs':self.count,'odom_path_poses':len(self.path.poses),'slam_path_poses':self.graph_count,'cloud_points':self.cloud_points,'tracking_lost':self.lost,'moving':self.moving,'last_valid_age_s':None if self.last_valid is None else time.monotonic()-self.last_valid}
        temp=self.output.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False));temp.replace(self.output)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--config',required=True);args,ros=parser.parse_known_args()
    rclpy.init(args=ros);node=SlamDisplay(args.output,load(args.config))
    try:rclpy.spin(node)
    except KeyboardInterrupt:pass
    finally:node.destroy_node();rclpy.try_shutdown()
