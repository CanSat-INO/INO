"""WSLg settings window: no terminal editing needed for normal use."""
import argparse
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
import uuid
import yaml
from design_config import ROOT,load,geometry_summary

LABELS={
'baseline_m':'左右間隔 [m]','height_m':'レンズ中心の地上高 [m]','forward_m':'機体中心から前方位置 [m]',
'hfov_deg':'水平画角 [deg]（製品の120度とは別）','width':'横解像度 [px]','height':'縦解像度 [px]',
'fps':'仮想カメラ更新頻度 [Hz]','pitch_down_deg':'下向き角度 [deg]','yaw_deg':'全体の左右向き [deg]',
'roll_deg':'全体の傾き [deg]','toe_in_deg':'左右の内向き角 [deg]（負で外向き）',
'left_pitch_delta_deg':'左の下向き角の追加 [deg]','right_pitch_delta_deg':'右の下向き角の追加 [deg]',
'right_height_delta_m':'右の上下位置の追加 [m]','right_forward_delta_m':'右の前後位置の追加 [m]',
'mode':'撮影方式（走行中のSLAMはcontinuous）','settle_s':'停止後の待ち時間 [s]','period_s':'撮影ペアの間隔 [s]',
'skew_s':'左から右の撮影時間差 [s]','acquisition_s':'取得処理の追加待ち時間 [s]',
'transmission_s':'転送の追加待ち時間 [s]','jpeg_quality':'JPEG品質（100で圧縮なし）',
'drop_probability':'画像ペアの欠落確率 [0..1未満]','seed':'乱数シード',
'surface':'地面条件','size_m':'フィールド一辺 [m]','texture_span_m':'草の模様・葉の範囲 [m]',
'grass_height_m':'合成草の高さ [m]','grass_density':'合成草の葉の本数',
'cones':'コーン位置 [[x,y], ...] [m]','cone_height_m':'コーン高さ [m]（仮値）',
'cone_base_m':'台座幅 [m]（仮値）','boxes':'箱 [[x,y,幅,奥行,高さ], ...] [m]',
'mat_enabled':'凹凸マットを設置する [true/false]','mat_center':'マット中心 [x,y] [m]','mat_size':'マット寸法 [幅,奥行] [m]',
'mat_bump_height_m':'マット突起半径 [m]','mat_bump_spacing_m':'マット突起間隔 [m]',
'shape':'機体形状','mass_kg':'参考質量 [kg]（走破性未校正）',
'speed_mps':'自動試験の走行速度 [m/s]','step_m':'1回の移動距離 [m]',
'turn_deg':'撮影地点間の旋回角 [deg]','turn_rate_degps':'旋回速度 [deg/s]',
'stop_s':'各移動後の停止時間 [s]','repeats':'移動回数','route':'経路（returnは前進・後退）'}
CHOICES={'mode':['continuous','stop','sequential'],'surface':['grass_dry','grass_green','low_texture','lab'],'shape':['deployed','folded','simple'],'route':['zigzag','return']}

