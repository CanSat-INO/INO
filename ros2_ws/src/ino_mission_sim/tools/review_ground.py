"""Independent, stricter post-run geometry/goal review from saved truth CSV.

Preserve the original online verdict. Cone bases are square collision boxes,
not circular disks. No navigation data or control commands are changed.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import yaml


def clearance(point,obstacles,radius):
    x,y=point
    boxes=[(cx,cy,obstacles['cone_base_m'],obstacles['cone_base_m']) for cx,cy in obstacles['cones']]
    boxes += [(cx,cy,sx,sy) for cx,cy,sx,sy,_ in obstacles['boxes']]
    return min((math.hypot(max(abs(x-cx)-sx/2,0),max(abs(y-cy)-sy/2,0))-radius
                for cx,cy,sx,sy in boxes),default=float('inf'))


def review(out):
    out=Path(out);result=json.loads((out/'result.json').read_text());cfg=yaml.safe_load((out/'ground-effective.yaml').read_text())
    raw=out/'result-online.json'
    if not raw.exists():raw.write_text(json.dumps(result,indent=2))
    if cfg.get('goal',{}).get('camera_confirmation'):cfg['obstacles']['cones']=list(cfg['obstacles']['cones'])+[cfg['goal_xy_m']]
    rows=list(csv.DictReader((out/'trajectory.csv').open()))
    minimum=min((clearance((float(row['truth_x']),float(row['truth_y'])),cfg['obstacles'],cfg['footprint_radius_m']) for row in rows),default=float('inf'))
    within_goal=result['true_goal_distance_m'] is not None and result['true_goal_distance_m']<=cfg['goal_tolerance_m']
    result.update(min_conservative_obstacle_clearance_m=minimum if math.isfinite(minimum) else None,
        goal_within_configured_tolerance=within_goal,
        review=dict(method='square cone bases and boxes vs circular robot footprint; no goal allowance',
                    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),trajectory_sha256=hashlib.sha256((out/'trajectory.csv').read_bytes()).hexdigest()))
    result['manual_intervention']=(out/'manual-intervention.json').exists()
    result['passed']=bool(result['passed'] and minimum>=0 and within_goal and not result['manual_intervention'])
    (out/'result.json').write_text(json.dumps(result,indent=2))
    return result
