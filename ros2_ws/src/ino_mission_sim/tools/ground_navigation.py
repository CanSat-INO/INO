"""Stop / photograph / replan / short-drive navigation from stereo + odometry.

Ground truth, obstacle lists and world geometry are never read by this node.
Unknown terrain may be proposed in a global path; it cannot authorize a drive.
"""
import argparse
import copy
import csv
import json
import math
from pathlib import Path
import time
import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from cv_bridge import CvBridge
from geometry_msgs.msg import Point, PoseStamped, Twist
from nav_msgs.msg import OccupancyGrid, Odometry, Path as PathMessage
from rtabmap_msgs.msg import RGBDImage,MapData
from std_msgs.msg import ColorRGBA, String
from visualization_msgs.msg import Marker, MarkerArray
from tf2_ros import Buffer, TransformListener, TransformException
from rclpy.time import Time
from scipy.spatial.transform import Rotation
from design_config import load as load_camera, rig
from ground_world import load
from ground_grid import TerrainGrid
from ground_observations import ObservationHistory
from ground_motion import TerrainHeadingLock,TurnProgress,arc_points,CornerTarget
from goal_perception import GoalAssociation,cone_candidates,approach_plan,needs_goal_view,goal_view_angle
from rviz_mesh import ensure_stl


def stamp_seconds(stamp):return stamp.sec+stamp.nanosec*1e-9
def wrap(angle):return math.atan2(math.sin(angle),math.cos(angle))


