"""Three-axis point-mass descent, staged CdA and reproducible time-varying wind.

No cloth, attitude, tether or terrain-contact solver. Gazebo handles the rendered
scene/cameras/contact; this module supplies translational velocity commands.
"""
import math
from copy import deepcopy
import numpy as np

GRAVITY = np.array([0., 0., -9.81])

def vector(value, name):
    result = np.asarray(value, dtype=float)
    if result.shape != (3,) or not np.isfinite(result).all():
        raise ValueError(name+' must contain three finite ENU values')
    return result

class Descent:
    def __init__(self, config):
        config=deepcopy(config)
        self.cfg = config
        self.settings = config['descent']
        self.chute = self.settings['parachute']
        self.wind_cfg = self.settings['wind']
        self.mass = float(config['mass_kg'])
        self.rho = float(config['air_density_kgm3'])
        self.full_cda = float(config['drag_coefficient'])*math.pi*(float(config['parachute_diameter_m'])/2)**2
        self.body_cda = float(self.settings['body_cda_m2'])
        for name, value in [('mass',self.mass),('density',self.rho),('full CdA',self.full_cda),('diameter',config['parachute_diameter_m']),('release height',config['release_height_m'])]:
            if not math.isfinite(value) or value <= 0: raise ValueError(name+' must be positive')
        for name, value in [('body CdA',self.body_cda),('trigger time',self.chute['trigger_time_s']),('opening time',self.chute['opening_s']),('delay',self.chute['delay_s']),('turbulence',self.wind_cfg['turbulence_std_mps'])]:
            if not math.isfinite(float(value)) or value < 0: raise ValueError(name+' must be finite and nonnegative')
        if self.chute['trigger'] not in ('time','altitude','command'): raise ValueError('Unknown parachute trigger')
        if not 0 <= self.chute['max_fraction'] <= 1: raise ValueError('max_fraction must be 0..1')
        if not math.isfinite(self.chute['trigger_altitude_m']) or self.chute['trigger_altitude_m'] <= 0: raise ValueError('trigger altitude must be positive')
        self.mean_wind = vector(self.wind_cfg['mean_enu_mps'], 'mean wind')
        for gust in self.wind_cfg['gusts']:
            vector(gust['delta_enu_mps'], 'gust')
            if gust['start_s'] < 0 or gust['duration_s'] <= 0: raise ValueError('Invalid gust interval')
        self.velocity = vector(self.settings['initial_velocity_enu_mps'], 'initial velocity').copy()
        self.acceleration = np.zeros(3)
        rng = np.random.default_rng(self.wind_cfg['seed'])
        self.phase = rng.uniform(0,2*math.pi,(3,4))
        self.frequencies = np.array([.19,.43,.79,1.31])
        self.triggered_at = None
        self.fraction = 0.
        self.detached = False
        self.stage = 'stowed'

    def wind(self, t):
        result = self.mean_wind.copy()
        for gust in self.wind_cfg['gusts']:
            u = (t-gust['start_s'])/gust['duration_s']
            if 0 < u < 1:
                result += math.sin(math.pi*u)**2*vector(gust['delta_enu_mps'],'gust')
        # A bounded deterministic fluctuation, not a calibrated atmospheric spectrum.
        result += self.wind_cfg['turbulence_std_mps']*math.sqrt(2/4)*np.sin(2*math.pi*self.frequencies*t+self.phase).sum(axis=1)
        return result

    def deploy(self, t):
        if self.triggered_at is None and not self.detached: self.triggered_at = float(t)

    def detach(self):
        self.detached = True
        self.fraction = 0.
        self.stage = 'detached'

    def opening(self, t, altitude):
        if self.detached: self.stage='detached';self.fraction=0.;return 0.
        if self.triggered_at is None:
            if self.chute['trigger']=='time' and t >= self.chute['trigger_time_s']: self.deploy(t)
            elif self.chute['trigger']=='altitude' and altitude <= self.chute['trigger_altitude_m'] and self.velocity[2] < 0: self.deploy(t)
        if self.chute['failure']: self.stage='failed';self.fraction=0.;return 0.
        if self.triggered_at is None: self.stage='stowed';self.fraction=0.;return 0.
        elapsed = t-self.triggered_at-self.chute['delay_s']
        if elapsed < 0: self.stage='delay';self.fraction=0.;return 0.
        u = min(1.,elapsed/self.chute['opening_s']) if self.chute['opening_s'] else 1.
        self.fraction = self.chute['max_fraction']*u*u*(3-2*u)
        self.stage = 'open' if u >= 1 else 'opening'
        return self.fraction

    def advance(self, t, dt, altitude):
        if dt <= 0: return self.velocity.copy(),self.acceleration.copy()
        steps = max(1, math.ceil(dt/.0025))
        h = dt/steps
        old = self.velocity.copy()
        height = float(altitude)
        for step in range(steps):
            stamp = t-dt+(step+.5)*h
            fraction = self.opening(stamp,height)
            relative = self.velocity-self.wind(stamp)
            cda = self.body_cda+self.full_cda*fraction
            # F_drag = -0.5 rho CdA |v-w| (v-w), in world ENU coordinates.
            acceleration = GRAVITY-.5*self.rho*cda/self.mass*np.linalg.norm(relative)*relative
            self.velocity += acceleration*h
            height += self.velocity[2]*h
        self.acceleration = (self.velocity-old)/dt
        self.opening(t,height)
        return self.velocity.copy(),self.acceleration.copy()

    def info(self, t):
        return dict(stage=self.stage,open_fraction=float(self.fraction),triggered_at_s=self.triggered_at,
                    velocity_enu_mps=self.velocity.tolist(),acceleration_enu_mps2=self.acceleration.tolist(),
                    wind_enu_mps=self.wind(t).tolist(),cda_m2=self.body_cda+self.full_cda*self.fraction)

def world_to_body(value, yaw):
    c,s=math.cos(yaw),math.sin(yaw)
    return np.array([c*value[0]+s*value[1],-s*value[0]+c*value[1],value[2]])
