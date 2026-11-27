"""Bounded headless integration check; saves received images and JSON evidence.

A successful check requires actual ROS delivery, progressing simulation time,
non-blank raw/rectified stereo images, intrinsics, capture pairs and valid SLAM
odometry. Rendering still requires WSLg/OpenGL. Only this launch session is stopped.
"""
import argparse
import datetime
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time
import uuid

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from cv_bridge import CvBridge
from nav_msgs.msg import Odometry
from geometry_msgs.msg import Twist
from rosgraph_msgs.msg import Clock
from rtabmap_msgs.msg import RGBDImage
from sensor_msgs.msg import Image, CameraInfo, PointCloud2
from design_config import ROOT


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--timeout',type=float,default=90)
    parser.add_argument('--config',default=str(ROOT/'config/design.yaml'))
    args=parser.parse_args()
    out=ROOT/'logs'/('pipeline-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
    out.mkdir(parents=True)
    env=os.environ.copy()
    env.setdefault('ROS_DOMAIN_ID','64')
    env.setdefault('GZ_PARTITION','ino_camera_'+env['ROS_DOMAIN_ID'])
    env.setdefault('GZ_IP','127.0.0.1')
    os.environ.update({k:env[k] for k in ('ROS_DOMAIN_ID','GZ_PARTITION','GZ_IP')})
    rclpy.init()
    node=Node('ino_camera_pipeline_check')
    bridge=CvBridge()
    counts={}; images={}; intrinsics={}; clocks=[]; pairs=[]; odoms=[]; cloud=[0]
    def image(msg,key):
        counts[key]=counts.get(key,0)+1
        if key not in images:
            a=bridge.imgmsg_to_cv2(msg,'bgr8')
            images[key]={'width':msg.width,'height':msg.height,'stddev':float(np.std(a)), 'frame':msg.header.frame_id}
            cv2.imwrite(str(out/(key.replace('/','_')+'.png')),a)
    def info(msg,side):
        intrinsics[side]={'width':msg.width,'height':msg.height,'fx':msg.k[0],'frame':msg.header.frame_id}
    def clock(msg):
        t=msg.clock.sec+msg.clock.nanosec/1e9
        if not clocks:clocks.append(t)
        elif len(clocks)==1:clocks.append(t)
        else:clocks[1]=t
    def odom(msg):
        p=msg.pose.pose.position
        if all(math.isfinite(v) for v in (p.x,p.y,p.z)) and 0<msg.pose.covariance[0]<=1:
            odoms.append([p.x,p.y,p.z])
    def pair(msg):
        stamp=lambda i:i.header.stamp.sec+i.header.stamp.nanosec/1e9
        pairs.append([stamp(msg.rgb),stamp(msg.depth)])
    subs=[node.create_subscription(Clock,'/clock',clock,qos_profile_sensor_data),
          node.create_subscription(RGBDImage,'/capture/rgbd_image',pair,qos_profile_sensor_data),
          node.create_subscription(Odometry,'/odom',odom,qos_profile_sensor_data),
          node.create_subscription(PointCloud2,'/cloud_map',lambda m:cloud.__setitem__(0,m.width*m.height),qos_profile_sensor_data)]
    for side in ('left','right'):
        for stage in ('raw','stereo'):
            key=stage+'/'+side
            subs.append(node.create_subscription(Image,'/'+key+'/image',lambda m,k=key:image(m,k),qos_profile_sensor_data))
        subs.append(node.create_subscription(CameraInfo,'/stereo/'+side+'/camera_info',lambda m,s=side:info(m,s),qos_profile_sensor_data))
    cmd=node.create_publisher(Twist,'/cmd_vel',10)
    log=(out/'launch.log').open('w')
    proc=subprocess.Popen(['bash',str(ROOT/'scripts/start.sh'),'gui:=false','rviz:=false','capture_mode:=continuous','config:='+str(Path(args.config).resolve()),'runtime:='+str(out)],env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    checks={};error=None
    def verify():
        return {'clock':len(clocks)==2 and clocks[1]>clocks[0],
                'images':len(images)==4 and all(counts.get(k,0)>=3 and v['stddev']>1 for k,v in images.items()),
                'camera_info':len(intrinsics)==2 and all(v['fx']>0 for v in intrinsics.values()),
                'capture_pairs':len(pairs)>=3,
                'valid_slam_odometry':len(odoms)>=3,
                'slam_cloud':cloud[0]>0}
    try:
        deadline=time.monotonic()+args.timeout
        while time.monotonic()<deadline and proc.poll() is None:
            rclpy.spin_once(node,timeout_sec=.1)
            # Stay still until tracking is established, then make a short straight move.
            msg=Twist()
            if len(clocks)==2 and 8<clocks[1]<11 and odoms:msg.linear.x=.03
            cmd.publish(msg)
            checks=verify()
            if all(checks.values()):break
    except Exception as exc:error=str(exc)
    finally:
        cmd.publish(Twist())
        time.sleep(.1)
        if proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:proc.wait(timeout=45)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGTERM)
                try:proc.wait(timeout=10)
                except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        log.close();node.destroy_node();rclpy.try_shutdown()
    checks=verify()
    result={'passed':all(checks.values()) and error is None,'checks':checks,'image_counts':counts,'images':images,'intrinsics':intrinsics,'clock':clocks,'pairs':len(pairs),'valid_odom_count':len(odoms),'cloud_points':cloud[0],'error':error,'output':str(out)}
    (out/'verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
