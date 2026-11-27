"""Own a dedicated ground-navigation session/router and collect actual evidence."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import uuid
import yaml
from ament_index_python.packages import get_package_share_directory
from ground_world import ROOT,load
from shared_camera import CAMERA


def stop(proc):
    if proc.poll() is not None:return
    os.killpg(proc.pid,signal.SIGINT)
    try:proc.wait(timeout=40)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGTERM)
        try:proc.wait(timeout=8)
        except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()


def main():
    a=argparse.ArgumentParser();a.add_argument('--config',default=str(ROOT/'config/ground_navigation.yaml'))
    a.add_argument('--headless',action='store_true');a.add_argument('--out');a.add_argument('--wall-timeout',type=float,default=1800)
    args=a.parse_args();cfg=load(args.config)
    out=Path(args.out or ROOT/'logs'/f'{datetime.datetime.now():%Y%m%d-%H%M%S}-ground-{uuid.uuid4().hex[:4]}').resolve()
    out.mkdir(parents=True,exist_ok=True)
    protected=[CAMERA/'config/design.yaml',CAMERA/'launch/stereo.launch.py',CAMERA/'config/stereo.rviz']
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    config=out/'requested.yaml';config.write_text(yaml.safe_dump(cfg,sort_keys=False))
    for folder in ('tools','launch','config'):
        shutil.copytree(ROOT/folder,out/'source'/folder,ignore=shutil.ignore_patterns('__pycache__'),dirs_exist_ok=True)
    defaults=Path(get_package_share_directory('rmw_zenoh_cpp'))/'config'
    session=out/'zenoh-session.json5';router=out/'zenoh-router.json5'
    session.write_text((defaults/'DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5').read_text().replace('tcp/localhost:7447','tcp/127.0.0.1:17645'))
    router.write_text((defaults/'DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5').read_text().replace('tcp/[::]:7447','tcp/127.0.0.1:17645'))
    env=os.environ.copy();env.update(RMW_IMPLEMENTATION='rmw_zenoh_cpp',ZENOH_SESSION_CONFIG_URI=str(session),
        ZENOH_ROUTER_CONFIG_URI=str(router),ROS_DOMAIN_ID='65',GZ_IP='127.0.0.1',GZ_PARTITION='ino_ground_'+uuid.uuid4().hex[:12],CANSAT_LOCK_NAME='.ground-navigation.lock')
    command=[sys.executable,str(ROOT/'tools/supervise.py'),sys.executable,str(ROOT/'tools/ground_session.py'),
             '--config',str(config),'--out',str(out)]+(['--headless'] if args.headless else [])
    manifest=dict(protected_sha256=hashes,source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
         for p in [*ROOT.glob('tools/ground*.py'),ROOT/'tools/run_ground.py',ROOT/'launch/ground.launch.py',ROOT/'config/ground.rviz',config]},
         requested_config=cfg,ros_domain_id=65,partition=env['GZ_PARTITION'],gazebo_ip=env['GZ_IP'])
    (out/'provenance.json').write_text(json.dumps(manifest,indent=2))
    print('Ground navigation: '+str(out),flush=True)
    with (out/'launch.log').open('w') as log:
        proc=subprocess.Popen(command,env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        deadline=time.monotonic()+args.wall_timeout;finished_at=None
        try:
            while proc.poll() is None:
                if (out/'navigation.json').exists():
                    try:state=json.loads((out/'navigation.json').read_text())
                    except (json.JSONDecodeError,OSError):state={}
                    if state.get('done'):
                        if finished_at is None:
                            finished_at=time.monotonic();print(json.dumps(state),flush=True)
                        if args.headless and time.monotonic()-finished_at>5:break
                if time.monotonic()>deadline:
                    print('Wall timeout; stopping this session only.',flush=True);break
                time.sleep(.3)
        except KeyboardInterrupt:pass
        finally:stop(proc)
    if hashes!={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}:raise RuntimeError('Camera defaults changed')
    if (out/'result.json').exists():
        from report_ground import report
        report(out)
        result=json.loads((out/'result.json').read_text());print(json.dumps(result,indent=2),flush=True)
        return 0 if result['passed'] else 2
    print('No result; inspect '+str(out/'launch.log'));return 3


if __name__=='__main__':sys.exit(main())
