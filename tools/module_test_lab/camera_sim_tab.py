"""Camera experiment panel; ROS runs in owned processes outside the Qt venv."""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime
import json
import os
import re
from pathlib import Path
import signal
import sys
import uuid
from PySide6.QtCore import QProcess,QProcessEnvironment,QTimer,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,
    QPushButton,QDoubleSpinBox,QSpinBox,QComboBox,QGroupBox,QPlainTextEdit,
    QFileDialog,QMessageBox,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView)
from camera_bridge import PACKAGE,load_config,save_config,read_json,list_results,results_csv,ros_environment


class CameraSimTab(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.config=None;self.runtime=None;self.process=None;self.stopping=False;self.rows=[];self.log_file=None
        layout=QVBoxLayout(self)
        heading=QLabel('Gazebo カメラ試験'); heading.setStyleSheet('font-size:18px;font-weight:bold;');layout.addWidget(heading)
        note=QLabel('Gazeboの左右画像・撮影方式・ステレオSLAMを試します。仮想CAN・本番ファームウェアとは独立した試験です。設定は実行ごとに保存します。')
        note.setWordWrap(True);layout.addWidget(note)
        group=QGroupBox('カメラ・撮影条件'); outer=QHBoxLayout(group); forms=[QFormLayout(),QFormLayout()]
        for form in forms:outer.addLayout(form)
        self.fields={}
        specs=[('camera','baseline_m','左右間隔 (m)',.01,.4,3),('camera','height_m','地上高 (m)',.02,1,3),
               ('camera','pitch_down_deg','下向き角度 (度)',-45,75,1),('camera','hfov_deg','水平画角 (度)',30,140,1),
               ('camera','width','横解像度',160,1920,0),('camera','height','縦解像度',120,1080,0),
               ('camera','fps','画像更新 (Hz)',1,30,1),('capture','period_s','撮影周期 (秒)',.01,60,2),
               ('capture','skew_s','左右の時間差 (秒)',0,10,2),('capture','settle_s','停止待機 (秒)',0,60,2)]
        for index,(section,key,label,low,high,decimals) in enumerate(specs):
            field=QDoubleSpinBox() if decimals else QSpinBox()
            field.setRange(low,high)
            if decimals:field.setDecimals(decimals);field.setSingleStep(.01 if high<=60 else 1)
            forms[index%2].addRow(label,field);self.fields[(section,key)]=field
        self.combos={}
        for section,key,label,values in [('capture','mode','撮影方式',[('連続','continuous'),('停止後同時','stop'),('停止後順次','sequential')]),
                                        ('world','surface','地面',[('草地（緑）','grass_green'),('草地（乾燥）','grass_dry'),('低模様','low_texture'),('試験フィールド','lab')]),
                                        ('robot','shape','機体形状',[('展開後CAD','deployed'),('展開前CAD','folded'),('簡易形状','simple')])]:
            field=QComboBox()
            for title,value in values:field.addItem(title,value)
            forms[len(self.combos)%2].addRow(label,field);self.combos[(section,key)]=field
        self.timeout_minutes=QSpinBox();self.timeout_minutes.setRange(1,120);self.timeout_minutes.setValue(10)
        forms[1].addRow('自動試験の上限 (分)',self.timeout_minutes)
        layout.addWidget(group)
        buttons=QHBoxLayout();self.config_buttons=[]
        for title,fn in [('初期設定を読込',self.reset),('設定ファイル読込',self.open_config),('設定JSON保存',self.export_config)]:
            b=QPushButton(title);b.clicked.connect(fn);buttons.addWidget(b);self.config_buttons.append(b)
        layout.addLayout(buttons)
        actions=QHBoxLayout();self.start_button=QPushButton('Gazebo・RVizを起動');self.start_button.clicked.connect(lambda:self.start(False))
        self.test_button=QPushButton('設定した経路で試験・結果保存');self.test_button.clicked.connect(lambda:self.start(True))
        self.stop_button=QPushButton('停止');self.stop_button.clicked.connect(self.stop);self.stop_button.setEnabled(False)
        for b in (self.start_button,self.test_button,self.stop_button):actions.addWidget(b)
        layout.addLayout(actions)
        hint=QLabel('手動走行はINO直下のcamera-teleop.batを使用。自動試験の経路・速度は読込設定のtest項目を使います。走行・描画にはWSLgが必要です。')
        hint.setWordWrap(True);layout.addWidget(hint)
        self.status=QLabel('初期設定を読み込んでください。');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.table=QTableWidget(0,6);self.table.setHorizontalHeaderLabels(['実行','方式','状況','撮影ペア','有効姿勢','位置RMSE (m)'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        layout.addWidget(self.table)
        history=QHBoxLayout()
        for title,fn in [('結果一覧を更新',self.refresh),('選択結果を開く',self.open_result),('比較CSV保存',self.export_results)]:
            b=QPushButton(title);b.clicked.connect(fn);history.addWidget(b)
        layout.addLayout(history)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumBlockCount(600);self.log.setMaximumHeight(140);layout.addWidget(self.log)
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.poll);self.timer.start()
        self.refresh()
        if sys.platform!='linux' or not (PACKAGE/'scripts/start.sh').exists():
            self.start_button.setEnabled(False);self.test_button.setEnabled(False)
            for b in self.config_buttons:b.setEnabled(False)
            self.status.setText('WSL Ubuntu側で、INOリポジトリ内のTest Labを起動してください。')
        else:self.start_button.setEnabled(False);self.test_button.setEnabled(False)

    def active(self):
        return self.process is not None and self.process.state()!=QProcess.NotRunning

    def apply_config(self,config):
        self.config=deepcopy(config)
        for (section,key),field in self.fields.items():field.setValue(config[section][key])
        for (section,key),field in self.combos.items():field.setCurrentIndex(field.findData(config[section][key]))
        self.start_button.setEnabled(True);self.test_button.setEnabled(True)
        self.status.setText('設定を読み込みました。実行時にスナップショットを保存します。')

    def collect(self):
        if self.config is None:raise ValueError('先に初期設定を読み込んでください。')
        config=deepcopy(self.config)
        for (section,key),field in self.fields.items():config[section][key]=field.value()
        for (section,key),field in self.combos.items():config[section][key]=field.currentData()
        return config

    def reset(self):
        try:self.apply_config(load_config())
        except Exception as e:self.error(e)

    def open_config(self):
        path,_=QFileDialog.getOpenFileName(self,'カメラ設定',str(PACKAGE/'config'),'設定 (*.yaml *.yml *.json)')
        if path:
            try:self.apply_config(load_config(path))
            except Exception as e:self.error(e)

    def export_config(self):
        path,_=QFileDialog.getSaveFileName(self,'カメラ設定JSON','camera-config.json','JSON (*.json)')
        if path:
            try:Path(path).write_text(json.dumps(self.collect(),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
            except Exception as e:self.error(e)

    def start(self,experiment=False,extra=()):
        if self.active():return
        try:
            folder=PACKAGE/'logs'/('lab-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
            config_path,checked=save_config(self.collect(),folder)
            self.runtime=folder
            (folder/'lab-request.json').write_text(json.dumps({'kind':'experiment' if experiment else 'interactive',
                'wall_timeout_s':self.timeout_minutes.value()*60 if experiment else None},indent=2),encoding='utf-8')
            if experiment:args=[str(PACKAGE/'scripts/experiment.sh'),'--config',str(config_path),'--runtime',str(folder),'--wall-timeout',str(self.timeout_minutes.value()*60),*extra]
            else:args=[str(PACKAGE/'scripts/start.sh'),'config:='+str(config_path),'runtime:='+str(folder),*extra]
            proc=QProcess(self);self.process=proc;self.stopping=False
            env=QProcessEnvironment()
            for key,value in ros_environment().items():env.insert(key,value)
            proc.setProcessEnvironment(env);proc.setWorkingDirectory(str(PACKAGE))
            proc.setProcessChannelMode(QProcess.MergedChannels)
            proc.readyReadStandardOutput.connect(self.output)
            proc.finished.connect(self.finished);proc.errorOccurred.connect(self.process_error)
            self.log_file=(folder/'controller.log').open('w',encoding='utf-8')
            self.log.clear();self.status.setText('起動中。ログ: '+str(folder))
            for b in (*self.config_buttons,self.start_button,self.test_button):b.setEnabled(False)
            for field in (*self.fields.values(),*self.combos.values(),self.timeout_minutes):field.setEnabled(False)
            self.stop_button.setEnabled(True)
            # A process group owned by this panel, never a global pkill/ROS stop.
            proc.start('/usr/bin/setsid',['/bin/bash',*args])
        except Exception as e:self.error(e)

    def output(self):
        if self.process is None:return
        text=bytes(self.process.readAllStandardOutput()).decode('utf-8',errors='replace')
        self.log.appendPlainText(re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text).rstrip())
        if self.log_file:self.log_file.write(text);self.log_file.flush()

    def stop(self):
        if not self.active() or self.stopping:return
        self.stopping=True;self.status.setText('停止中。地図DBと結果の保存を待っています。');self.stop_button.setEnabled(False)
        self._signal_stop()

    def _signal_stop(self):
        if not self.active():return
        pid=self.process.processId()
        try:
            if pid>0 and os.getpgid(pid)==pid:
                os.killpg(pid,signal.SIGINT)
                return
        except ProcessLookupError:pass
        # QProcess may be starting or setsid may not have run yet.
        QTimer.singleShot(100,self._signal_stop)

    def finished(self,code,status):
        self.output()
        if self.log_file:self.log_file.close();self.log_file=None
        self.status.setText(('停止しました。' if self.stopping else f'終了コード {code}。')+' 結果一覧・ログを確認してください。')
        self.stop_button.setEnabled(False)
        for b in (*self.config_buttons,self.start_button,self.test_button):b.setEnabled(True)
        for field in (*self.fields.values(),*self.combos.values(),self.timeout_minutes):field.setEnabled(True)
        self.refresh()

    def process_error(self,error):
        if error==QProcess.FailedToStart:self.finished(-1,QProcess.CrashExit)

    def poll(self):
        if not self.active() or self.stopping or self.runtime is None:return
        path=self.runtime/'slam-status.json'
        try:
            data=read_json(path)
            self.status.setText(f"{data.get('phase','実行中')} | 撮影ペア {data.get('captured_pairs',0)} | 軌跡 {data.get('slam_path_poses',0)} | 点群 {data.get('cloud_points',0)}")
        except (OSError,ValueError):pass

    def refresh(self):
        self.rows=list_results();self.table.setRowCount(len(self.rows))
        for i,row in enumerate(self.rows):
            values=[row['name'],row['mode'],row['status'],row['pairs'],row['samples'],f"{row['rmse_m']:.4f}" if isinstance(row['rmse_m'],(int,float)) else row['rmse_m']]
            for j,value in enumerate(values):self.table.setItem(i,j,QTableWidgetItem('' if value is None else str(value)))

    def open_result(self):
        index=self.table.currentRow()
        if 0<=index<len(self.rows):QDesktopServices.openUrl(QUrl.fromLocalFile(self.rows[index]['folder']))

    def export_results(self):
        path,_=QFileDialog.getSaveFileName(self,'カメラ比較CSV','camera-results.csv','CSV (*.csv)')
        if path:
            try:Path(path).write_text(results_csv(self.rows),encoding='utf-8-sig')
            except Exception as e:self.error(e)

    def error(self,error):
        self.status.setText(str(error));QMessageBox.warning(self,'カメラ試験',str(error))
