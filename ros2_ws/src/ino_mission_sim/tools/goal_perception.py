"""Image-only cone hypotheses, spatial prior gating, and multiple-view confirmation.

Cones have identical colors. No Gazebo model ID or true object position is read.
The basal ray model assumes a locally level support plane and known cone base.
"""
import math
import cv2
import numpy as np
from scipy.spatial.transform import Rotation


def cone_candidates(rgb,K,camera_rotation,camera_position,body_rotation,base_radius,base_height):
    hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    mask=cv2.inRange(hsv,np.array([0,100,50],np.uint8),np.array([15,255,255],np.uint8))
    mask|=cv2.inRange(hsv,np.array([170,100,50],np.uint8),np.array([179,255,255],np.uint8))
    count,labels,stats,_=cv2.connectedComponentsWithStats(mask,8)
    result=[];inverse=np.linalg.inv(K);camera=body_rotation.apply(camera_position)
    for index in range(1,count):
        x,y,w,h,area=stats[index]
        # A clipped basal skirt biases its apparent center and range. Wait for
        # a view that contains the complete horizontal extent before ranging.
        if area<80 or w<5 or h<8 or x<=2 or x+w>=rgb.shape[1]-3 or y+h>=rgb.shape[0]-3:continue
        yy,xx=np.nonzero(labels==index)
        bottom=float(np.quantile(yy,.99));u=float(np.median(xx[yy>=bottom-2]))
        ray=body_rotation.apply(camera_rotation@(inverse@np.array([u,bottom,1.])))
        if ray[2]>=-.02:continue
        t=(base_height-camera[2])/ray[2]
        if t<=0:continue
        edge=camera+t*ray;distance=float(np.linalg.norm(edge[:2]))
        if not .1<distance<2.5:continue
        center=edge.copy();center[:2]+=base_radius*edge[:2]/distance
        result.append(dict(relative=center,pixel=[u,bottom],area=int(area)))
    return result


class GoalAssociation:
    def __init__(self,prior,radius=.6,views=2):
        self.prior=np.array(prior,float);self.radius=radius;self.required=views
        self.point=None;self.last_pose=None;self.views=0;self.confirmed=False
        self.candidates=0;self.reason='coordinate_navigation';self.last_stamp=-1.

    def update(self,candidates,raw_position,body_rotation,map_rotation,map_translation,stamp):
        raw_position=np.array(raw_position,float)
        eligible=[]
        for candidate in candidates:
            point=raw_position+candidate['relative']
            mapped=map_rotation.apply(point)+map_translation
            if np.linalg.norm(mapped[:2]-self.prior)<=self.radius:eligible.append(point)
        self.candidates=len(eligible)
        if len(eligible)>1:
            self.confirmed=False;self.views=0;self.last_pose=None;self.reason='ambiguous_cones_near_goal';return
        if not eligible:
            self.reason='confirmed_goal_last_seen' if self.confirmed else 'coordinate_navigation';return
        point=eligible[0]
        if self.point is not None and np.linalg.norm(point[:2]-self.point[:2])>.2:
            self.views=0;self.confirmed=False;self.last_pose=None
        yaw=body_rotation.as_euler('xyz')[2]
        pose=np.array([*raw_position[:2],yaw])
        distinct=self.last_pose is None or np.linalg.norm(pose[:2]-self.last_pose[:2])>=.05 or abs(math.atan2(math.sin(yaw-self.last_pose[2]),math.cos(yaw-self.last_pose[2])))>=math.radians(5)
        if distinct:self.views+=1;self.last_pose=pose
        self.point=point;self.last_stamp=stamp;self.confirmed=self.views>=self.required
        self.reason='camera_goal_confirmed' if self.confirmed else 'confirming_goal_from_another_view'

    def mapped(self,rotation,translation):
        if self.point is None or not self.confirmed:return self.prior.copy()
        return (rotation.apply(self.point)+translation)[:2]


def needs_goal_view(distance,stop_radius,confirmed,visual_ready):
    # A confirmed goal may leave the image while following a detour. Requiring
    # it at every turn outside the arrival radius creates a view/path deadlock.
    # Arrival itself still requires a new, unambiguous stopped observation.
    return not visual_ready and (distance<stop_radius or (not confirmed and distance<stop_radius+.1))


def goal_view_angle(position,goal,yaw,camera_yaw=0.,candidates=0,confirmed=False):
    """Shortest bounded turn toward the expected goal; None means hold.

    A second view can be acquired with a 10-degree dither while keeping the
    cone near the image center. Missing/ambiguous objects at the expected
    bearing do not authorize driving or an endless full-circle search.
    """
    bearing=math.atan2(goal[1]-position[1],goal[0]-position[0])
    error=math.atan2(math.sin(bearing-yaw-camera_yaw),math.cos(bearing-yaw-camera_yaw))
    limit=math.radians(10.)
    if abs(error)>math.radians(5.):return float(np.clip(error,-limit,limit))
    if candidates==1 and not confirmed:return limit
    return None


def approach_plan(grid,start,goal,radius):
    """Plan to a ring around a physical goal, never into its occupied center."""
    direction=math.atan2(start[1]-goal[1],start[0]-goal[0])
    targets=[(goal[0]+radius*math.cos(direction+a),goal[1]+radius*math.sin(direction+a))
             for a in np.linspace(-math.pi,math.pi,24,endpoint=False)]
    targets.sort(key=lambda p:math.dist(start,p))
    choices=[]
    for target in targets:
        path=grid.plan(start,target)
        if path:
            # Grid cell rounding must not place the endpoint outside the ring.
            if math.dist(path[-1],goal)>radius+grid.res*.75:continue
            score=sum(math.dist(a,b) for a,b in zip(path,path[1:]))
            choices.append((score,path))
            if len(choices)>=3:break
    return min(choices,key=lambda choice:choice[0])[1] if choices else []
