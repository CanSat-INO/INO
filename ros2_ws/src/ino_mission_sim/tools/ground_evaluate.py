"""Read-only truth evaluation, in a separate process from navigation."""
import argparse
import bisect
import csv
import json
import math
from pathlib import Path
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from rtabmap_msgs.msg import MapData
from sensor_msgs.msg import PointCloud2
from std_msgs.msg import String
from ground_world import load


class Evaluate(Node):
    def __init__(self,cfg,out):
        super().__init__('ground_evaluate');self.cfg=cfg;self.out=Path(out);self.nav={};self.truth=None;self.nodes=0;self.cloud=0
        self.rows=0;self.previous=None;self.distance=0.;self.max_z=-1.;self.ramp_z=-1.;self.step_z=-1.
        self.min_clearance=float('inf');self.max_error=0.;self.map_updates=0;self.truth_speeds=[];self.truth_times=[]
        self.file=(self.out/'trajectory.csv').open('w',newline='');self.writer=csv.writer(self.file)
        self.writer.writerow(['time_s','truth_x','truth_y','truth_z','estimated_x','estimated_y','estimated_z','phase','linear_command','angular_command','truth_linear_mps','truth_angular_radps'])
        self.create_subscription(Odometry,'/ground_truth/odom',self.receive_truth,20)
        self.create_subscription(String,'/ground/status',self.receive_state,10)
        self.create_subscription(MapData,'/mapData',self.receive_map,10)
        self.create_subscription(PointCloud2,'/cloud_map',self.receive_cloud,10)
        self.create_timer(.5,self.write_result)

    def receive_state(self,msg):self.nav=json.loads(msg.data)
    def receive_map(self,msg):self.nodes=len(msg.graph.poses_id);self.map_updates+=1
    def receive_cloud(self,msg):self.cloud=msg.width*msg.height

    def receive_truth(self,msg):
        p=msg.pose.pose.position;self.truth=[p.x,p.y,p.z]
        if self.previous is not None:self.distance+=math.dist(self.previous,self.truth)
        self.previous=self.truth[:];self.max_z=max(self.max_z,p.z)
        for name in ('ramp','step'):
            spec=self.cfg['obstacles'][name]
            if abs(p.x-spec['center_x_m'])<spec['length_m']/3 and abs(p.y)<spec['width_m']/2:
                if name=='ramp':self.ramp_z=max(self.ramp_z,p.z)
                else:self.step_z=max(self.step_z,p.z)
        obstacles=self.cfg['obstacles']
        cones=list(obstacles['cones'])+([self.cfg['goal_xy_m']] if self.cfg['goal']['camera_confirmation'] else [])
        for x,y in cones:
            half=obstacles['cone_base_m']/2
            clearance=math.hypot(max(abs(p.x-x)-half,0),max(abs(p.y-y)-half,0))-self.cfg['footprint_radius_m']
            self.min_clearance=min(self.min_clearance,clearance)
        for x,y,sx,sy,_ in obstacles['boxes']:
            clearance=math.hypot(max(abs(p.x-x)-sx/2,0),max(abs(p.y-y)-sy/2,0))-self.cfg['footprint_radius_m']
            self.min_clearance=min(self.min_clearance,clearance)
        estimate=self.nav.get('estimated_position_m') or [None]*3
        if estimate[0] is not None:self.max_error=max(self.max_error,math.dist(estimate,self.truth))
        stamp=msg.header.stamp.sec+msg.header.stamp.nanosec*1e-9
        v=msg.twist.twist.linear;w=msg.twist.twist.angular
        self.truth_speeds.append((stamp,math.sqrt(v.x*v.x+v.y*v.y+v.z*v.z),math.sqrt(w.x*w.x+w.y*w.y+w.z*w.z)))
        self.truth_times.append(stamp)
        self.writer.writerow([stamp,*self.truth,*estimate,self.nav.get('phase','initializing'),self.nav.get('command_linear_mps',0),self.nav.get('command_angular_radps',0),self.truth_speeds[-1][1],self.truth_speeds[-1][2]])
        self.rows+=1
        if self.rows%20==0:self.file.flush()

    def write_result(self):
        goal_error=None if self.truth is None else math.dist(self.truth[:2],self.cfg['goal_xy_m'])
        photos=self.out/'photos.csv';capture_motion=None;physical_capture_motion=None;capture_details=[]
        if photos.exists():
            try:
                records=list(csv.DictReader(photos.open()))
                capture_motion=sum(abs(float(r['encoder_speed_mps']))>.005 or abs(float(r.get('encoder_turn_radps',0)))>.02 or r['phase']!='photograph' for r in records)
                if self.truth_speeds:
                    speeds=[]
                    for record in records:
                        t=float(record['image_stamp_s']);index=bisect.bisect_left(self.truth_times,t)
                        speeds.append(min(self.truth_speeds[max(0,index-1):min(index+1,len(self.truth_speeds))],key=lambda s:abs(s[0]-t)))
                    physical_capture_motion=sum(s[1]>.005 or s[2]>.02 for s in speeds)
                    capture_details=[dict(file=r['file'],image_stamp_s=float(r['image_stamp_s']),truth_stamp_s=s[0],linear_mps=s[1],angular_radps=s[2])
                                     for r,s in zip(records,speeds) if s[1]>.005 or s[2]>.02]
            except (ValueError,KeyError):pass
        crossings={}
        for name,measured in [('ramp',self.ramp_z),('step',self.step_z)]:
            spec=self.cfg['obstacles'][name]
            required=spec['width_m']>=self.cfg['map_bounds_m'][3]-self.cfg['map_bounds_m'][1] and self.cfg['goal_xy_m'][0]>spec['center_x_m']+spec['length_m']/2
            crossings[name]=dict(required=required,confirmed=measured>=spec['height_m']*.45,measured_base_height_m=measured)
        passed=bool(self.nav.get('done') and self.nav.get('phase')=='goal' and goal_error is not None
                    and goal_error<=self.cfg['goal_tolerance_m']+.05 and self.nodes>=3 and self.cloud>0
                    and capture_motion==0 and physical_capture_motion==0 and self.min_clearance>=-.02
                    and all(not c['required'] or c['confirmed'] for c in crossings.values()))
        result=dict(passed=passed,navigation=self.nav,truth_position_m=self.truth,true_goal_distance_m=goal_error,
                    distance_travelled_m=self.distance,slam_graph_nodes=self.nodes,slam_cloud_points=self.cloud,
                    slam_map_updates=self.map_updates,captures_while_commanded_moving=capture_motion,
                    captures_while_physically_moving=physical_capture_motion,
                    capture_motion_details=capture_details,
                    max_estimation_error_m=self.max_error,min_conservative_obstacle_clearance_m=None if not math.isfinite(self.min_clearance) else self.min_clearance,
                    max_base_height_m=self.max_z,base_height_over_ramp_m=self.ramp_z,base_height_over_step_m=self.step_z,
                    terrain_crossings=crossings,
                    evidence='actual Gazebo contact dynamics and cameras; truth used only by this evaluator',
                    limitations=['uncalibrated rigid-track geometry and friction','no real motor torque/current model','ideal virtual IMU/encoder','no semantic grass recognition'])
        temp=self.out/'result.tmp';temp.write_text(json.dumps(result,indent=2));temp.replace(self.out/'result.json');self.file.flush()


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--config',required=True);a.add_argument('--out',required=True);args,ros=a.parse_known_args()
    rclpy.init(args=ros);n=Evaluate(load(args.config),args.out)
    try:rclpy.spin(n)
    except KeyboardInterrupt:pass
    finally:n.write_result();n.file.close();n.destroy_node();rclpy.try_shutdown()
