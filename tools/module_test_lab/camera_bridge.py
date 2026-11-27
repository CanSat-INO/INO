"""Stdlib-only bridge. Importing Test Lab never imports ROS or simulation libraries."""
from __future__ import annotations
import csv
import io
import json
import os
from pathlib import Path
import subprocess
import sys

PACKAGE = Path(__file__).resolve().parents[2]/'ros2_ws/src/ino_camera_sim'


def ros_environment():
    env=os.environ.copy()
    venv=env.pop('VIRTUAL_ENV',None)
    if venv:env['PATH']=os.pathsep.join(p for p in env.get('PATH','').split(os.pathsep) if Path(p)!=Path(venv)/'bin')
    env.pop('PYTHONHOME',None)
    return env


def load_config(path=None, package=PACKAGE):
    if sys.platform!='linux':raise RuntimeError('この画面はWSL Ubuntu側のTest Labで使用してください。')
    command=['/usr/bin/python3',str(package/'tools/config_io.py')]
    if path:command.append(str(path))
    proc=subprocess.run(command,env=ros_environment(),capture_output=True,text=True,timeout=20)
    if proc.returncode:raise ValueError(proc.stderr.strip() or 'カメラ設定の読込に失敗しました。')
    return json.loads(proc.stdout)


def save_config(config, folder, package=PACKAGE):
    folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
    path=folder/'requested.json'
    path.write_text(json.dumps(config,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return path,load_config(path,package)


def read_json(path, limit=2_000_000):
    path=Path(path)
    if path.stat().st_size>limit:raise ValueError('結果ファイルが大きすぎます。')
    data=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data,dict):raise ValueError('結果はJSONオブジェクトである必要があります。')
    return data


def list_results(package=PACKAGE):
    root=(package/'logs').resolve(); rows=[]
    if not root.exists():return rows
    for path in root.glob('*/result.json'):
        if not path.resolve().is_relative_to(root):continue
        try:
            data=read_json(path)
            if type(data.get('completed')) is not bool:continue
            samples=data.get('matched_samples',0);fraction=data.get('tracking_valid_fraction',0);age=data.get('final_pose_age_s')
            adequate=(isinstance(samples,(int,float)) and samples>=10 and
                      isinstance(fraction,(int,float)) and fraction>=.8 and
                      isinstance(age,(int,float)) and 0<=age<=3)
            status=('完了・追跡継続の目安を満たす' if adequate else '完了・追跡は要確認') if data['completed'] else '未完了'
            rows.append({'folder':str(path.parent),'name':path.parent.name,'mode':data.get('mode',''),
                         'status':status,'pairs':data.get('image_pairs',0),'samples':samples,
                         'fraction':fraction,'rmse_m':data.get('position_rmse_m'),
                         'moving_captures':data.get('captures_during_motion'),
                         'stereo_skew_s':data.get('median_stereo_skew_s')})
        except (OSError,ValueError,TypeError):continue
    return sorted(rows,key=lambda x:x['name'],reverse=True)


def results_csv(rows):
    stream=io.StringIO(newline='')
    fields=['name','mode','status','pairs','samples','fraction','rmse_m','moving_captures','stereo_skew_s']
    writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    return stream.getvalue()
