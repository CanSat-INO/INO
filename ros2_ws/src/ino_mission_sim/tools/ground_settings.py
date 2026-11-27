"""Windows-entrypoint settings and owned-session controls, via WSLg Tk."""
import datetime
import json
from pathlib import Path
import signal
import subprocess
import tkinter as tk
from tkinter import ttk,messagebox
import uuid
import yaml
from ground_world import ROOT,load


class Settings:
    def __init__(self,master=None):
        self.root=master or tk.Tk();self.root.title('CanSat 地上自律走行：停止・撮影・再計画');self.root.geometry('650x750')
        self.cfg=load();self.proc=None;self.out=None;self.fields={}
        frame=ttk.Frame(self.root,padding=16);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='SLAM ＋ 走行可能性マップ ＋ 予定経路',font=('',15,'bold')).pack(anchor='w')
        ttk.Label(frame,text='放出なし。停止 → 左右撮影 → 再計画 → 短距離走行。\n走破性の閾値と接地モデルは実測前の仮設定です。').pack(anchor='w',pady=8)
        form=ttk.Frame(frame);form.pack(fill='x')
        definitions=[('goal_x','ゴール X [m]',self.cfg['goal_xy_m'][0]),('goal_y','ゴール Y [m]',self.cfg['goal_xy_m'][1]),
            ('goal_tolerance_m','ゴール中心からの到着範囲 [m]',self.cfg['goal_tolerance_m']),
            ('speed_mps','走行速度 [m/s]',self.cfg['speed_mps']),('drive_step_m','1回の走行距離 [m]',self.cfg['drive_step_m']),
            ('settle_s','停止後の待機 [s]',self.cfg['settle_s']),('capture_period_s','停止中の撮影間隔 [s]',self.cfg['capture_period_s']),
            ('max_step_m','通行判定の段差上限 [m]',self.cfg['max_step_m']),('max_slope_deg','通行判定の傾斜上限 [deg]',self.cfg['max_slope_deg']),
            ('duration_s','シミュレーション上限 [s]',self.cfg['duration_s'])]
        for row,(key,label,value) in enumerate(definitions):
            ttk.Label(form,text=label).grid(row=row,column=0,sticky='w',pady=3)
            variable=tk.StringVar(value=str(value));self.fields[key]=variable
            ttk.Entry(form,textvariable=variable,width=18).grid(row=row,column=1,sticky='w',padx=16)
        ttk.Label(frame,text='地図：緑＝走行しやすい／橙＝難しい／赤＝通行を避ける\n無色＝未観測。ピンク＝予定経路。青＝推定した走行軌跡。\n指定座標へ進み、付近のコーンを複数の向きから確認して停止。').pack(anchor='w',pady=12)
        buttons=ttk.Frame(frame);buttons.pack(fill='x')
        ttk.Button(buttons,text='保存して起動',command=self.start).pack(side='left',padx=4)
        ttk.Button(buttons,text='停止',command=self.stop).pack(side='left',padx=4)
        self.status=tk.StringVar(value='待機中');ttk.Label(frame,textvariable=self.status,wraplength=590,justify='left').pack(anchor='w',pady=15)
        ttk.Label(frame,text='カメラ検証用・放出試験用の設定は変更しません。\nコーン・箱・坂・段差の配置は config/ground_navigation.yaml で変更できます。',wraplength=590).pack(anchor='w')
        self.root.protocol('WM_DELETE_WINDOW',self.close);self.root.after(500,self.refresh)

    def start(self):
        if self.proc is not None and self.proc.poll() is None:return
        try:
            cfg=load()
            cfg['goal_xy_m']=[float(self.fields['goal_x'].get()),float(self.fields['goal_y'].get())]
            for key,var in self.fields.items():
                if key not in ('goal_x','goal_y'):cfg[key]=float(var.get())
            config=ROOT/'config/ground_navigation.yaml';temporary=ROOT/'logs/ground-settings-requested.yaml'
            temporary.parent.mkdir(exist_ok=True);temporary.write_text(yaml.safe_dump(cfg,sort_keys=False));load(temporary)
            config.write_text(yaml.safe_dump(cfg,sort_keys=False))
            self.out=ROOT/'logs'/f'{datetime.datetime.now():%Y%m%d-%H%M%S}-ground-{uuid.uuid4().hex[:4]}'
            self.proc=subprocess.Popen(['bash',str(ROOT/'scripts/start-ground.sh'),'--out',str(self.out)],start_new_session=True)
            self.status.set('起動中：'+str(self.out))
        except (ValueError,KeyError,TypeError,OSError) as error:messagebox.showerror('設定エラー',str(error))

    def stop(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT);self.status.set('この画面で起動したシミュレーションを停止しています。')

    def refresh(self):
        if self.out is not None and (self.out/'navigation.json').exists():
            try:
                state=json.loads((self.out/'navigation.json').read_text());phase={'photograph':'停止・撮影待ち','drive':'短距離走行','turn':'旋回','goal':'ゴール到着','stopped':'停止'}.get(state['phase'],state['phase'])
                distance=state.get('goal_distance_estimated_m');distance='準備中' if distance is None else f'{distance:.2f} m'
                confirmation='確認済み' if state.get('camera_goal_confirmed') else '確認中'
                reasons={'no_safe_path':'安全な経路が見つからないため、停止して再撮影します。',
                    'waiting_for_observed_ground':'進行先の地面を確認できるまで停止します。',
                    'waiting_for_fresh_odometry':'位置情報の更新を待っています。',
                    'ambiguous_cones_near_goal':'候補が複数あるため、向きを変えて確認します。',
                    'confirming_goal_from_another_view':'異なる向きからゴール候補を確認します。',
                    'coordinate_navigation':'指定座標を目指して走行します。',
                    'confirm_goal_with_stopped_slam':'停止画像とSLAMで到着を確認しています。',
                    'align_goal_camera':'推定したゴールの方向へカメラを向けています。',
                    'goal_not_visible_at_expected_bearing':'想定した方向のゴールを確認できるまで停止・再撮影します。',
                    'goal_reached_camera_and_coordinate':'座標と画像で到着を確認しました。',
                    'cross_terrain_before_turning':'段差・傾斜を直進してから向きを変えます。',
                    'terrain_crossing_needs_observed_straight_path':'段差上の進行先を確認できるまで停止します。',
                    'imu_detected_blocked_turn':'旋回指令に対して向きが変わらないため停止しました。',
                    'simulation_timeout':'設定した時間の上限で停止しました。'}
                reason=reasons.get(state['reason'],'')
                self.status.set(f"状態：{phase}　残り推定距離：{distance}\n撮影：{state['photos']}　観測セル：{state['observed_cells']}\nゴール画像：{confirmation} ({state.get('camera_goal_views',0)}視点)\n{reason}\n結果：{self.out}"+('\n終了済み' if self.proc is not None and self.proc.poll() is not None else ''))
            except (OSError,json.JSONDecodeError,KeyError):pass
        self.root.after(500,self.refresh)

    def close(self):
        self.stop();self.root.destroy()


if __name__=='__main__':Settings().root.mainloop()