class GroundNavigation(Node):
    def __init__(self,cfg,out):
        super().__init__('ground_navigation')
        self.cfg=cfg;self.out=Path(out);self.grid=TerrainGrid(cfg);self.bridge=CvBridge()
        self.goal=GoalAssociation(cfg['goal_xy_m'],cfg['goal']['association_radius_m'],cfg['goal']['confirmation_views'])
        self.camera_goal=cfg['goal']['camera_confirmation']
        self.goal_xy=np.array(cfg['goal_xy_m'],float)
        self.stop_radius=cfg['goal_tolerance_m']-cfg['goal']['stop_margin_m'] if self.camera_goal else cfg['goal_tolerance_m']
        self.drive_diagnostic={}
        self.rebuild_wall_s=0.
        self.heading_lock=TerrainHeadingLock();self.turn_progress=TurnProgress()
        self.corner=CornerTarget()
        scene=load_camera(self.out/'effective.yaml');geometry=rig(scene)
        self.camera_rotation=geometry['raw_rotations']['left']@geometry['R1'].T
        self.camera_yaw=math.atan2(self.camera_rotation[1,2],self.camera_rotation[0,2])
        self.camera_position=geometry['positions']['left']
        self.matcher=cv2.StereoSGBM_create(minDisparity=0,numDisparities=128,blockSize=5,
            P1=8*25,P2=32*25,disp12MaxDiff=1,uniquenessRatio=12,speckleWindowSize=70,speckleRange=2,
            mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY)
        self.right_matcher=cv2.StereoSGBM_create(minDisparity=-128,numDisparities=128,blockSize=5,
            P1=8*25,P2=32*25,disp12MaxDiff=1,uniquenessRatio=12,speckleWindowSize=70,speckleRange=2,
            mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY)
        cv2.setNumThreads(2)
        self.odom=None;self.odom_stamp=None;self.started=None;self.started_wall=time.monotonic()
        self.tf_buffer=Buffer();self.tf_listener=TransformListener(self.tf_buffer,self)
        self.map_rotation=Rotation.identity();self.map_translation=np.zeros(3);self.map_ready=False
        self.grid_rotation=Rotation.identity();self.grid_translation=np.zeros(3)
        self.observations=ObservationHistory();self.rebuilds=0;self.last_rebuilt_photo=-1
        self.last_slam_stamp=-1.
        self.last_pair=-1.;self.last_mapped=-1.;self.photos=0;self.points=0;self.plan=[]
        self.phase='photograph';self.stop_since=0.;self.drive_until=0.;self.pending=Twist()
        self.done=False;self.reason='';self.state={};self.last_status=-1.;self.map_nodes=0
        self.path=PathMessage();self.path.header.frame_id='odom'
        qos=QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.command_pub=self.create_publisher(Twist,'/cmd_vel',10)
        self.grid_pub=self.create_publisher(OccupancyGrid,'/ground/traversability',qos)
        self.color_pub=self.create_publisher(MarkerArray,'/ground/terrain_colors',qos)
        self.plan_pub=self.create_publisher(PathMessage,'/ground/planned_path',qos)
        self.path_pub=self.create_publisher(PathMessage,'/ground/driven_path',qos)
        self.robot_pub=self.create_publisher(Marker,'/ground/robot',qos)
        self.status_pub=self.create_publisher(String,'/ground/status',10)
        self.create_subscription(Odometry,'/odom',self.receive_odom,1)
        self.create_subscription(RGBDImage,'/capture/rgbd_image',self.receive_pair,1)
        self.create_subscription(MapData,'/mapData',self.receive_slam,1)
        self.create_timer(.05,self.tick)
        self.photo_file=(self.out/'photos.csv').open('w',newline='');self.photo_writer=csv.writer(self.photo_file)
        self.photo_writer.writerow(['image_stamp_s','phase','encoder_speed_mps','encoder_turn_radps','points','file'])
        self.plan_file=(self.out/'plans.jsonl').open('w')
        self.goal_file=(self.out/'goal-observations.jsonl').open('w')
        (self.out/'photos').mkdir(exist_ok=True)

    def receive_odom(self,msg):
        self.odom=msg;self.odom_stamp=stamp_seconds(msg.header.stamp)
        p=msg.pose.pose.position
        if not self.path.poses or math.dist((p.x,p.y,p.z),tuple(getattr(self.path.poses[-1].pose.position,k) for k in ('x','y','z')))>.015:
            pose=PoseStamped();pose.header=copy.deepcopy(msg.header);pose.pose=copy.deepcopy(msg.pose.pose)
            self.path.header=msg.header;self.path.poses.append(pose)

    def receive_slam(self,msg):
        self.last_slam_stamp=max(stamp_seconds(msg.header.stamp),stamp_seconds(msg.graph.header.stamp))
        self.observations.update(msg.nodes,msg.graph.poses_id,msg.graph.poses)

    def rebuild_map(self):
        started=time.monotonic()
        clouds=list(self.observations.clouds(self.map_rotation,self.map_translation))
        self.grid=TerrainGrid(self.cfg)
        if clouds:self.grid.integrate(np.concatenate(clouds))
        self.observations.dirty=False;self.rebuilds+=1;self.publish_map()
        self.last_rebuilt_photo=self.photos
        self.rebuild_wall_s=time.monotonic()-started

    def receive_pair(self,msg):
        if self.odom is None or self.done:return
        stamp=stamp_seconds(msg.header.stamp)
        if self.phase!='photograph' or stamp<=self.last_pair or stamp<self.stop_since+self.cfg['settle_s']-.05:return
        if self.last_mapped>self.stop_since+self.cfg['settle_s']-.05:return
        if abs(stamp-self.odom_stamp)>.18:return
        if abs(self.odom.twist.twist.linear.x)>.005 or abs(self.odom.twist.twist.angular.z)>.02:return
        self.last_pair=stamp
        left=self.bridge.imgmsg_to_cv2(msg.rgb,'mono8');right=self.bridge.imgmsg_to_cv2(msg.depth,'mono8')
        disparity=self.matcher.compute(left,right).astype(np.float32)/16.
        reverse=self.right_matcher.compute(right,left).astype(np.float32)/16.
        info=msg.rgb_camera_info;fx=info.p[0];fy=info.p[5];cx=info.p[2];cy=info.p[6]
        baseline=-msg.depth_camera_info.p[3]/msg.depth_camera_info.p[0]
        vv,uu=np.indices(disparity.shape);depth=fx*baseline/np.maximum(disparity,.01)
        match_x=np.rint(uu-disparity).astype(int)
        valid_x=(match_x>=0)&(match_x<left.shape[1])
        reverse_match=reverse[vv,np.clip(match_x,0,left.shape[1]-1)]
        consistent=valid_x&(np.abs(disparity+reverse_match)<.8)
        # Textureless sky and flat-color stereo objects create long disparity
        # streaks. Keep locally supported matches; silhouettes remain visible.
        mean=cv2.blur(left.astype(np.float32),(7,7))
        variance=cv2.blur(left.astype(np.float32)**2,(7,7))-mean**2
        keep=consistent&(variance>4.)&(disparity>2.)&(depth>.12)&(depth<self.cfg['max_observation_range_m'])&((vv%2)==0)&((uu%2)==0)
        optical=np.column_stack(((uu[keep]-cx)*depth[keep]/fx,(vv[keep]-cy)*depth[keep]/fy,depth[keep]))
        base=optical@self.camera_rotation.T+self.camera_position
        base=base[(base[:,0]>.14)&(np.abs(base[:,1])<1.8)&(base[:,2]>-.15)&(base[:,2]<1.)]
        q=self.odom.pose.pose.orientation;rot=Rotation.from_quat([q.x,q.y,q.z,q.w])
        p=self.odom.pose.pose.position;points=rot.apply(base)+[p.x,p.y,p.z]
        if len(points)<100:return
        if not self.map_ready:return
        rgb=self.bridge.imgmsg_to_cv2(msg.rgb,'rgb8')
        goal_observation=None
        if self.camera_goal:
            K=np.array([[fx,0,cx],[0,fy,cy],[0,0,1.]])
            candidates=cone_candidates(rgb,K,self.camera_rotation,self.camera_position,rot,
                self.cfg['obstacles']['cone_base_m']*self.cfg['goal']['cone_visible_radius_ratio'],self.cfg['goal']['cone_base_height_m'])
            self.goal.update(candidates,[p.x,p.y,p.z],rot,self.map_rotation,self.map_translation,stamp)
            self.goal_xy=self.goal.mapped(self.map_rotation,self.map_translation)
            projected=[]
            for candidate in candidates:
                mapped=self.map_rotation.apply(np.array([p.x,p.y,p.z])+candidate['relative'])+self.map_translation
                projected.append(dict(pixel=candidate['pixel'],map_xy_m=mapped[:2].tolist(),
                    within_coordinate_prior=bool(np.linalg.norm(mapped[:2]-self.goal.prior)<=self.goal.radius)))
            goal_observation=dict(stamp_s=stamp,candidates=projected,confirmed=self.goal.confirmed,views=self.goal.views,
                                  reason=self.goal.reason,target_xy_m=self.goal_xy.tolist())
        self.observations.append(stamp,points[::2])
        self.grid.integrate(self.map_rotation.apply(points)+self.map_translation)
        self.points=len(points);self.last_mapped=stamp;self.photos+=1
        name=f'{self.photos:04d}-{stamp:.3f}.png'
        if goal_observation is not None:
            goal_observation['file']=name;self.goal_file.write(json.dumps(goal_observation)+'\n');self.goal_file.flush()
        cv2.imwrite(str(self.out/'photos'/name),self.bridge.imgmsg_to_cv2(msg.rgb,'bgr8'))
        cv2.imwrite(str(self.out/'photos'/name.replace('.png','-right.png')),self.bridge.imgmsg_to_cv2(msg.depth,'bgr8'))
        self.photo_writer.writerow([stamp,self.phase,self.odom.twist.twist.linear.x,self.odom.twist.twist.angular.z,len(points),name]);self.photo_file.flush()
        self.publish_map()

    def publish_map(self):
        now=self.get_clock().now().to_msg();grid=OccupancyGrid();grid.header.frame_id='map';grid.header.stamp=now
        grid.info.resolution=self.grid.res;grid.info.height,grid.info.width=self.grid.shape
        grid.info.origin.position.x=self.grid.x0;grid.info.origin.position.y=self.grid.y0;grid.info.origin.orientation.w=1.
        grid.data=self.grid.cost.ravel().tolist();self.grid_pub.publish(grid)
        markers=MarkerArray();terrain=Marker();terrain.header=grid.header;terrain.ns='terrain';terrain.id=0
        terrain.type=Marker.CUBE_LIST;terrain.action=Marker.ADD;terrain.pose.orientation.w=1.
        terrain.scale.x=terrain.scale.y=self.grid.res*.95;terrain.scale.z=.008
        for row,col in np.argwhere(self.grid.seen):
            x,y=self.grid.xy((row,col));terrain.points.append(Point(x=x,y=y,z=.008))
            cost=int(self.grid.cost[row,col])
            color=(.88,.12,.12) if cost>=100 else ((1.,.65,.06) if cost>=35 else (.12,.75,.3))
            terrain.colors.append(ColorRGBA(r=color[0],g=color[1],b=color[2],a=.8))
        markers.markers.append(terrain)
        text=Marker();text.header=grid.header;text.ns='legend';text.id=1;text.type=Marker.TEXT_VIEW_FACING;text.action=Marker.ADD
        text.pose.orientation.w=1.;text.pose.position.x=1.5;text.pose.position.y=1.6;text.pose.position.z=.25
        text.scale.z=.12;text.color=ColorRGBA(r=1.,g=1.,b=1.,a=1.)
        text.text='GREEN: easy | ORANGE: difficult | RED: blocked\nUncolored: unknown | MAGENTA: planned (unknown sections provisional)'
        markers.markers.append(text)
        goal=Marker();goal.header=grid.header;goal.ns='goal';goal.id=2;goal.type=Marker.CYLINDER;goal.action=Marker.ADD
        goal.pose.orientation.w=1.;goal.pose.position.x=float(self.goal_xy[0]);goal.pose.position.y=float(self.goal_xy[1])
        goal.scale.x=goal.scale.y=self.cfg['goal_tolerance_m']*2;goal.scale.z=.02;goal.color=ColorRGBA(r=.2,g=.9,b=.9,a=.6)
        markers.markers.append(goal);self.color_pub.publish(markers)

    def publish_plan(self):
        msg=PathMessage();msg.header.frame_id='map';msg.header.stamp=self.get_clock().now().to_msg()
        for x,y in self.plan:
            p=PoseStamped();p.header=msg.header;p.pose.position.x=x;p.pose.position.y=y;p.pose.position.z=.03;p.pose.orientation.w=1.
            msg.poses.append(p)
        self.plan_pub.publish(msg)
        self.plan_file.write(json.dumps(dict(time_s=self.get_clock().now().nanoseconds*1e-9,
                                            path=self.plan,observed_cells=int(self.grid.seen.sum())))+'\n');self.plan_file.flush()

    def follow_corner(self,now,xy,yaw,raw_yaw):
        target=self.corner.point;delta=wrap(math.atan2(target[1]-xy[1],target[0]-xy[0])-yaw)
        if abs(delta)>math.radians(3):
            self.pending.angular.z=math.copysign(self.cfg['turn_rate_radps'],delta)
            angle=min(abs(delta),math.radians(self.cfg['turn_step_deg']))
            self.drive_until=now+angle/self.cfg['turn_rate_radps'];self.turn_progress.begin(raw_yaw,angle)
            self.phase='turn';self.reason='align_with_nearest_path_cell';return self.pending
        speed=self.cfg['speed_mps'];authorized=False
        for fraction in (1.,.5,.25):
            duration=min(self.cfg['drive_step_m'],math.dist(xy,target))*fraction/speed
            arc=arc_points(xy,yaw,speed,0.,duration)
            if all(self.grid.observed_segment(a,b) for a,b in zip(arc,arc[1:])):authorized=True;break
        self.drive_diagnostic=dict(yaw_rad=float(yaw),heading_error_rad=float(delta),arc=arc,authorized=authorized)
        if authorized:
            self.pending.linear.x=speed;self.drive_until=now+duration;self.phase='drive';self.reason='follow_nearest_safe_path_cell';return self.pending
        self.reason='waiting_for_observed_ground';self.stop_since=now;return Twist()

    def tick(self):
        now=self.get_clock().now().nanoseconds*1e-9
        try:
            transform=self.tf_buffer.lookup_transform('map','odom',Time()).transform
            q=transform.rotation;rotation=Rotation.from_quat([q.x,q.y,q.z,q.w])
            t=transform.translation;translation=np.array([t.x,t.y,t.z])
            self.map_rotation=rotation;self.map_translation=translation;self.map_ready=True
            self.goal_xy=self.goal.mapped(rotation,translation)
            if np.linalg.norm(translation-self.grid_translation)>.03 or (rotation*self.grid_rotation.inv()).magnitude()>math.radians(2):
                self.observations.dirty=True
                self.grid_rotation=rotation;self.grid_translation=translation
                if not self.done:self.last_mapped=-1.;self.phase='photograph';self.stop_since=now
        except TransformException:pass
        if self.started is None and self.odom is not None:self.started=now;self.stop_since=now
        cmd=Twist()
        if self.started is not None:
            if now-self.started>self.cfg['duration_s'] and not self.done:self.done=True;self.reason='simulation_timeout';self.phase='stopped'
            fresh=self.map_ready and self.odom_stamp is not None and 0<=now-self.odom_stamp<self.cfg['max_sensor_age_s']
            if not fresh:
                if not self.done:
                    # Already-stopped image work remains valid while queued
                    # clock/odometry catches up after expensive reprojection.
                    # Reset only when a moving phase had to be interrupted.
                    if self.phase in ('drive','turn'):self.phase='photograph';self.stop_since=now
                    self.reason='waiting_for_fresh_odometry'
            elif not self.done:
                raw=self.odom.pose.pose.position;xyz=self.map_rotation.apply([raw.x,raw.y,raw.z])+self.map_translation
                q=self.odom.pose.pose.orientation;raw_rotation=Rotation.from_quat([q.x,q.y,q.z,q.w]);raw_yaw=float(raw_rotation.as_euler('xyz')[2])
                was_locked=self.heading_lock.active;self.heading_lock.update([raw.x,raw.y],raw_rotation)
                if self.heading_lock.active and not was_locked and self.phase in ('drive','turn'):
                    self.phase='photograph';self.stop_since=now;self.last_mapped=-1.
                self.grid.occupy(xyz)
                xy=(float(xyz[0]),float(xyz[1]));px,py=xy
                ready=self.last_mapped>self.stop_since+self.cfg['settle_s']-.05 and self.last_slam_stamp>=self.last_mapped-.15
                if ready and self.observations.dirty and self.phase=='photograph' and self.last_rebuilt_photo!=self.photos:
                    self.rebuild_map();self.grid.occupy(xyz)
                    # Reprojection can take time. Drain latest odometry/clock
                    # callbacks before starting a timed drive, rather than
                    # scheduling it from the timestamp before that computation.
                    self.command_pub.publish(cmd);self.publish_status(now,cmd);return
                current_stopped_view=self.phase=='photograph' and self.goal.last_stamp>=self.stop_since+self.cfg['settle_s']-.05
                visual_ready=self.goal.confirmed and self.goal.candidates==1 and (now-self.goal.last_stamp<3. or current_stopped_view)
                arrived=math.dist(xy,self.goal_xy)<self.stop_radius and (not self.camera_goal or visual_ready)
                if arrived:
                    if self.phase!='photograph':
                        self.phase='photograph';self.stop_since=now;self.last_mapped=-1.;self.reason='confirm_goal_with_stopped_slam'
                    elif ready:
                        self.done=True;self.reason='goal_reached_camera_and_coordinate' if self.camera_goal else 'goal_reached_estimate';self.phase='goal'
                elif self.phase in ('drive','turn'):
                    if now<self.drive_until:
                        cmd=copy.deepcopy(self.pending)
                    else:
                        self.turn_progress.finish(raw_yaw)
                        self.phase='photograph';self.stop_since=now
                        if self.turn_progress.blocked>=2:
                            self.done=True;self.phase='stopped';self.reason='imu_detected_blocked_turn'
                elif ready:
                    near_unconfirmed=self.camera_goal and needs_goal_view(math.dist(xy,self.goal_xy),self.stop_radius,self.goal.confirmed,visual_ready)
                    if near_unconfirmed:
                        yaw=(self.map_rotation*raw_rotation).as_euler('xyz')[2]
                        angle=goal_view_angle(xy,self.goal_xy,yaw,self.camera_yaw,self.goal.candidates,self.goal.confirmed)
                        if angle is None or self.heading_lock.active:
                            self.reason='ambiguous_cones_near_goal' if self.goal.candidates>1 else 'goal_not_visible_at_expected_bearing'
                            self.stop_since=now
                        else:
                            angle=math.copysign(min(abs(angle),math.radians(self.cfg['turn_step_deg'])),angle)
                            self.pending=Twist();self.pending.angular.z=math.copysign(self.cfg['turn_rate_radps'],angle)
                            self.drive_until=now+abs(angle)/self.cfg['turn_rate_radps']
                            self.turn_progress.begin(raw_yaw,abs(angle))
                            self.phase='turn';self.reason='align_goal_camera';cmd=self.pending
                        self.command_pub.publish(cmd);self.publish_status(now,cmd);return
                    self.plan=approach_plan(self.grid,xy,self.goal_xy,self.stop_radius-self.grid.res*.75) if self.camera_goal else self.grid.plan(xy,self.goal_xy)
                    self.publish_plan()
                    if not self.plan:self.reason='no_safe_path';self.stop_since=now
                    else:
                        q=self.odom.pose.pose.orientation;yaw=(self.map_rotation*Rotation.from_quat([q.x,q.y,q.z,q.w])).as_euler('xyz')[2]
                        target=next((point for point in self.plan if math.dist(xy,point)>=.24),self.plan[-1])
                        delta=wrap(math.atan2(target[1]-py,target[0]-px)-yaw)
                        self.pending=Twist();self.reason=''
                        corner=self.corner.current(xy,self.grid.res,self.grid.observed_segment)
                        if self.heading_lock.active:
                            wanted=self.map_rotation.apply([math.cos(self.heading_lock.heading),math.sin(self.heading_lock.heading),0.])
                            omega=float(np.clip(wrap(math.atan2(wanted[1],wanted[0])-yaw)*.5,-.05,.05))
                            speed=self.cfg['speed_mps'];duration=self.cfg['drive_step_m']/speed
                            arc=arc_points(xy,yaw,speed,omega,duration)
                            authorized=all(self.grid.observed_segment(a,b) for a,b in zip(arc,arc[1:]))
                            if authorized:
                                self.pending.linear.x=speed;self.pending.angular.z=omega;self.drive_until=now+duration
                                self.phase='drive';self.reason='cross_terrain_before_turning';cmd=self.pending
                            else:self.reason='terrain_crossing_needs_observed_straight_path';self.stop_since=now
                            self.drive_diagnostic=dict(yaw_rad=float(yaw),heading_error_rad=float(delta),arc=arc,authorized=authorized)
                        elif corner is not None:cmd=self.follow_corner(now,xy,yaw,raw_yaw)
                        elif abs(delta)>math.radians(25):
                            self.pending.angular.z=math.copysign(self.cfg['turn_rate_radps'],delta)
                            self.drive_until=now+min(abs(delta),math.radians(self.cfg['turn_step_deg']))/self.cfg['turn_rate_radps']
                            self.turn_progress.begin(raw_yaw,min(abs(delta),math.radians(self.cfg['turn_step_deg'])))
                            self.phase='turn';cmd=self.pending
                        else:
                            length=min(self.cfg['drive_step_m'],max(.01,math.dist(xy,self.goal_xy)-self.stop_radius+.03))
                            speed=self.cfg['speed_mps'];duration=length/speed
                            omega=float(np.clip(2*speed*math.sin(delta)/.24,-.1,.1))
                            authorized=False
                            for fraction in (1.,.75,.5,.25):
                                duration=length*fraction/speed;arc=[]
                                for t in np.linspace(0.,duration,6):
                                    if abs(omega)<1e-5:arc.append((px+speed*t*math.cos(yaw),py+speed*t*math.sin(yaw)))
                                    else:arc.append((px+speed/omega*(math.sin(yaw+omega*t)-math.sin(yaw)),py-speed/omega*(math.cos(yaw+omega*t)-math.cos(yaw))))
                                if all(self.grid.observed_segment(a,b) for a,b in zip(arc,arc[1:])):authorized=True;break
                            if authorized:
                                self.pending.linear.x=speed;self.pending.angular.z=omega;self.drive_until=now+duration
                                self.phase='drive';cmd=self.pending
                            else:
                                # The distant lookahead can cut an A* corner.
                                # Align with its next safe cell, then take a
                                # shorter straight step along that actual edge.
                                self.corner.choose(self.plan,xy,self.grid.res)
                                cmd=self.follow_corner(now,xy,yaw,raw_yaw)
                            self.drive_diagnostic=dict(yaw_rad=float(yaw),heading_error_rad=float(delta),arc=arc,authorized=authorized)
        self.command_pub.publish(cmd)
        if now-self.last_status>.25:
            self.last_status=now;self.publish_status(now,cmd)

    def publish_status(self,now,cmd):
        position=None;distance=None
        if self.odom is not None:
            p=self.odom.pose.pose.position;position=(self.map_rotation.apply([p.x,p.y,p.z])+self.map_translation).tolist();distance=math.dist(position[:2],self.goal_xy)
            marker=Marker();marker.header=self.odom.header;marker.ns='robot';marker.id=0;marker.type=Marker.MESH_RESOURCE;marker.action=Marker.ADD
            marker.pose=self.odom.pose.pose;marker.scale.x=marker.scale.y=marker.scale.z=1.
            marker.mesh_resource=ensure_stl('deployed').as_uri();marker.color=ColorRGBA(r=.8,g=.6,b=.3,a=1.)
            self.robot_pub.publish(marker)
        self.path_pub.publish(self.path)
        state=dict(phase=self.phase,reason=self.reason,done=self.done,sim_time_s=now,
                   elapsed_s=None if self.started is None else now-self.started,estimated_position_m=position,
                   goal_distance_estimated_m=distance,photos=self.photos,latest_stereo_points=self.points,
                   observed_cells=int(self.grid.seen.sum()),blocked_cells=int(self.grid.blocked.sum()),
                   difficult_cells=int(((self.grid.cost>=35)&(self.grid.cost<100)).sum()),planned_path_points=len(self.plan),
                   command_linear_mps=cmd.linear.x,command_angular_radps=cmd.angular.z,
                   last_image_age_s=None if self.last_mapped<0 else now-self.last_mapped,
                   slam_transform_ready=self.map_ready,
                   terrain_rebuilds=self.rebuilds,terrain_slam_keyframes=len(self.observations.anchors),
                   last_terrain_rebuild_wall_s=self.rebuild_wall_s,
                   terrain_heading_lock=self.heading_lock.active,blocked_turn_attempts=self.turn_progress.blocked,
                   goal_prior_xy_m=self.cfg['goal_xy_m'],goal_target_xy_m=self.goal_xy.tolist(),
                   camera_goal_required=self.camera_goal,camera_goal_confirmed=self.goal.confirmed,
                   camera_goal_views=self.goal.views,camera_goal_candidates=self.goal.candidates,camera_goal_reason=self.goal.reason,
                   drive_diagnostic=self.drive_diagnostic,
                   last_slam_observation_age_s=None if self.last_slam_stamp<0 else now-self.last_slam_stamp,
                   estimator='track encoder + IMU, corrected by RTAB-Map map-to-odom; ground truth is not an input',
                   capture_mode='stop and photograph')
        self.state=state;self.status_pub.publish(String(data=json.dumps(state)))
        temp=self.out/'navigation.tmp';temp.write_text(json.dumps(state,indent=2));temp.replace(self.out/'navigation.json')
        np.savez_compressed(self.out/'terrain.npz',height=self.grid.height,seen=self.grid.seen,cost=self.grid.cost,slope=self.grid.slope,step=self.grid.step)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--config',required=True);a.add_argument('--out',required=True);args,ros=a.parse_known_args()
    rclpy.init(args=ros);n=GroundNavigation(load(args.config),args.out)
    try:rclpy.spin(n)
    except KeyboardInterrupt:pass
    finally:n.command_pub.publish(Twist());n.photo_file.close();n.plan_file.close();n.goal_file.close();n.destroy_node();rclpy.try_shutdown()
