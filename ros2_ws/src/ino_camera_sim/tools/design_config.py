"""Single source of camera geometry and validated exploration settings."""
from pathlib import Path
import copy
import math
import yaml
import cv2
import numpy as np
from scipy.spatial.transform import Rotation

ROOT=Path(__file__).resolve().parents[1]

def load(path=None, overrides=()):
    cfg=yaml.safe_load((ROOT/'config/design.yaml').read_text())
    if path and Path(path).resolve()!=(ROOT/'config/design.yaml').resolve():
        def merge(dst,src):
            for k,v in src.items():
                if k not in dst: raise ValueError(f'Unknown setting: {k}')
                if isinstance(v,dict) and isinstance(dst.get(k),dict): merge(dst[k],v)
                else: dst[k]=v
        merge(cfg,yaml.safe_load(Path(path).read_text()) or {})
    for override in overrides:
        key,value=override.split('=',1)
        target=cfg
        parts=key.split('.')
        for part in parts[:-1]: target=target[part]
        if parts[-1] not in target: raise ValueError(f'Unknown setting: {key}')
        target[parts[-1]]=yaml.safe_load(value)
    c=cfg['camera']; a=cfg['capture']; w=cfg['world']; t=cfg['test']
    checks=[(.01<=c['baseline_m']<=.4,'baseline .01.. .4 m'),(.02<=c['height_m']<=1,'height .02..1 m'),(30<=c['hfov_deg']<=140,'horizontal FOV 30..140 deg'),(160<=c['width']<=1920 and 120<=c['height']<=1080,'resolution'),(1<=c['fps']<=30,'fps 1..30'),(abs(c['toe_in_deg'])<=30,'toe-in +/-30 deg'),(-45<=c['pitch_down_deg']<=75,'pitch -45..75 deg'),(a['mode'] in ('continuous','stop','sequential'),'capture mode'),(0<=a['drop_probability']<1,'drop probability [0,1)'),(1<=a['jpeg_quality']<=100,'JPEG quality 1..100'),(all(a[k]>=0 for k in ('settle_s','skew_s','acquisition_s','transmission_s')) and a['period_s']>0,'capture timing'),(w['surface'] in ('lab','grass_dry','grass_green','low_texture'),'surface'),(cfg['robot']['shape'] in ('simple','deployed','folded'),'robot shape'),(0<t['speed_mps']<=.5 and 0<t['step_m']<=1.5,'test speed / step'),(0<t['turn_rate_degps']<=30 and t['stop_s']>=0,'turn rate / stop'),(1<=t['repeats']<=10,'repeats'),(t['route'] in ('zigzag','return'),'test route')]
    checks += [(all(isinstance(c[k],int) and not isinstance(c[k],bool) for k in ['width','height']),'integer image resolution'),(isinstance(w['grass_density'],int) and isinstance(t['repeats'],int) and isinstance(a['jpeg_quality'],int),'integer count settings'),(0<w['cone_height_m']<=2 and 0<w['cone_base_m']<=2,'cone dimensions'),(w['mat_size'][0]*w['mat_size'][1]/max(w['mat_bump_spacing_m']**2,1e-9)<=3000,'too many mat bumps'),(2<=w['size_m']<=30 and 0<w['texture_span_m']<=w['size_m'],'world dimensions'),(0<=w['grass_height_m']<=.2 and 100<=w['grass_density']<=100000,'grass geometry'),(.01<=w['mat_bump_spacing_m']<=.3 and 0<w['mat_bump_height_m']<=.1,'mat geometry'),(len(w['mat_size'])==2 and all(.05<=x<=3 for x in w['mat_size']),'mat size'),(all(len(x)==2 for x in w['cones']) and all(len(x)==5 and all(v>0 for v in x[2:]) for x in w['boxes']),'obstacle layout'),(abs(t['turn_deg'])<=180,'turn angle'),(all(abs(c[k])<=30 for k in ['left_pitch_delta_deg','right_pitch_delta_deg']),'independent pitch'),(abs(c['roll_deg'])<=45 and abs(c['yaw_deg'])<=180,'rig orientation'),(c['height_m']+c['right_height_delta_m']>0,'right camera above ground')]
    for valid,message in checks:
        if not valid: raise ValueError('Invalid '+message)
    if a['mode']=='sequential' and a['skew_s'] and a['skew_s']<1/c['fps']-1e-6:
        raise ValueError('skew_s is smaller than the camera frame interval; increase fps or skew_s')
    return cfg

def rig(cfg):
    c=cfg['camera']
    common=Rotation.from_euler('ZYX',[c['yaw_deg'],c['pitch_down_deg'],c['roll_deg']],degrees=True).as_matrix()
    # Gazebo camera axes: forward X, left Y, up Z. Optical: right X, down Y, forward Z.
    optical=np.array([[0,0,1],[-1,0,0],[0,-1,0]],float)
    positions={}; rotations={}; gazebo={}
    for side,sign in [('left',1),('right',-1)]:
        offset=np.array([0,sign*c['baseline_m']/2,0.])
        if side=='right': offset+=np.array([c['right_forward_delta_m'],0,c['right_height_delta_m']])
        positions[side]=np.array([c['forward_m'],0,c['height_m']])+common@offset
        extra=Rotation.from_euler('ZYX',[-sign*c['toe_in_deg'],c[f'{side}_pitch_delta_deg'],0],degrees=True).as_matrix()
        gazebo[side]=common@extra
        rotations[side]=gazebo[side]@optical
    f=c['width']/(2*math.tan(math.radians(c['hfov_deg'])/2))
    K=np.array([[f,0,(c['width']-1)/2],[0,f,(c['height']-1)/2],[0,0,1.]])
    R=rotations['right'].T@rotations['left']
    T=rotations['right'].T@(positions['left']-positions['right'])
    R1,R2,P1,P2,Q,roi1,roi2=cv2.stereoRectify(K,np.zeros(5),K,np.zeros(5),(c['width'],c['height']),R,T,flags=cv2.CALIB_ZERO_DISPARITY,alpha=0)
    return dict(positions=positions,raw_rotations=rotations,gazebo_rotations=gazebo,K=K,R=R,T=T,R1=R1,R2=R2,P1=P1,P2=P2,Q=Q,roi1=roi1,roi2=roi2)

def geometry_summary(cfg):
    r=rig(cfg); c=cfg['camera']
    vfov=math.degrees(2*math.atan(c['height']/c['width']*math.tan(math.radians(c['hfov_deg'])/2)))
    near_angle=math.radians(c['pitch_down_deg']+vfov/2)
    return {'horizontal_fov_deg':c['hfov_deg'],'vertical_fov_deg':vfov,'nearest_ground_from_camera_m':c['height_m']/math.tan(near_angle) if 0<near_angle<math.pi/2 else None,'rectified_fx_px':float(r['P1'][0,0]),'minimum_depth_at_max_disparity_128px_m':float(-r['P2'][0,3]/128),'rectified_baseline_m':float(-r['P2'][0,3]/r['P2'][0,0]),'raw_positions_m':{k:v.tolist() for k,v in r['positions'].items()},'note':'Ground intersection is a pinhole, level-ground estimate; body occlusion and rectification crop require image checks.'}
