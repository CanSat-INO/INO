"""IMU-based turn progress and candidate arcs, independent of simulator truth."""
import math
import numpy as np


def wrap(angle):return math.atan2(math.sin(angle),math.cos(angle))


def arc_points(xy,yaw,speed,omega,duration):
    x,y=xy;points=[]
    for t in np.linspace(0.,duration,7):
        if abs(omega)<1e-5:points.append((x+speed*t*math.cos(yaw),y+speed*t*math.sin(yaw)))
        else:points.append((x+speed/omega*(math.sin(yaw+omega*t)-math.sin(yaw)),y-speed/omega*(math.cos(yaw+omega*t)-math.cos(yaw))))
    return points


def next_path_cell(path,xy,resolution):
    candidates=path[1:] if len(path)>1 else path
    return next((point for point in candidates if math.dist(point,xy)>resolution*.3),path[-1])


class CornerTarget:
    def __init__(self):self.point=None

    def current(self,xy,resolution,segment_safe):
        if self.point is not None and (math.dist(xy,self.point)<resolution*.3 or not segment_safe(xy,self.point)):self.point=None
        return self.point

    def choose(self,path,xy,resolution):self.point=next_path_cell(path,xy,resolution);return self.point


class TurnProgress:
    def __init__(self):self.start=None;self.expected=0.;self.blocked=0

    def begin(self,yaw,expected):self.start=yaw;self.expected=abs(expected)

    def finish(self,yaw):
        if self.start is None:return
        actual=abs(wrap(yaw-self.start))
        self.blocked=self.blocked+1 if actual<max(math.radians(1),self.expected*.2) else 0
        self.start=None


class TerrainHeadingLock:
    """Keep heading across an incline and until a flat exit has been traversed."""
    def __init__(self,flat_exit_m=.14):
        self.active=False;self.heading=0.;self.last_incline=None;self.flat_exit_m=flat_exit_m

    def update(self,position,rotation):
        position=np.asarray(position)[:2]
        tilt=math.acos(float(np.clip(rotation.as_matrix()[2,2],-1.,1.)))
        if tilt>math.radians(2.):
            if not self.active:self.heading=float(rotation.as_euler('xyz')[2])
            self.active=True;self.last_incline=position.copy()
        elif self.active and np.linalg.norm(position-self.last_incline)>self.flat_exit_m:self.active=False
