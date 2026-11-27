"""Stdlib-only ground/descent/native-controller bridge."""
import csv,io,json,subprocess,sys
from pathlib import Path
from camera_bridge import ros_environment,read_json
PACKAGE=Path(__file__).resolve().parents[2]/'ros2_ws/src/ino_mission_sim'

def load_config(mode,path=None):
    if sys.platform!='linux':raise RuntimeError('WSL Ubuntu側で実行してください。')
    command=['/usr/bin/python3',str(PACKAGE/'tools/config_io.py'),'ground' if mode in ('ground','virtual') else 'descent']
    if path:command.append(str(path))
    proc=subprocess.run(command,env=ros_environment(),capture_output=True,text=True,timeout=20)
    if proc.returncode:raise ValueError(proc.stderr.strip())
    return json.loads(proc.stdout)

def results(package=PACKAGE):
    root=(package/'logs').resolve();rows=[]
    for path in root.glob('*/result.json'):
        if not path.resolve().is_relative_to(root):continue
        try:
            d=read_json(path,limit=8_000_000)
            if 'passed' in d and type(d['passed']) is not bool:continue
            landing=d.get('landing') if isinstance(d.get('landing'),dict) else {}
            kind='自律走行' if 'passed' in d else '降下・SIL'
            if 'passed' in d:state='ゴール確認' if d['passed'] else '未達／要確認'
            else:state={'landed':'着地（降下のみ）','landing_confirmed':'着地判定','goal_stopped':'ゴール停止'}.get(d.get('reason'),d.get('reason','未判定'))
            rows.append({'name':path.parent.name,'kind':kind,'state':state,'controller':d.get('controller_kind','ROS自律走行' if 'passed' in d else '未記録'),
                         'distance_m':d.get('true_goal_distance_m',d.get('final_goal_distance_m')), 'landing_speed_mps':landing.get('vertical_speed_mps'),
                         'folder':str(path.parent)})
        except (OSError,ValueError,TypeError):pass
    for path in root.glob('*/module-events.jsonl'):
        if not path.resolve().is_relative_to(root):
            continue
        try:
            with path.open(encoding='utf-8') as events:
                config = json.loads(events.readline(8192))
            if config.get('kind') != 'configuration':
                continue
            modes = config['modes']
            summary = ', '.join(f'{role}={mode}' for role, mode in modes.items())
            rows.append({'name':path.parent.name,'kind':'担当者別試験','state':'イベント記録あり',
                         'controller':summary,'distance_m':None,'landing_speed_mps':None,
                         'folder':str(path.parent)})
        except (OSError, ValueError, KeyError, AttributeError):
            continue
    return sorted(rows,key=lambda r:r['name'],reverse=True)

def csv_results(rows):
    stream=io.StringIO(newline='');fields=['name','kind','state','controller','distance_m','landing_speed_mps']
    w=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows);return stream.getvalue()
