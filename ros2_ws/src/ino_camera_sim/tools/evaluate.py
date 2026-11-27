"""Bounded, simulation-clock-driven motion test and timestamp-matched errors.

Ground truth is consumed here only, never by the SLAM pipeline.
"""
import argparse
import csv
import json
import math
import time
from pathlib import Path
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image, PointCloud2
from sensor_msgs_py import point_cloud2
from rtabmap_msgs.msg import RGBDImage, MapData
from cv_bridge import CvBridge
import cv2
from design_config import load
from geometry_msgs.msg import Twist

def stamp(m):
    return m.header.stamp.sec+m.header.stamp.nanosec/1e9

def pose(m):
    p,q=m.pose.pose.position,m.pose.pose.orientation
    yaw=math.atan2(2*(q.w*q.z+q.x*q.y),1-2*(q.y*q.y+q.z*q.z))
    return [stamp(m),p.x,p.y,p.z,yaw]

def wrap(v):
    return math.atan2(math.sin(v),math.cos(v))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    parser.add_argument('--config')
    parser.add_argument('--wall-timeout',type=float)
    parser.add_argument('--mode',choices=['continuous','stop','sequential'],default='continuous')
    args=parser.parse_args()
    cfg=load(args.config) if args.config else load()
    t=cfg['test'];schedule=[(5.,0.,0.)]
    for i in range(t['repeats']):
        direction=-1 if t['route']=='return' and i%2 else 1
        schedule.extend([(t['step_m']/t['speed_mps'],direction*t['speed_mps'],0.),(t['stop_s'],0.,0.)])
        if i<t['repeats']-1 and t['route']!='return':
            schedule.extend([(abs(t['turn_deg'])/t['turn_rate_degps'],0.,math.copysign(math.radians(t['turn_rate_degps']),t['turn_deg'])),(t['stop_s'],0.,0.)])
    schedule.append((4.,0.,0.))
    duration=sum(x[0] for x in schedule)
    def velocity_at(elapsed):
        for seconds,v,w in schedule:
            if elapsed<seconds:return v,w
            elapsed-=seconds
        return 0.,0.
    dest=Path(args.output)
    dest.mkdir(parents=True,exist_ok=True)
    rclpy.init()
    n=Node('cansat_evaluation',parameter_overrides=[rclpy.parameter.Parameter('use_sim_time',value=True)])
    truth, estimates, images = [], [], {'left':[],'right':[]}
    pairs=[];cloud=[];link_types=set();bridge=CvBridge()
    def paired(m):
        pairs.append((stamp(m.rgb),stamp(m.depth)))
        if len(pairs)==1:
            for side,image in [('left',m.rgb),('right',m.depth)]:cv2.imwrite(str(dest/f'{side}.png'),bridge.imgmsg_to_cv2(image,'bgr8'))
        if len(pairs)%10==0:
            for side,image in [('left',m.rgb),('right',m.depth)]:cv2.imwrite(str(dest/f'{side}-latest.png'),bridge.imgmsg_to_cv2(image,'bgr8'))
    def mapped(m):
        cloud[:]=[point_cloud2.read_points_numpy(m,field_names=['x','y','z'],skip_nans=True).copy()]
        stats['cloud_points']=m.width*m.height
    stats={'cloud_points':0,'invalid_odom':0}
    delays=[]
    def odom(m):
        # RTAB-Map publishes a null pose/zero covariance when tracking fails.
        if not any(m.pose.covariance) or m.pose.covariance[0]>1:
            stats['invalid_odom']+=1
        else:
            estimates.append(pose(m))
            delays.append(n.get_clock().now().nanoseconds/1e9-stamp(m))
    subs=[n.create_subscription(Odometry,'/ground_truth/odom',lambda m:truth.append(pose(m)),qos_profile_sensor_data),n.create_subscription(Odometry,'/odom',odom,qos_profile_sensor_data),n.create_subscription(PointCloud2,'/cloud_map',mapped,qos_profile_sensor_data),n.create_subscription(RGBDImage,'/capture/rgbd_image',paired,10),n.create_subscription(MapData,'/mapData',lambda m:link_types.update(link.type for link in m.graph.links),10)]
    for side in images:
        subs.append(n.create_subscription(Image,f'/capture/{side}/image',lambda m,s=side:images[s].append(stamp(m)),10))
    pub=n.create_publisher(Twist,'/cmd_vel',10)
    start=None
    deadline=time.monotonic()+max(100,duration*2+45)
    if args.wall_timeout:deadline=time.monotonic()+args.wall_timeout
    completed=False
    try:
        while time.monotonic()<deadline:
            rclpy.spin_once(n,timeout_sec=.03)
            now=n.get_clock().now().nanoseconds/1e9
            if start is None and truth and estimates:
                start=now
            elapsed=0 if start is None else now-start
            cmd=Twist()
            cmd.linear.x,cmd.angular.z=velocity_at(elapsed)
            pub.publish(cmd)
            if elapsed>=duration:
                completed=True
                break
    finally:
        # Repeat stop while servicing callbacks to avoid leaving a latched motion.
        for _ in range(10):
            pub.publish(Twist())
            rclpy.spin_once(n,timeout_sec=.02)
        n.destroy_node()
        rclpy.shutdown()
    rows=[]
    if truth and estimates:
        ts=np.array([t[0] for t in truth])
        for e in estimates:
            idx=int(np.argmin(abs(ts-e[0])))
            if abs(ts[idx]-e[0])<=.075:
                rows.append(e+truth[idx][1:])
    errors=[]
    if rows:
        origin=rows[0]
        def relative(p,origin):
            dx,dy=p[0]-origin[0],p[1]-origin[1]
            c,s=math.cos(origin[3]),math.sin(origin[3])
            return [c*dx+s*dy,-s*dx+c*dy,p[2]-origin[2],wrap(p[3]-origin[3])]
        for row in rows:
            est=relative(row[1:5],origin[1:5]);gt=relative(row[5:9],origin[5:9])
            errors.append([math.dist(est[:3],gt[:3]),abs(wrap(est[3]-gt[3]))])
    if delays:
        stats['odom_delay_median_s']=float(np.median(delays))
        stats['odom_delay_max_s']=max(delays)
    stats.update(completed=completed,truth_samples=len(truth),valid_odom_samples=len(estimates),matched_samples=len(rows),image_pairs=min(map(len,images.values())))
    if errors:
        stats.update(position_rmse_m=float(np.sqrt(np.mean(np.array(errors)[:,0]**2))),position_max_error_m=max(e[0] for e in errors),yaw_rmse_deg=float(np.sqrt(np.mean(np.array(errors)[:,1]**2))*180/math.pi),final_position_error_m=errors[-1][0],final_yaw_error_deg=errors[-1][1]*180/math.pi)
    if truth:
        stats['truth_start']=truth[0][1:];stats['truth_end']=truth[-1][1:]
    if pairs:
        skews=[abs(r-l) for l,r in pairs]
        stats['median_stereo_skew_s']=float(np.median(skews))
        stats['max_stereo_skew_s']=max(skews)
    if start is not None:
        stats['captures_during_motion']=sum(any(abs(x)>1e-6 for x in velocity_at(pair[0]-start)) for pair in pairs)
    stats['mode']=args.mode
    stats['image_pairs']=len(pairs)
    stats['surface']=cfg['world']['surface']
    stats['config_path']=args.config
    stats['link_types_observed']=sorted(link_types)
    stats['requested_route_duration_s']=duration
    if cloud and len(cloud[0]):
        xyz=cloud[0]
        roi=xyz[(xyz[:,0]>=0)&(xyz[:,0]<=3)&(abs(xyz[:,1])<=2)]
        ground=roi[(roi[:,2]>=-.05)&(roi[:,2]<=cfg['world']['grass_height_m']+.05)]
        stats['ground_like_points_in_roi']=len(ground)
        stats['observed_ground_grid_area_m2']=len(np.unique(np.floor(ground[:,:2]/.1),axis=0))*.01
        stats['ground_roi_area_m2']=12.0
        stats['points_in_cone_regions']=[int(np.sum(((xyz[:,0]-x)**2+(xyz[:,1]-y)**2<(cfg['world']['cone_base_m']*.6)**2)&(xyz[:,2]>.05)&(xyz[:,2]<cfg['world']['cone_height_m']+.1))) for x,y in cfg['world']['cones']]
        np.savez_compressed(dest/'cloud.npz',xyz=xyz)
    if rows:stats['final_pose_age_s']=max(0,truth[-1][0]-rows[-1][0])
    stats['tracking_valid_fraction']=len(estimates)/(len(estimates)+stats['invalid_odom']) if estimates or stats['invalid_odom'] else 0
    with (dest/'trajectory.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['time','est_x','est_y','est_z','est_yaw','truth_x','truth_y','truth_z','truth_yaw']);w.writerows(rows)
    (dest/'result.json').write_text(json.dumps(stats,indent=2))
    print(json.dumps(stats,indent=2))
    if not completed or not rows or not stats['cloud_points']:
        raise SystemExit(1)

if __name__=='__main__':
    main()

