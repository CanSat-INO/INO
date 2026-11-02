"""Run one isolated, bounded design case; preserve configuration and evidence."""
import argparse
import datetime
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import uuid
import yaml
from design_config import ROOT,load

os.environ.setdefault('ROS_DOMAIN_ID','64')
os.environ.setdefault('GZ_PARTITION','ino_camera_'+os.environ['ROS_DOMAIN_ID'])
p=argparse.ArgumentParser()
p.add_argument('mode',nargs='?',choices=['continuous','stop','sequential'])
p.add_argument('--gui',action='store_true')
p.add_argument('--runtime',help='Unique run directory supplied by a controller')
p.add_argument('--config',default=str(ROOT/'config/design.yaml'))
p.add_argument('--wall-timeout',type=float)
p.add_argument('--stereo-max-disparity',type=int,default=128)
p.add_argument('--set',action='append',default=[])
a=p.parse_args()
cfg=load(a.config,a.set)
if a.mode:cfg['capture']['mode']=a.mode
out=ROOT/'logs'/f'{datetime.datetime.now():%Y%m%d-%H%M%S}-{cfg["world"]["surface"]}-{cfg["capture"]["mode"]}-{uuid.uuid4().hex[:4]}'
if a.runtime:
    out=Path(a.runtime).resolve()
    if (out/'result.json').exists() or (out/'source').exists():
        raise RuntimeError('Runtime directory already contains an experiment')
    out.mkdir(parents=True,exist_ok=True)
else:
    out.mkdir(parents=True)
(out/'requested.yaml').write_text(yaml.safe_dump(cfg,sort_keys=False))
for folder in ('tools','launch','config','scripts'):
    shutil.copytree(ROOT/folder,out/'source'/folder,ignore=shutil.ignore_patterns('__pycache__'))
with (out/'versions.txt').open('w') as versions:
    subprocess.run(['dpkg-query','-W','ros-jazzy-rtabmap','ros-jazzy-gz-sim-vendor','ros-jazzy-ros-gz-bridge'],stdout=versions,check=True)

def stop(proc):
    for sig,seconds in [(signal.SIGINT,35),(signal.SIGTERM,8),(signal.SIGKILL,2)]:
        try:os.killpg(proc.pid,sig)
        except ProcessLookupError:return
        try:proc.wait(timeout=seconds)
        except subprocess.TimeoutExpired:continue
        return

t=cfg['test']
duration=9+t['repeats']*(t['step_m']/t['speed_mps']+t['stop_s'])+(t['repeats']-1)*(abs(t['turn_deg'])/t['turn_rate_degps']+t['stop_s'])
with (out/'launch.log').open('w') as log,(out/'evaluation.log').open('w') as evidence:
    (out/'algorithm.json').write_text(__import__('json').dumps({'Stereo/MaxDisparity':a.stereo_max_disparity},indent=2))
    proc=subprocess.Popen(['bash',str(ROOT/'scripts/start.sh'),f'gui:={str(a.gui).lower()}',f'rviz:={str(a.gui).lower()}',f'config:={out}/requested.yaml',f'runtime:={out}',f'stereo_max_disparity:={a.stereo_max_disparity}'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    ev=None
    try:
        ev_cmd=[sys.executable,str(ROOT/'tools/evaluate.py'),'--output',str(out),'--config',str(out/'requested.yaml'),'--mode',cfg['capture']['mode']]
        if a.wall_timeout:ev_cmd+=['--wall-timeout',str(a.wall_timeout)]
        ev=subprocess.Popen(ev_cmd,stdout=evidence,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+max(115,duration*2+60)
        if a.wall_timeout:deadline=time.monotonic()+a.wall_timeout+30
        while ev.poll() is None:
            if proc.poll() is not None:raise RuntimeError('Simulator exited; see '+str(out/'launch.log'))
            if time.monotonic()>deadline:raise TimeoutError('Evaluation exceeded time limit')
            time.sleep(.2)
        code=ev.returncode
    finally:
        if ev and ev.poll() is None:stop(ev)
        stop(proc)
if (out/'result.json').exists():
    from plot_run import plot
    plot(out)
print((out/'evaluation.log').read_text())
print(out)
sys.exit(code)
