"""Rectify Gazebo's independently posed cameras using the configured extrinsics."""
import argparse
import copy
import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from cv_bridge import CvBridge
from sensor_msgs.msg import Image, CameraInfo
from design_config import load,rig

class Rectifier(Node):
    def __init__(self,cfg):
        super().__init__('stereo_rectifier')
        self.c=cfg['camera'];self.geometry=rig(cfg);self.bridge=CvBridge()
        self.infos={};self.maps={};self.subs=[];self.pubs={}
        for side in ('left','right'):
            self.pubs[side]=(self.create_publisher(Image,f'/stereo/{side}/image',10),self.create_publisher(CameraInfo,f'/stereo/{side}/camera_info',10))
            self.subs.append(self.create_subscription(CameraInfo,f'/raw/{side}/camera_info',lambda msg,s=side:self.infos.update({s:msg}),10))
            self.subs.append(self.create_subscription(Image,f'/raw/{side}/image',lambda msg,s=side:self.receive(s,msg),10))

    def receive(self,side,msg):
        if len(self.infos)!=2:return
        if not self.maps:
            # Use actual Gazebo camera intrinsics, not a separately rounded estimate.
            Kl=np.array(self.infos['left'].k).reshape(3,3);Kr=np.array(self.infos['right'].k).reshape(3,3)
            size=(msg.width,msg.height);g=self.geometry
            R1,R2,P1,P2,*_=cv2.stereoRectify(Kl,np.zeros(5),Kr,np.zeros(5),size,g['R'],g['T'],flags=cv2.CALIB_ZERO_DISPARITY,alpha=0)
            for s,R,P,K in [('left',R1,P1,Kl),('right',R2,P2,Kr)]:
                self.maps[s]=(*cv2.initUndistortRectifyMap(K,np.zeros(5),R,P[:3,:3],size,cv2.CV_32FC1),P)
            self.get_logger().info('Rectification ready; baseline = %.4f m'%(-P2[0,3]/P2[0,0]))
        mx,my,P=self.maps[side]
        frame=cv2.remap(self.bridge.imgmsg_to_cv2(msg,'rgb8'),mx,my,cv2.INTER_LINEAR)
        out=self.bridge.cv2_to_imgmsg(frame,'rgb8');out.header=copy.deepcopy(msg.header);out.header.frame_id=f'{side}_optical'
        info=CameraInfo();info.header=out.header;info.width=msg.width;info.height=msg.height
        info.distortion_model='plumb_bob';info.d=[0.]*5;info.k=P[:3,:3].reshape(-1).tolist();info.r=np.eye(3).reshape(-1).tolist();info.p=P.reshape(-1).tolist()
        self.pubs[side][0].publish(out);self.pubs[side][1].publish(info)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);a,ros=p.parse_known_args()
    rclpy.init(args=ros);n=Rectifier(load(a.config))
    try:rclpy.spin(n)
    except KeyboardInterrupt:pass
    finally:n.destroy_node();rclpy.try_shutdown()
