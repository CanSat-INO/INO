"""Use native command logs and Gazebo truth to assess hazards independently."""
import argparse,json
from pathlib import Path
import numpy as np

def assess(folder,kind='landing'):
    folder=Path(folder);r=json.loads((folder/'result.json').read_text())
    commands=np.atleast_2d(np.genfromtxt(folder/'firmware_commands.csv',delimiter=',',skip_header=1))
    poses=np.atleast_2d(np.genfromtxt(folder/'trajectory.csv',delimiter=',',skip_header=1));t=poses[:,0]-poses[0,0]
    landing=r.get('landing');contact=landing['time_s'] if landing else float('inf')
    premature=(commands[:,0]<contact)&((commands[:,1]!=0)|(commands[:,2]!=0))
    checks=dict(images_received=r['image_frames']>0,not_claimed_false_success=not r['goal_stopped'] or bool(r.get('final_goal_distance_m',float('inf'))<=.5 and r['ground_contact']))
    if kind=='original_wait':
        checks=dict(images_received=r['image_frames']>0,original_hazard_reproduced=bool(premature.any()),still_airborne=not r['ground_contact'])
    else:
        checks.update(no_early_motor_or_separation=not bool(premature.any()),stale_commands_stop=not bool(((commands[:,5]!=31)&(commands[:,1]!=0)).any()))
        held=poses[t<r['pre_release_wait_s']-.1,3]
        checks['held_before_release']=bool(len(held)>2 and np.ptp(held)<.03)
        if kind=='guarded_wait':checks['never_armed']=bool((commands[:,4]==0).all())
        elif kind in ('landing','barometer_loss_after_arm'):
            confirmed=commands[commands[:,4]==2,0]
            checks.update(ground_contact=r['ground_contact'],firmware_confirmed_after_ground=bool(len(confirmed) and confirmed[0]>=contact+1.8),finished_confirmation=r['reason']=='landing_confirmed')
        elif kind=='barometer_loss':
            # No valid sustained descent was observed before the dropout. A
            # later stable low reading alone must not manufacture a release.
            checks.update(ground_contact=r['ground_contact'],no_release_inferred=bool((commands[:,4]==0).all()),no_motion=bool((commands[:,1]==0).all()),held_without_claiming_success=r['reason']=='time_limit' and not r['goal_stopped'])
        elif kind=='gnss_loss':
            missing=(commands[:,4]==2)&((commands[:,5].astype(int)&2)==0)
            checks.update(missing_seen=bool(missing.any()),moves_before_loss=bool(((commands[:,0]<30)&(commands[:,1]!=0)).any()),moves_after_recovery=bool(((commands[:,0]>35.5)&(commands[:,1]!=0)).any()))
        elif kind=='camera_delay':checks.update(no_motion=bool((commands[:,1]==0).all()),camera_expired=bool(((commands[:,5].astype(int)&16)==0).all()),stopped_not_success=not r['goal_stopped'])
        elif kind=='goal':
            speed=float(np.linalg.norm(poses[-1,1:3]-poses[-2,1:3])/max(1e-6,t[-1]-t[-2]))
            checks.update(goal_stopped=r['goal_stopped'],distance_under_half_m=r['final_goal_distance_m']<=.5,final_speed_under_1cmps=speed<.01)
    (folder/'robust-verification.json').write_text(json.dumps(checks,indent=2));return checks

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder');parser.add_argument('--kind',default='landing');a=parser.parse_args();checks=assess(a.folder,a.kind);print(json.dumps(checks,indent=2))
    if not all(checks.values()):raise SystemExit(1)
