"""Sensor-derived elevation/traversability and bounded A*; no ROS dependency."""
import heapq
import math
import numpy as np
from scipy.ndimage import distance_transform_edt, maximum_filter, minimum_filter, uniform_filter


class TerrainGrid:
    def __init__(self,cfg):
        self.cfg=cfg;self.res=cfg['resolution_m'];self.x0,self.y0,x1,y1=cfg['map_bounds_m']
        self.shape=(int(math.ceil((y1-self.y0)/self.res)),int(math.ceil((x1-self.x0)/self.res)))
        self.height=np.zeros(self.shape,float);self.roughness=np.zeros(self.shape,float)
        self.seen=np.zeros(self.shape,bool);self.count=np.zeros(self.shape,int)
        self.cost=np.full(self.shape,-1,np.int16);self.blocked=np.zeros(self.shape,bool)
        self.slope=np.zeros(self.shape,float);self.step=np.zeros(self.shape,float)
        yy,xx=np.indices(self.shape);x=self.x0+(xx+.5)*self.res;y=self.y0+(yy+.5)*self.res
        # Known starting footprint only; this is an explicit flat-start assumption.
        self.seen[x*x+y*y<=cfg['footprint_radius_m']**2]=True

    def cell(self,x,y):return (int(math.floor((y-self.y0)/self.res)),int(math.floor((x-self.x0)/self.res)))
    def inside(self,cell):return 0<=cell[0]<self.shape[0] and 0<=cell[1]<self.shape[1]
    def xy(self,cell):return (self.x0+(cell[1]+.5)*self.res,self.y0+(cell[0]+.5)*self.res)

    def occupy(self,position):
        # Only the occupied central footprint is known from being there.
        # Preserve every measured hazard; never clear an obstacle to obtain a path.
        # Holes and suspended chassis are outside this ground-model assumption.
        yy,xx=np.indices(self.shape)
        distance=np.hypot(self.x0+(xx+.5)*self.res-position[0],self.y0+(yy+.5)*self.res-position[1])
        new=(distance<=.08)&(~self.seen)
        self.seen[new]=True;self.height[new]=position[2];self.cost[new]=5

    def integrate(self,points):
        points=np.asarray(points,float)
        if not len(points):return
        points=points[np.isfinite(points).all(axis=1)]
        cells=np.floor((points[:,:2]-[self.x0,self.y0])/self.res).astype(int)
        keep=(cells[:,0]>=0)&(cells[:,0]<self.shape[1])&(cells[:,1]>=0)&(cells[:,1]<self.shape[0])&(points[:,2]>-.15)&(points[:,2]<1.2)
        cells=cells[keep];points=points[keep]
        keys=cells[:,1]*self.shape[1]+cells[:,0]
        order=np.argsort(keys);keys=keys[order];points=points[order]
        for group in np.split(np.arange(len(keys)),np.flatnonzero(np.diff(keys))+1):
            if len(group)<3:continue
            key=keys[group[0]];row,col=divmod(int(key),self.shape[1]);z=points[group,2]
            # Upper percentile preserves box/cone surfaces, rather than averaging
            # vertical obstacles into the ground. Noise remains a model limitation.
            top=float(np.quantile(z,.85));rough=float(np.quantile(z,.85)-np.quantile(z,.15))
            if self.seen[row,col] and self.count[row,col]>0:
                self.height[row,col]=.6*self.height[row,col]+.4*top
                self.roughness[row,col]=.6*self.roughness[row,col]+.4*rough
            else:self.height[row,col]=top;self.roughness[row,col]=rough
            self.seen[row,col]=True;self.count[row,col]+=len(group)
        self.classify()

    def classify(self):
        valid=self.seen
        # Do not use zero-valued unknown cells as slope/step measurements.
        weights=uniform_filter(valid.astype(float),size=3,mode='constant')
        mean=uniform_filter(np.where(valid,self.height,0.),size=3,mode='constant')/np.maximum(weights,1e-6)
        filled=np.where(valid,self.height,mean)
        gy,gx=np.gradient(mean,self.res)
        self.slope=np.degrees(np.arctan(np.hypot(gx,gy)))
        hi=maximum_filter(np.where(valid,self.height,-np.inf),size=3,mode='constant',cval=-np.inf)
        lo=minimum_filter(np.where(valid,self.height,np.inf),size=3,mode='constant',cval=np.inf)
        self.step=np.maximum(0,hi-lo)
        cfg=self.cfg
        slope_ratio=self.slope/cfg['max_slope_deg']
        step_ratio=self.step/cfg['max_step_m']
        rough_ratio=self.roughness/cfg['max_roughness_m']
        risk=np.maximum.reduce([slope_ratio,step_ratio,rough_ratio])
        # Sparse margins cannot estimate slope reliably; high objects can still
        # be blocked using height and locally observed vertical extent.
        self.blocked=valid&((self.roughness>cfg['obstacle_height_m'])|(step_ratio>1.)|
                           ((weights>.65)&(slope_ratio>1.))|(rough_ratio>1.5))
        self.cost=np.where(valid,np.clip(5+55*risk,5,85),-1).astype(np.int16)
        self.cost[self.blocked]=100
        return self.cost

    def planning_cost(self,origin=None):
        raw=self.blocked.copy()
        raw[[0,-1],:]=True;raw[:,[0,-1]]=True
        distance=distance_transform_edt(~raw)*self.res
        inflated=distance<=self.cfg['footprint_radius_m']+self.cfg['safety_margin_m']
        cost=np.where(self.seen,1+np.maximum(self.cost,0)/25.,3.5)
        cost[inflated]=np.inf
        if origin is not None:
            start=self.cell(*origin)
            if self.inside(start) and inflated[start] and not raw[start] and self.seen[start] and distance[start]>=self.cfg['footprint_radius_m']:
                # A newly observed safety margin can cover the current pose.
                # Permit a short escape through observed cells whose clearance
                # is no worse than the current one. Actual obstacles and the
                # hard footprint radius stay blocked; unknown is not cleared.
                yy,xx=np.indices(self.shape)
                near=np.hypot((yy-start[0])*self.res,(xx-start[1])*self.res)<=.4
                escape=near&self.seen&(~raw)&(distance>=distance[start]-1e-9)
                cost[escape]=np.maximum(6.,1+np.maximum(self.cost[escape],0)/25.)
        return cost

    def plan(self,start,goal):
        origin=start;start=self.cell(*start);goal=self.cell(*goal)
        if not self.inside(start) or not self.inside(goal):return []
        costs=self.planning_cost(origin)
        if not np.isfinite(costs[start]) or not np.isfinite(costs[goal]):return []
        frontier=[(0.,0.,start)];scores={start:0.};parent={}
        directions=[(a,b) for a in (-1,0,1) for b in (-1,0,1) if a or b]
        while frontier:
            _,score,current=heapq.heappop(frontier)
            if score>scores[current]+1e-9:continue
            if current==goal:
                path=[goal]
                while path[-1]!=start:path.append(parent[path[-1]])
                return [self.xy(cell) for cell in path[::-1]]
            for dy,dx in directions:
                nxt=(current[0]+dy,current[1]+dx)
                if not self.inside(nxt) or not np.isfinite(costs[nxt]):continue
                if dx and dy and (not np.isfinite(costs[current[0]+dy,current[1]]) or not np.isfinite(costs[current[0],current[1]+dx])):continue
                value=score+math.hypot(dx,dy)*float(costs[nxt])
                if value>=scores.get(nxt,float('inf')):continue
                scores[nxt]=value;parent[nxt]=current
                heuristic=math.hypot(nxt[0]-goal[0],nxt[1]-goal[1])
                heapq.heappush(frontier,(value+heuristic,value,nxt))
        return []

    def observed_segment(self,start,end):
        # At every sampled center the forward path must be observed; blocked
        # footprint clearance is already enforced by the inflated planning map.
        cost=self.planning_cost(start)
        for t in np.linspace(0.,1.,max(2,int(math.dist(start,end)/(self.res/2))+1)):
            cell=self.cell(start[0]+t*(end[0]-start[0]),start[1]+t*(end[1]-start[1]))
            if not self.inside(cell) or not self.seen[cell] or not np.isfinite(cost[cell]):return False
        return True
