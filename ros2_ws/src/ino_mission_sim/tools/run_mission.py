"""Own a descent/native-SIL run with explicit controller provenance and timeout."""
import argparse,datetime,importlib.util,json,os,signal,subprocess,sys,time,uuid
from pathlib import Path
import yaml
from mission_config import load_mission
ROOT=Path(__file__).resolve().parents[1]

def stop(proc):
    if proc.poll() is not None:return
    os.killpg(proc.pid,signal.SIGINT)
    try:proc.wait(timeout=45)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGTERM)
        try:proc.wait(timeout=10)
        except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',default=str(ROOT/'config/firmware/descent.yaml'))
    parser.add_argument('--out');parser.add_argument('--headless',action='store_true')
    parser.add_argument('--wall-timeout',type=float,default=1800)
    parser.add_argument('--controller-source',action='append');parser.add_argument('--include',action='append',default=[])
    parser.add_argument('--reference-profile',choices=['original','mission','guarded'])
    a=parser.parse_args()
    if a.controller_source and a.reference_profile:raise ValueError('Select either your adapter or an explicit legacy reference')
    cfg=load_mission(a.config)
    out=Path(a.out or ROOT/'logs'/('mission-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:5])).resolve()
    out.mkdir(parents=True,exist_ok=True)
    if (out/'result.json').exists():raise ValueError('This directory already has a result')
    build=out/'native';build.mkdir(exist_ok=True)
    kind='connection_example_only'
    if a.controller_source:
        builder=Path(__file__).resolve().parents[4]/'cansat/sil/build_controller.py'
        if not builder.exists():raise RuntimeError('Use the repository source launcher for user firmware SIL builds')
        spec=importlib.util.spec_from_file_location('ino_sil_build',builder);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        binary=module.build(a.controller_source,build/'controller',a.include,ROOT/'firmware/sil')
        kind='user_native_adapter'
    elif a.reference_profile:
        subprocess.run([sys.executable,str(ROOT/'tools/build_legacy_sil.py'),'--profile',a.reference_profile],check=True)
        binary=ROOT/'firmware/sil/build'/a.reference_profile/'legacy_sil';cfg['profile']=a.reference_profile;kind='legacy_2025_reference'
    else:
        binary=build/'controller'
        subprocess.run(['g++','-std=c++17','-O2','-I'+str(ROOT/'firmware/sil'),str(ROOT/'firmware/sil/stop_controller_example.cpp'),'-o',str(binary)],check=True)
    if not a.reference_profile:cfg['profile']='passive'
    cfg['controller_executable']=str(binary.resolve());cfg['middleware']='zenoh';cfg['keep_open']=False
    cfg['controller_kind']=kind
    (out/'requested.yaml').write_text(yaml.safe_dump(cfg,sort_keys=False))
    env=os.environ.copy();env.update(ROS_DOMAIN_ID='66',GZ_PARTITION='ino_mission_'+uuid.uuid4().hex[:12],GZ_IP='127.0.0.1',CANSAT_LOCK_NAME='.mission.lock')
    cmd=[sys.executable,str(ROOT/'tools/supervise.py'),'ros2','launch',str(ROOT/'launch/mission.launch.py'),
         'config:='+str(out/'requested.yaml'),'runtime:='+str(out),'gui:='+str(not a.headless).lower(),
         'rviz:='+str(not a.headless).lower(),'keep_open:=false']
    (out/'request-manifest.json').write_text(json.dumps({'controller_kind':kind,'ros_domain_id':66,'partition':env['GZ_PARTITION'],'wall_timeout_s':a.wall_timeout},indent=2))
    print('Mission: '+str(out),flush=True)
    with (out/'launch.log').open('w') as log:
        proc=subprocess.Popen(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            end=time.monotonic()+a.wall_timeout
            while proc.poll() is None and time.monotonic()<end:time.sleep(.2)
        except KeyboardInterrupt:pass
        finally:stop(proc)
    path=out/'result.json'
    if not path.exists():print('No result; inspect launch.log',flush=True);return 3
    result=json.loads(path.read_text());result['controller_kind']=kind;path.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)
    return 0 if result.get('reason') in ('landed','landing_confirmed','goal_stopped') else 2

if __name__=='__main__':raise SystemExit(main())
