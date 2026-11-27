"""Check actual release/phase/stop evidence instead of trusting phase=6 alone."""
import argparse,json
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('folder');p.add_argument('--expect',choices=['goal','time_limit'],default='goal');a=p.parse_args();folder=Path(a.folder)
r=json.loads((folder/'result.json').read_text());d=np.atleast_2d(np.genfromtxt(folder/'trajectory.csv',delimiter=',',skip_header=1))
checks=dict(release_above_ground=bool(d[0,3]>5),ground_contact=r['ground_contact'],separation_command=r['parachute_release_command'],gnss_phase=4 in r['phases'],camera_phase=5 in r['phases'])
if a.expect=='goal':
    speed=float(np.linalg.norm(d[-1,1:3]-d[-2,1:3])/max(1e-6,d[-1,0]-d[-2,0]))
    checks.update(goal_stopped=r['goal_stopped'],goal_phase=6 in r['phases'],distance_under_half_m=r['final_goal_distance_m']<=.5,final_motion_under_1cmps=speed<.01)
else:checks.update(time_limit=r['reason']=='time_limit',not_claimed_success=not r['goal_stopped'])
(folder/'verification.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks,indent=2))
if not all(checks.values()):raise SystemExit(1)
