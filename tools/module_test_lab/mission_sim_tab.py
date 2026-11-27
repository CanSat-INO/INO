"""Test Lab front end for owned ground/descent/SIL processes."""
from copy import deepcopy
from datetime import datetime
import json,os,re,signal,uuid,sys
from pathlib import Path
from PySide6.QtCore import QProcess,QProcessEnvironment,QTimer,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QComboBox,QPushButton,QDoubleSpinBox,QSpinBox,QCheckBox,QLineEdit,QFileDialog,QMessageBox,QPlainTextEdit,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView)
from camera_bridge import ros_environment,read_json
from mission_bridge import PACKAGE,load_config,results,csv_results

class MissionSimTab(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent);self.config=None;self.runtime=None;self.process=None;self.stopping=False;self.rows=[];self.log_file=None
        layout=QVBoxLayout(self)
        note=QLabel('自律走行／降下・開傘／今後の本番ロジックのSIL接続。SILはPC用C++アダプターであり、ESP32バイナリやRTOSのエミュレーションではありません。')
        note.setWordWrap(True);layout.addWidget(note)
        form=QFormLayout();self.mode=QComboBox()
        for title,key in [('地上自律走行（停止撮影・経路計画）','ground'),('仮想センサー単独（外部ROS接続）','virtual'),('降下・開傘（着地まで）','descent'),('降下＋ユーザーC++ SILアダプター','sil')]:self.mode.addItem(title,key)
        self.mode.currentIndexChanged.connect(self.reset);form.addRow('試験',self.mode)
        self.bench = QComboBox()
        for title, key in [('センサーのみ', 'none'), ('Main試験', 'main'), ('Camera試験', 'camera'),
                           ('Drive試験', 'drive'), ('画像処理試験', 'vision'), ('地上局開発', 'station'), ('全仮想試験', 'all')]:
            self.bench.addItem(title, key)
        self.bench.setEnabled(False)
        form.addRow('担当者別構成', self.bench)
        self.height=self.spin(30,.1,200);self.wind=self.spin(6,-30,30);self.opening=self.spin(1.5,0,60)
        self.goal_x=self.spin(3.6,-50,50);self.goal_y=self.spin(0,-50,50);self.speed=self.spin(.06,.001,.2)
        for label,w in [('放出高度 (m)',self.height),('東向き風速 (m/s)',self.wind),('開傘所要時間 (秒)',self.opening),('ゴールX (m)',self.goal_x),('ゴールY (m)',self.goal_y),('地上速度 (m/s)',self.speed)]:form.addRow(label,w)
        self.source=QLineEdit();self.source.setPlaceholderText('cansat/内のPC用.cppアダプターを指定（本番コードは今後追加）')
        row=QHBoxLayout();row.addWidget(self.source);browse=QPushButton('選択');browse.clicked.connect(self.select_source);row.addWidget(browse);form.addRow('SILアダプター',row)
        self.on_landing=QCheckBox('着地で試験を終了');self.on_landing.setChecked(True);form.addRow(self.on_landing)
        self.headless=QCheckBox('Gazebo/RViz画面を出さずに実行');form.addRow(self.headless)
        self.timeout=QSpinBox();self.timeout.setRange(1,120);self.timeout.setValue(30);form.addRow('実時間の上限 (分)',self.timeout)
        layout.addLayout(form)
        actions=QHBoxLayout();self.actions=[]
        for title,fn in [('初期設定を読込',self.reset),('設定JSON/YAML読込',self.open_config),('起動',self.start)]:
            b=QPushButton(title);b.clicked.connect(fn);actions.addWidget(b);self.actions.append(b)
        self.stop_button=QPushButton('停止');self.stop_button.clicked.connect(self.stop);self.stop_button.setEnabled(False);actions.addWidget(self.stop_button);layout.addLayout(actions)
        self.status=QLabel('初期設定を読み込んでください。');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.table=QTableWidget(0,5);self.table.setHorizontalHeaderLabels(['実行','試験','結果','制御コード種別','着地鉛直速度 (m/s)']);self.table.setSelectionBehavior(QAbstractItemView.SelectRows);self.table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents);layout.addWidget(self.table)
        row=QHBoxLayout()
        for title,fn in [('結果を更新',self.refresh),('選択結果を開く',self.open_result),('比較CSV保存',self.export)]:b=QPushButton(title);b.clicked.connect(fn);row.addWidget(b)
        layout.addLayout(row);self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumBlockCount(600);self.log.setMaximumHeight(140);layout.addWidget(self.log)
        self.timer=QTimer(self);self.timer.setInterval(1000);self.timer.timeout.connect(self.poll);self.timer.start();self.refresh()
        if sys.platform!='linux' or not any(Path(f'/opt/ros/{distro}/setup.bash').is_file() for distro in ('jazzy', 'lyrical')) or not (PACKAGE/'tools/run_mission.py').exists():
            for b in self.actions:b.setEnabled(False)
            self.mode.setEnabled(False);self.status.setText('この試験にはROS/Gazebo環境が必要です。通常のsetup-simulation.batを実行してください。')
    @staticmethod
    def spin(value,low,high):
        w=QDoubleSpinBox();w.setRange(low,high);w.setDecimals(3);w.setValue(value);return w
    def error(self,e):self.status.setText(str(e));QMessageBox.warning(self,'ミッション試験',str(e))
    def apply(self,cfg):
        self.bench.setEnabled(self.mode.currentData() == 'virtual')
        self.config=deepcopy(cfg);ground=self.mode.currentData() in ('ground','virtual')
        if ground:self.goal_x.setValue(cfg['goal_xy_m'][0]);self.goal_y.setValue(cfg['goal_xy_m'][1]);self.speed.setValue(cfg['speed_mps'])
        else:self.height.setValue(cfg['release_height_m']);self.wind.setValue(cfg['descent']['wind']['mean_enu_mps'][0]);self.opening.setValue(cfg['descent']['parachute']['opening_s']);self.on_landing.setChecked(cfg.get('stop_on_landing',True))
        for w in (self.goal_x,self.goal_y,self.speed):w.setEnabled(ground)
        for w in (self.height,self.wind,self.opening,self.on_landing):w.setEnabled(not ground)
        self.timeout.setEnabled(self.mode.currentData() != 'virtual');self.source.setEnabled(self.mode.currentData()=='sil');self.status.setText('設定を読み込みました。'+('PC用C++アダプターを指定してください。' if self.mode.currentData()=='sil' else '起動すると実行条件のコピーを保存します。'))
    def reset(self,*_):
        if self.active():return
        try:self.apply(load_config(self.mode.currentData()))
        except Exception as e:self.error(e)
    def open_config(self):
        path,_=QFileDialog.getOpenFileName(self,'試験設定',str(PACKAGE/'config'),'設定 (*.yaml *.yml *.json)')
        if path:
            try:self.apply(load_config(self.mode.currentData(),path))
            except Exception as e:self.error(e)
    def collect(self):
        if self.config is None:raise ValueError('先に初期設定を読み込んでください。')
        cfg=deepcopy(self.config)
        if self.mode.currentData() in ('ground','virtual'):cfg['goal_xy_m']=[self.goal_x.value(),self.goal_y.value()];cfg['speed_mps']=self.speed.value()
        else:
            cfg['release_height_m']=self.height.value();cfg['descent']['wind']['mean_enu_mps'][0]=self.wind.value();cfg['descent']['parachute']['opening_s']=self.opening.value();cfg['stop_on_landing']=self.on_landing.isChecked() if self.mode.currentData()=='sil' else True
        return cfg
    def select_source(self):
        path,_=QFileDialog.getOpenFileName(self,'PC用C++アダプター',str(PACKAGE.parents[2]/'cansat'),'C++ (*.cpp *.cc *.cxx)')
        if path:self.source.setText(path)
    def active(self):return self.process is not None and self.process.state()!=QProcess.NotRunning
    def start(self):
        if self.active():return
        try:
            cfg=self.collect();mode=self.mode.currentData()
            if mode=='sil' and not Path(self.source.text()).is_file():raise ValueError('本番の判断ロジックを呼ぶPC用.cppアダプターを指定してください。')
            out=PACKAGE/'logs'/('lab-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);out.mkdir(parents=True)
            path=out/'input.json';path.write_text(json.dumps(cfg,indent=2,allow_nan=False));load_config(mode,path)
            args=['--config',str(path),'--out',str(out),'--wall-timeout',str(self.timeout.value()*60)]
            if self.headless.isChecked():args.append('--headless')
            if mode=='sil':args+=['--controller-source',self.source.text()]
            script=PACKAGE/'scripts'/('start-ground.sh' if mode=='ground' else 'start-mission.sh')
            if mode == 'virtual':
                script = PACKAGE/'scripts/start-virtual.sh'
                args = [f'config:={path}', f'runtime:={out}',
                        f'gui:={str(not self.headless.isChecked()).lower()}',
                        f'bench:={self.bench.currentData()}',
                        f'drive:={str(self.bench.currentData() in ("main", "drive", "all")).lower()}']
            self.config=deepcopy(cfg);self.runtime=out;self.stopping=False;proc=QProcess(self);self.process=proc;env=QProcessEnvironment()
            for k,v in ros_environment().items():env.insert(k,v)
            proc.setProcessEnvironment(env);proc.setWorkingDirectory(str(PACKAGE));proc.setProcessChannelMode(QProcess.MergedChannels)
            proc.readyReadStandardOutput.connect(self.output);proc.finished.connect(self.finished);proc.errorOccurred.connect(self.failed)
            self.log_file=(out/'controller.log').open('w');self.log.clear();self.status.setText((f'外部ROS接続 domain {env.value("ROS_DOMAIN_ID", "67")}: ' if mode == 'virtual' else '起動中: ')+str(out))
            self.mode.setEnabled(False)
            self.bench.setEnabled(False)
            for w in (self.height,self.wind,self.opening,self.goal_x,self.goal_y,self.speed,self.source,self.on_landing,self.headless,self.timeout):w.setEnabled(False)
            for b in self.actions:b.setEnabled(False)
            self.stop_button.setEnabled(True);proc.start('/usr/bin/setsid',['/bin/bash',str(script),*args])
        except Exception as e:self.error(e)
    def output(self):
        text=bytes(self.process.readAllStandardOutput()).decode('utf-8',errors='replace');self.log.appendPlainText(re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',text).rstrip())
        if self.log_file:self.log_file.write(text);self.log_file.flush()
    def stop(self):
        if not self.active() or self.stopping:return
        self.stopping=True;self.stop_button.setEnabled(False);self.status.setText('停止・結果保存中');self.signal_stop()
    def signal_stop(self):
        if not self.active():return
        pid=self.process.processId()
        try:
            if pid>0 and os.getpgid(pid)==pid:os.killpg(pid,signal.SIGINT);return
        except ProcessLookupError:pass
        QTimer.singleShot(100,self.signal_stop)
    def finished(self,code,status):
        self.output()
        if self.log_file:self.log_file.close();self.log_file=None
        self.mode.setEnabled(True)
        self.headless.setEnabled(True);self.timeout.setEnabled(True)
        if self.config is not None:self.apply(self.config)
        for b in self.actions:b.setEnabled(True)
        self.stop_button.setEnabled(False);self.status.setText(f'終了コード {code}。結果とログを確認してください。');self.refresh()
    def failed(self,error):
        if error==QProcess.FailedToStart:self.finished(-1,QProcess.CrashExit)
    def poll(self):
        if not self.active() or self.stopping or not self.runtime:return
        for name in ('navigation.json','status.json'):
            try:
                d=read_json(self.runtime/name);self.status.setText(str({k:d[k] for k in ('phase','reason','done','altitude_m','truth_distance_m','goal_distance_m') if k in d}));break
            except (OSError,ValueError):pass
    def refresh(self):
        self.rows=results();self.table.setRowCount(len(self.rows))
        for i,r in enumerate(self.rows):
            for j,v in enumerate([r['name'],r['kind'],r['state'],{'user_native_adapter':'ユーザーC++アダプター','connection_example_only':'停止する接続例','legacy_2025_reference':'去年版の参照コード'}.get(r['controller'],r['controller']),f"{r['landing_speed_mps']:.3f}" if isinstance(r['landing_speed_mps'],(int,float)) else r['landing_speed_mps']]):self.table.setItem(i,j,QTableWidgetItem('' if v is None else str(v)))
    def open_result(self):
        i=self.table.currentRow()
        if 0<=i<len(self.rows):QDesktopServices.openUrl(QUrl.fromLocalFile(self.rows[i]['folder']))
    def export(self):
        path,_=QFileDialog.getSaveFileName(self,'試験比較CSV','mission-results.csv','CSV (*.csv)')
        if path:Path(path).write_text(csv_results(self.rows),encoding='utf-8-sig')