class Settings:
    def __init__(self,root):
        self.root=root;self.process=None;self.comparison=None;self.log=None;self.out=None
        self.path=ROOT/'config/design.yaml';self.cfg=load();self.variables={}
        root.title('CanSat カメラ・草地SLAM 設定');root.geometry(f"900x{min(800,root.winfo_screenheight()-80)}")
        ttk.Label(root,text='前方 = STEPの穴が2つある面 (+X)。変更は次回起動から反映。\n合成草地・理想レンズでの比較用です。実機校正値・走破性能を保証するものではありません。',padding=10).pack(fill='x')
        tabs=ttk.Notebook(root);tabs.pack(fill='both',expand=True,padx=10)
        for section,title in [('camera','カメラ配置'),('capture','撮影・転送'),('world','草地・障害物'),('robot','機体'),('test','自動比較試験')]:
            outer=ttk.Frame(tabs);tabs.add(outer,text=title)
            canvas=tk.Canvas(outer,highlightthickness=0);bar=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
            canvas.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
            tab=ttk.Frame(canvas,padding=10);item=canvas.create_window((0,0),window=tab,anchor='nw')
            tab.bind('<Configure>',lambda event,c=canvas:c.configure(scrollregion=c.bbox('all')))
            canvas.bind('<Configure>',lambda event,c=canvas,i=item:c.itemconfigure(i,width=event.width))
            for row,(key,value) in enumerate(self.cfg[section].items()):
                ttk.Label(tab,text=LABELS.get(key,key)).grid(row=row,column=0,sticky='w',pady=4,padx=4)
                var=tk.StringVar(value=yaml.safe_dump(value,default_flow_style=True).split('\n...')[0].strip())
                self.variables[(section,key)]=var
                widget=ttk.Combobox(tab,textvariable=var,values=CHOICES[key],state='readonly',width=38) if key in CHOICES else ttk.Entry(tab,textvariable=var,width=42)
                widget.grid(row=row,column=1,sticky='ew',pady=4,padx=4)
            tab.columnconfigure(1,weight=1)
        actions=ttk.Frame(root,padding=10);actions.pack(fill='x')
        for text,command in [('設定を保存',self.save),('設定を読み込み',self.open_config),('視野の概算',self.geometry),('起動',self.start),('停止',self.stop),('比較試験',self.compare)]:
            ttk.Button(actions,text=text,command=command).pack(side='left',padx=3)
        self.status=tk.StringVar(value='待機中。手動操作は teleop.bat を開き、i=前進、j/l=旋回、k=停止。')
        ttk.Label(root,textvariable=self.status,wraplength=860,padding=10).pack(fill='x')
        root.protocol('WM_DELETE_WINDOW',self.close);root.after(500,self.poll)

    def collect(self):
        return {section:{key:yaml.safe_load(self.variables[(section,key)].get()) for key in values} for section,values in self.cfg.items()}

    def save(self):
        try:
            cfg=self.collect();temp=ROOT/'config/.validation.yaml';temp.write_text(yaml.safe_dump(cfg,sort_keys=False))
            checked=load(temp);temp.unlink()
            self.path.write_text(yaml.safe_dump(checked,sort_keys=False));self.cfg=checked
            self.status.set('保存しました: '+str(self.path))
            return True
        except Exception as e:messagebox.showerror('設定エラー',str(e));return False

    def open_config(self):
        selected=filedialog.askopenfilename(initialdir=ROOT/'config',filetypes=[('YAML','*.yaml')])
        if not selected:return
        try:
            self.cfg=load(selected)
            for (section,key),var in self.variables.items():var.set(yaml.safe_dump(self.cfg[section][key],default_flow_style=True).split('\n...')[0].strip())
            self.status.set('読み込みました。保存すると現在の設定になります。')
        except Exception as e:messagebox.showerror('読込エラー',str(e))

    def geometry(self):
        if self.save():messagebox.showinfo('視野の概算（遮蔽・草の影響は含まない）',json.dumps(geometry_summary(self.cfg),indent=2,ensure_ascii=False))

    def start(self):
        if (self.process and self.process.poll() is None) or (self.comparison and self.comparison.poll() is None):return
        if not self.save():return
        self.out=ROOT/'logs'/f'gui-{datetime.datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:4]}'
        self.out.mkdir(parents=True);self.log=(self.out/'launch.log').open('w')
        self.process=subprocess.Popen(['bash',str(ROOT/'scripts/start.sh'),f'runtime:={self.out}'],stdout=self.log,stderr=subprocess.STDOUT,start_new_session=True)
        self.status.set('起動中: '+str(self.out))

    def stop(self):
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid,signal.SIGINT)
            self.status.set('停止処理中（地図DBを保存します）')
            self.root.after(25000,lambda proc=self.process:self.force_stop(proc))
        if self.comparison and self.comparison.poll() is None:
            os.killpg(self.comparison.pid,signal.SIGINT)
            self.status.set('比較試験の停止処理中')

    def force_stop(self,proc):
        if proc and proc.poll() is None:os.killpg(proc.pid,signal.SIGTERM)

    def compare(self):
        if self.comparison and self.comparison.poll() is None:return
        if self.process and self.process.poll() is None:
            messagebox.showinfo('比較試験','先にシミュレーションを停止してください。');return
        if not self.save():return
        self.comparison=subprocess.Popen(['bash',str(ROOT/'scripts/compare.sh'),'--quick'],start_new_session=True)
        self.status.set('現在の設定と、地面・カメラ配置を変えた比較試験を開始しました。結果は logs/design-comparison.md。')

    def poll(self):
        if self.process and self.process.poll() is None and self.out:
            state=self.out/'slam-status.json'
            if state.exists():
                try:
                    info=json.loads(state.read_text())
                    self.status.set(f"{info['phase']} | 撮影ペア {info['captured_pairs']} | 軌跡 {info['slam_path_poses']} | 点群 {info['cloud_points']} 点")
                except (OSError,ValueError,KeyError):pass
        if self.comparison and self.comparison.poll() is not None:
            self.status.set('比較試験終了。logs/design-comparison.md を確認してください。')
            self.comparison=None
        if self.process and self.process.poll() is not None:
            code=self.process.returncode
            self.status.set(f'終了コード {code}。ログ: {self.out}/launch.log')
            self.process=None
            if self.log:self.log.close();self.log=None
        self.root.after(500,self.poll)

    def close(self):
        self.stop();self.root.destroy()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args()
    root=tk.Tk();window=Settings(root)
    if args.check:root.update();root.destroy();print('Settings window initialized successfully')
    else:root.mainloop()
