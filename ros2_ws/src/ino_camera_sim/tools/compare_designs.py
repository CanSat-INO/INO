"""Bounded sensitivity comparison. Does not choose a production design."""
import argparse
import datetime
import uuid
import csv
import json
from pathlib import Path
import subprocess
import sys
import yaml
from design_config import ROOT,load

parser=argparse.ArgumentParser();parser.add_argument('--quick',action='store_true');parser.add_argument('--additional',action='store_true');parser.add_argument('--case');parser.add_argument('--config',default=str(ROOT/'config/design.yaml'));a=parser.parse_args()
if a.additional and (ROOT/'logs/design-comparison.json').exists():
    first=json.loads((ROOT/'logs/design-comparison.json').read_text())[0]
    a.config=str(ROOT/first['folder']/'requested.yaml')
suite=ROOT/'logs'/f'suite-{datetime.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}'
suite.mkdir(parents=True)
frozen=suite/'base.yaml';frozen.write_text(yaml.safe_dump(load(a.config),sort_keys=False))
a.config=str(frozen)
cases=[('current',[]),('low_texture',['world.surface=low_texture']),('toe_pitch',['camera.toe_in_deg=5','camera.pitch_down_deg=30'])]
if not a.quick:
    cases += [('green_grass',['world.surface=grass_green']),('baseline_40mm',['camera.baseline_m=0.04']),('baseline_120mm',['camera.baseline_m=0.12']),('wide120',['camera.hfov_deg=120']),('compressed_delayed',['capture.skew_s=0.2','capture.jpeg_quality=40','capture.transmission_s=0.3','capture.drop_probability=0.1']),('grass_only',['world.cones=[]','world.boxes=[]','world.mat_enabled=false']),('higher_mount',['camera.height_m=0.18']),('toe_continuous',['camera.toe_in_deg=5','capture.mode=continuous']),('grass_only_shortstep',['world.cones=[]','world.boxes=[]','world.mat_enabled=false','test.step_m=0.06'])]
if a.case:
    cases=[case for case in cases if case[0]==a.case]
    if not cases:raise ValueError('Unknown case: '+a.case)
elif a.additional:cases=cases[-4:]
summary=json.loads((ROOT/'logs/design-comparison.json').read_text()) if a.additional else []
for name,overrides in cases:
    before=set((ROOT/'logs').glob('*/requested.yaml'))
    command=[sys.executable,str(ROOT/'tools/run_case.py'),'--config',a.config]
    for value in overrides:command+=['--set',value]
    print('CASE:',name,flush=True)
    result=subprocess.run(command)
    added=set((ROOT/'logs').glob('*/requested.yaml'))-before
    if not added:raise RuntimeError('No evidence directory created')
    folder=max(added,key=lambda x:x.stat().st_mtime).parent
    stats=json.loads((folder/'result.json').read_text()) if (folder/'result.json').exists() else {}
    cfg=yaml.safe_load((folder/'requested.yaml').read_text())
    summary.append({'case':name,'exit_code':result.returncode,'folder':str(folder.relative_to(ROOT)),'surface':cfg['world']['surface'],'baseline_mm':cfg['camera']['baseline_m']*1000,'hfov_deg':cfg['camera']['hfov_deg'],'height_mm':cfg['camera']['height_m']*1000,'pitch_deg':cfg['camera']['pitch_down_deg'],'toe_deg':cfg['camera']['toe_in_deg'],'completed':stats.get('completed',False),'matched_samples':stats.get('matched_samples',0),'valid_fraction':stats.get('tracking_valid_fraction',0),'position_rmse_mm':stats.get('position_rmse_m',0)*1000 if stats.get('matched_samples') else None,'ground_grid_m2':stats.get('observed_ground_grid_area_m2',0),'cloud_points':stats.get('cloud_points',0),'final_pose_age_s':stats.get('final_pose_age_s'),'delay_s':stats.get('odom_delay_median_s')})
    (ROOT/'logs/design-comparison.json').write_text(json.dumps(summary,indent=2))
    with (ROOT/'logs/design-comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=summary[0].keys());writer.writeheader();writer.writerows(summary)
    text=['# カメラ配置・合成草地の比較結果','',
          '数値は合成画像・静的な草・簡易移動モデルでの結果です。現地の再現精度や実機性能を保証しません。',
          '地面グリッド面積は x=0〜3m、y=-2〜2m の固定領域内で、地面近傍に点群が存在した10cmセルの面積です。全域の可視性や地図の正確さとは異なります。',
          'RMSEは初期姿勢を合わせたステレオオドメトリの誤差。少数サンプルや途中の追跡喪失がある場合、誤差だけで良否を判断しないでください。','',
          '| 条件 | 完走 | 有効姿勢数 | 有効率 | 位置RMSE mm | 地面セル面積 m² | 最終姿勢の古さ s |','|---|---|---:|---:|---:|---:|---:|']
    for row in summary:
        error='—' if row['position_rmse_mm'] is None else f"{row['position_rmse_mm']:.2f}"
        age='—' if row['final_pose_age_s'] is None else f"{row['final_pose_age_s']:.2f}"
        text.append(f"| [{row['case']}]({Path(row['folder']).name}/result.json) | {'完了' if row['completed'] else '未完了'} | {row['matched_samples']} | {row['valid_fraction']:.3f} | {error} | {row['ground_grid_m2']:.2f} | {age} |")
    text += ['','実行設定・画像・地図・軌跡・起動ログは各リンク先と同じフォルダに保存。カメラ設定とCSVも合わせて確認してください。']
    (ROOT/'logs/design-comparison.md').write_text('\n'.join(text)+'\n')
from report_designs import report
report()
for suffix in ('json','csv','md'):
    import shutil
    source=ROOT/'logs'/f'design-comparison.{suffix}'
    target=suite/f'design-comparison.{suffix}'
    if suffix=='md':target.write_text(source.read_text().replace('](','](../'))
    else:shutil.copyfile(source,target)
print(ROOT/'logs/design-comparison.md')
