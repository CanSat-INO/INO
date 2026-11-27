"""Read-only progress panel plus an explicit SIL stop request."""
import argparse,json
import yaml
from pathlib import Path
import tkinter as tk
from tkinter import ttk
p=argparse.ArgumentParser();p.add_argument('folder');a=p.parse_args();folder=Path(a.folder)
root=tk.Tk();root.title('CanSat 放出・降下・ゴール ミッション');root.geometry('660x540')
text=tk.StringVar(value='Gazebo・仮想センサーの準備中…')
ttk.Label(root,text='ミッション用SIL（PCで組み込みの判断処理を実行）',font=('',14),padding=12).pack()
ttk.Label(root,textvariable=text,font=('',12),padding=15,wraplength=560).pack(fill='both',expand=True)
ttk.Button(root,text='ミッション停止',command=lambda:(folder/'stop.request').write_text('stop')).pack(pady=8)
if yaml.safe_load((folder/'mission.yaml').read_text()).get('descent'):
    ttk.Button(root,text='試験用の開傘指令（自動条件より優先）',command=lambda:(folder/'deploy.request').write_text('deploy')).pack(pady=3)
ttk.Label(root,text='シミュレーション全体の終了：Gazeboを閉じる、または起動端末でCtrl+C',padding=8).pack()
def poll():
    try:
        s=json.loads((folder/'status.json').read_text()) if (folder/'status.json').exists() else None
        value=f"モード：{s['profile']}\n経過：{s['elapsed_s']:.1f}秒　高度：{s['altitude_m']:.2f}m\nフェーズ：{s['phase_name']}\nゴールまで：{s['truth_distance_m']:.2f}m（シミュレーター正解値）\n動作ID：{s['action']}" if s else 'Gazebo・仮想センサーの準備中…'
        if s and s.get('descent'):
            f=s['descent'];wind=f['wind_enu_mps'];velocity=f['velocity_enu_mps']
            value+=f"\n開傘：{f['stage']}　有効面積：{100*f['open_fraction']:.0f}%\n風 ENU：{wind[0]:.1f}, {wind[1]:.1f}, {wind[2]:.1f}m/s\n鉛直速度：{velocity[2]:.2f}m/s（上向き正）"
            if s.get('released') is False:value+='\n放出前の待機中'
        if s and s.get('firmware_guard'):
            g=s['firmware_guard'];missing=[name for bit,name in [(1,'気圧'),(2,'GNSS'),(4,'IMU'),(8,'方位'),(16,'画像')] if not g['health_mask']&bit]
            value+=f"\n制御側の判定：{['待機','降下確認済み','着地確認済み'][g['stage']]}\n入力："+('正常' if not missing else '古い／未受信：'+'・'.join(missing))
        if (folder/'result.json').exists():
            r=json.loads((folder/'result.json').read_text());value+='\n結果：'+('ゴール停止を確認' if r['goal_stopped'] else r['reason'])
            if r.get('landing'):value+=f"　着地時の横流れ：{r['landing']['drift_m']:.1f}m"
        text.set(value)
    except (OSError,ValueError,KeyError):pass
    root.after(500,poll)
root.after(500,poll)
try:root.mainloop()
except KeyboardInterrupt:pass
