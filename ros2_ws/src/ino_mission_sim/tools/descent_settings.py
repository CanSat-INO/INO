"""Desktop settings for the separate release/opening/wind experiment."""
import math,subprocess,sys,tkinter as tk
from pathlib import Path
from tkinter import ttk,messagebox
import yaml
from mission_config import load_mission
from descent_dynamics import Descent

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'config/firmware/descent_custom.yaml'
cfg=load_mission(TARGET if TARGET.exists() else ROOT/'config/firmware/descent.yaml')
root=tk.Tk();root.title('CanSat 放出・開傘・風の設定');root.geometry('720x820')
frame=ttk.Frame(root,padding=14);frame.pack(fill='both',expand=True)
ttk.Label(frame,text='種子島向け降下試験（未校正の質点モデル）',font=('',15)).grid(row=0,column=0,columnspan=2,pady=8)
entries={}
fields=[('height','放出高度 [m]',cfg['release_height_m']),('mass','全備質量 [kg]',cfg['mass_kg']),('diameter','傘の直径 [m]',cfg['parachute_diameter_m']),('cd','傘の抵抗係数 Cd',cfg['drag_coefficient']),('body','収納時の機体 Cd×面積 [m²]',cfg['descent']['body_cda_m2']),('yaw','放出時の向き [度、東=0・北=90]',cfg.get('release_yaw_deg',0.)),('speed','風速 [m/s]',math.hypot(*cfg['descent']['wind']['mean_enu_mps'][:2])),('direction','風が向かう方位 [度、北=0・東=90]',math.degrees(math.atan2(*cfg['descent']['wind']['mean_enu_mps'][:2]))%360),('trigger_time','放出から開傘開始まで [秒]',cfg['descent']['parachute']['trigger_time_s']),('trigger_alt','高度による開傘開始 [m]',cfg['descent']['parachute']['trigger_altitude_m']),('delay','開傘条件成立からの追加遅延 [秒]',cfg['descent']['parachute']['delay_s']),('opening','開傘にかける時間 [秒]',cfg['descent']['parachute']['opening_s']),('fraction','最大有効面積の割合 [0〜1]',cfg['descent']['parachute']['max_fraction']),('gust','同じ方位への突風の追加風速 [m/s]',0.),('gust_start','突風の開始 [放出後の秒]',2.5),('gust_duration','突風の継続 [秒]',3.),('turbulence','風の変動強度 [m/s、仮モデル]',cfg['descent']['wind']['turbulence_std_mps'])]
for row,(key,label,value) in enumerate(fields,1):
    ttk.Label(frame,text=label).grid(row=row,column=0,sticky='w',pady=3);var=tk.StringVar(value=str(value));entries[key]=var;ttk.Entry(frame,textvariable=var,width=18).grid(row=row,column=1,sticky='ew')
row=len(fields)+1;trigger=tk.StringVar(value=cfg['descent']['parachute']['trigger']);ttk.Label(frame,text='開傘条件').grid(row=row,column=0,sticky='w');ttk.Combobox(frame,textvariable=trigger,values=['time','altitude','command'],state='readonly').grid(row=row,column=1,sticky='ew')
failure=tk.BooleanVar(value=cfg['descent']['parachute']['failure']);stop=tk.BooleanVar(value=cfg.get('stop_on_landing',True))
ttk.Checkbutton(frame,text='不展開の故障を注入',variable=failure).grid(row=row+1,column=0,sticky='w',pady=5)
ttk.Checkbutton(frame,text='着地で終了（外すと去年の調整版で地上誘導）',variable=stop).grid(row=row+2,column=0,columnspan=2,sticky='w')
ttk.Label(frame,text='公式2027要領：投下高度30m前後／風速8m/s以上は投下しない。\n8m/s超の設定はストレス試験。Cd・開傘時間・風は実測に合わせて調整。\ntimeは放出からの時間で、電源投入後の待機時間ではありません。',wraplength=650).grid(row=row+3,column=0,columnspan=2,sticky='w',pady=8)

def save(start=False):
    try:
        v={key:float(value.get()) for key,value in entries.items()}
        if not all(math.isfinite(value) for value in v.values()):raise ValueError('有限の数値を入力してください')
        if v['height']<=0 or min(v['speed'],v['gust'])<0 or v['gust_duration']<=0:raise ValueError('高度・風速・継続時間を確認してください')
        cfg.update(release_height_m=v['height'],release_yaw_deg=v['yaw'],mass_kg=v['mass'],parachute_diameter_m=v['diameter'],drag_coefficient=v['cd'],profile='passive' if stop.get() else 'mission',stop_on_landing=stop.get(),duration_s=60. if stop.get() else 600.)
        cfg['world_size_m']=max(160.,v['height']*6);cfg['geofence_m']=cfg['world_size_m']/2-5
        d=cfg['descent'];d['body_cda_m2']=v['body'];d['parachute'].update(trigger=trigger.get(),trigger_time_s=v['trigger_time'],trigger_altitude_m=v['trigger_alt'],delay_s=v['delay'],opening_s=v['opening'],max_fraction=v['fraction'],failure=failure.get())
        bearing=math.radians(v['direction']);unit=[math.sin(bearing),math.cos(bearing),0.]
        d['wind'].update(mean_enu_mps=[v['speed']*x for x in unit],turbulence_std_mps=v['turbulence'],gusts=[dict(start_s=v['gust_start'],duration_s=v['gust_duration'],delta_enu_mps=[v['gust']*x for x in unit])] if v['gust'] else [])
        Descent(cfg);TARGET.write_text(yaml.safe_dump(cfg,sort_keys=False))
        if start:subprocess.Popen(['bash',str(ROOT/'scripts/start-mission.sh'),'config:='+str(TARGET)],cwd=ROOT)
        else:messagebox.showinfo('保存','descent_custom.yaml に保存しました')
    except (ValueError,OSError) as error:messagebox.showerror('設定を確認',str(error))

buttons=ttk.Frame(frame);buttons.grid(row=row+4,column=0,columnspan=2,pady=8)
ttk.Button(buttons,text='保存して起動',command=lambda:save(True)).pack(side='left',padx=6)
ttk.Button(buttons,text='保存のみ',command=save).pack(side='left',padx=6)
ttk.Button(buttons,text='閉じる',command=root.destroy).pack(side='left',padx=6)
frame.columnconfigure(1,weight=1)
if '--check' in sys.argv:root.after(300,root.destroy)
root.mainloop()
