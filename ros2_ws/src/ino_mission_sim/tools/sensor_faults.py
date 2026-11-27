"""Acquisition-time sensor faults. No simulator truth is passed to the controller.

Channels have independent RNGs. Delayed samples retain their acquisition stamp;
missing samples retain the last value but become invalid on age expiry.
"""
import hashlib,heapq,math
from copy import deepcopy
import numpy as np

NAMES=('barometer','gnss','imu','heading','camera')
DEFAULTS={'barometer':(.05,.5),'gnss':(.2,2.5),'imu':(.02,.3),'heading':(.05,.7),'camera':(0.,.7)}

class Channel:
    def __init__(self,name,config,seed):
        self.name=name;self.cfg=deepcopy(config);self.period=float(config.get('period_s',DEFAULTS[name][0]));self.max_age=float(config.get('max_age_s',DEFAULTS[name][1]))
        self.delay=float(config.get('delay_s',0));self.jitter=float(config.get('jitter_s',0));self.drop=float(config.get('drop_probability',0))
        for value in [self.period,self.max_age,self.delay,self.jitter]:
            if not math.isfinite(value) or value<0:raise ValueError('Invalid timing for '+name)
        if self.max_age==0 or not 0<=self.drop<=1:raise ValueError('Invalid age/drop rate for '+name)
        for interval in config.get('blackouts',[]):
            if len(interval)!=2 or not all(math.isfinite(v) for v in interval) or not 0<=interval[0]<interval[1]:raise ValueError('Invalid blackout for '+name)
        for key in ['noise_std','bias']:
            values=np.asarray(config.get(key,0.),dtype=float)
            if not np.isfinite(values).all() or (key=='noise_std' and (values<0).any()):raise ValueError('Invalid '+key+' for '+name)
        channel_seed=int.from_bytes(hashlib.sha256(name.encode()).digest()[:4],'little')
        self.rng=np.random.default_rng(seed+channel_seed);self.next=-math.inf;self.queue=[];self.last=None;self.serial=0
        self.acquired=0;self.dropped=0;self.delivered=0

    def push(self,t,value):
        if t+1e-9<self.next:return
        self.next=t+self.period;self.acquired+=1
        if any(start<=t<end for start,end in self.cfg.get('blackouts',[])) or self.rng.random()<self.drop:
            self.dropped+=1;return
        if not isinstance(value,(bytes,str)):
            value=np.array(value,dtype=float)+np.asarray(self.cfg.get('bias',0.))
            value=value+self.rng.normal(size=value.shape)*np.asarray(self.cfg.get('noise_std',0.))
        self.serial+=1
        arrival=t+max(0.,self.delay+self.rng.uniform(-self.jitter,self.jitter))
        heapq.heappush(self.queue,(arrival,self.serial,t,value))

    def read(self,t):
        while self.queue and self.queue[0][0]<=t+1e-9:
            _,serial,stamp,value=heapq.heappop(self.queue)
            if self.last is None or stamp>=self.last['stamp_s']:
                self.last=dict(stamp_s=stamp,value=value,serial=serial);self.delivered+=1
        if self.last is None:return dict(value=None,stamp_s=None,age_s=None,valid=False,serial=0)
        age=max(0.,t-self.last['stamp_s'])
        return dict(self.last,age_s=age,valid=age<=self.max_age+1e-9)

class SensorBank:
    def __init__(self,config,seed):self.channels={name:Channel(name,config.get(name,{}),seed) for name in NAMES}
    def read(self,t):return {name:channel.read(t) for name,channel in self.channels.items()}
    def counts(self):return {name:dict(acquired=c.acquired,dropped=c.dropped,delivered=c.delivered) for name,c in self.channels.items()}
