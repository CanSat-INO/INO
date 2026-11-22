"""v11 GUI for portable configuration and honest virtual-CAN run export."""
from __future__ import annotations

from pathlib import Path
from project_store import export_path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout, QGroupBox, QLabel,
    QLineEdit, QDoubleSpinBox, QComboBox, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QFileDialog, QMessageBox,
    QScrollArea,
)

from module_network import SCENARIOS, simulate
from simulation_common import (
    CommonFormatError, default_config, load_config, save_config,
    validate_config, make_run, run_csv, run_json,
)


class SimulationCommonTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_run = None
        self.config = default_config()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.page_scroll = QScrollArea()
        self.page_scroll.setWidgetResizable(True)
        self.page_scroll.setFrameShape(QScrollArea.NoFrame)
        self.page_scroll.setMinimumSize(0, 0)
        outer.addWidget(self.page_scroll)

        body = QWidget()
        self.page_scroll.setWidget(body)
        root = QVBoxLayout(body)

        title = QLabel('v11 シミュレーション共通基盤')
        title.setStyleSheet('font-size:18px; font-weight:bold; color:#17365e;')
        root.addWidget(title)
        note = QLabel('INOの仮想CANを共通形式に変換します。質量・車輪径・段差等は現在は設定メタデータのみで、'
                      '走破性や物理運動の計算には使用されません。ROS 2・REGULUSとの連携もまだ行いません。')
        note.setWordWrap(True)
        root.addWidget(note)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.settings_scroll = scroll
        container = QWidget(); form_root = QVBoxLayout(container)
        robot = QGroupBox('機体パラメータ（v11では物理演算に未反映）')
        rf = QFormLayout(robot)
        self.name = QLineEdit()
        rf.addRow('機体名', self.name)
        self.fields = {}
        for key, label, suffix, maxval in (
            ('mass_kg','質量',' kg',10000),
            ('wheel_diameter_m','タイヤ直径',' m',10000),
            ('wheel_width_m','タイヤ幅',' m',10000),
            ('motor_max_torque_nm','最大トルク',' N·m',10000),
            ('step_height_m','段差高さ',' m',10000),
            ('gravity_mps2','重力加速度',' m/s²',1000),
        ):
            widget = QDoubleSpinBox()
            widget.setDecimals(6)
            widget.setRange(0 if key=='step_height_m' else 0.000001, maxval)
            widget.setSingleStep(0.005)
            widget.setSuffix(suffix)
            self.fields[key] = widget
            rf.addRow(label, widget)
        self.terrain = QLineEdit()
        rf.addRow('地形名', self.terrain)
        self.com = QLineEdit()
        rf.addRow('重心 [x,y,z] (m)', self.com)
        form_root.addWidget(robot)
        initial = QGroupBox('初期状態（将来の3D連携用・現在は未計算）')
        ini = QFormLayout(initial)
        self.position = QLineEdit()
        self.orientation = QLineEdit()
        self.velocity = QLineEdit()
        ini.addRow('位置 [x,y,z] (m)', self.position)
        ini.addRow('姿勢 [x,y,z,w]', self.orientation)
        ini.addRow('速度 [x,y,z] (m/s)', self.velocity)
        form_root.addWidget(initial)
        test = QGroupBox('仮想CANシナリオ')
        tf = QFormLayout(test)
        self.scenario = QComboBox()
        for s in SCENARIOS:
            self.scenario.addItem(s.name, s.key)
        tf.addRow('試験ケース', self.scenario)
        form_root.addWidget(test)
        scroll.setWidget(container)
        scroll.setMaximumHeight(360)
        root.addWidget(scroll)
        actions = QGridLayout()
        for i, (label, fn) in enumerate((
            ('初期値に戻す', self.reset_config),
            ('設定JSON読込', self.open_config),
            ('設定JSON保存', self.write_config),
            ('▶ 仮想CAN実行', self.execute),
            ('結果JSON出力', self.export_json),
            ('結果CSV出力', self.export_csv),
        )):
            b = QPushButton(label)
            b.clicked.connect(fn)
            actions.addWidget(b, i // 3, i % 3)
            if label == '結果JSON出力': self.json_button = b
            if label == '結果CSV出力': self.csv_button = b
        root.addLayout(actions)
        self.summary = QLabel('未実行：設定の保存と仮想CAN試験を利用できます。')
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['時刻(s)','送信元','宛先','メッセージ','イベント','詳細'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(230)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        root.addWidget(self.table, 1)
        self._apply_config(self.config)
        self.name.textChanged.connect(self._clear_run)
        self.terrain.textChanged.connect(self._clear_run)
        self.com.textChanged.connect(self._clear_run)
        self.position.textChanged.connect(self._clear_run)
        self.orientation.textChanged.connect(self._clear_run)
        self.velocity.textChanged.connect(self._clear_run)
        self.scenario.currentIndexChanged.connect(self._clear_run)
        for spin in self.fields.values():
            spin.valueChanged.connect(self._clear_run)
        self._clear_run()

    def _clear_run(self):
        self.last_run = None
        self.table.setRowCount(0)
        self.json_button.setEnabled(False)
        self.csv_button.setEnabled(False)

    @staticmethod
    def _vec(text, count):
        parts = [v.strip() for v in text.split(',')]
        if len(parts) != count:
            raise CommonFormatError(f'ベクトルは{count}要素をカンマ区切りで入力してください。')
        try:
            return [float(v) for v in parts]
        except ValueError as exc:
            raise CommonFormatError('ベクトルには数値を入力してください。') from exc

    def _read_config(self):
        cfg = default_config()
        cfg['robot']['name'] = self.name.text().strip()
        for key in ('mass_kg','wheel_diameter_m','wheel_width_m','motor_max_torque_nm'):
            cfg['robot'][key] = self.fields[key].value()
        cfg['robot']['center_of_mass_m'] = self._vec(self.com.text(),3)
        cfg['environment']['terrain'] = self.terrain.text().strip()
        for key in ('step_height_m','gravity_mps2'):
            cfg['environment'][key] = self.fields[key].value()
        for key,widget,n in (('position_m',self.position,3),('orientation_xyzw',self.orientation,4),('velocity_mps',self.velocity,3)):
            cfg['initial_state'][key] = self._vec(widget.text(),n)
        cfg['scenario']['key'] = self.scenario.currentData()
        return validate_config(cfg)

    def _apply_config(self, cfg):
        self.config = validate_config(cfg)
        r,e,s = (self.config[x] for x in ('robot','environment','initial_state'))
        self.name.setText(r['name'])
        for key in ('mass_kg','wheel_diameter_m','wheel_width_m','motor_max_torque_nm'):
            self.fields[key].setValue(r[key])
        for key in ('step_height_m','gravity_mps2'):
            self.fields[key].setValue(e[key])
        self.terrain.setText(e['terrain'])
        self.com.setText(', '.join(map(str,r['center_of_mass_m'])))
        for key,widget in (('position_m',self.position),('orientation_xyzw',self.orientation),('velocity_mps',self.velocity)):
            widget.setText(', '.join(map(str,s[key])))
        idx = self.scenario.findData(self.config['scenario']['key'])
        self.scenario.setCurrentIndex(idx)
        self._clear_run()

    def reset_config(self, *_):
        self._apply_config(default_config())
        self.summary.setText('初期値を表示しました。')

    def open_config(self, *_):
        path,_ = QFileDialog.getOpenFileName(self,'設定JSONを読み込む','','JSON (*.json)')
        if not path: return
        try:
            cfg = load_config(path)
            self._apply_config(cfg)
            self.summary.setText(f'設定を読み込みました: {Path(path).name}（前回の実行結果は破棄）')
        except (OSError, UnicodeError, CommonFormatError) as exc:
            QMessageBox.warning(self,'設定読込エラー',str(exc))

    def write_config(self, *_):
        try:
            cfg = self._read_config()
        except CommonFormatError as exc:
            QMessageBox.warning(self,'入力エラー',str(exc)); return
        path,_ = QFileDialog.getSaveFileName(self,'設定JSONを保存',export_path('cansat_config_v11.json'),'JSON (*.json)')
        if not path: return
        try:
            save_config(path,cfg)
            self.summary.setText(f'設定を保存しました: {Path(path).name}')
        except OSError as exc:
            QMessageBox.warning(self,'保存エラー',str(exc))

    def execute(self, *_):
        self._clear_run()
        try:
            cfg = self._read_config()
            result = simulate(cfg['scenario']['key'])
            run = make_run(cfg,result)
        except (CommonFormatError,ValueError,RuntimeError) as exc:
            self.summary.setText('実行失敗。結果出力は無効です。')
            QMessageBox.warning(self,'実行エラー',str(exc)); return
        self.config = cfg
        self.last_run = run
        self.json_button.setEnabled(True)
        self.csv_button.setEnabled(True)
        self.table.setRowCount(len(run['samples']))
        for i,row in enumerate(run['samples']):
            vals = [f"{row['time_s']:.3f}",row['source'],row['target'],row['message'],row['event'],row['detail']]
            for j,v in enumerate(vals):
                self.table.setItem(i,j,QTableWidgetItem(v))
        self.summary.setText(f"仮想CAN評価: {run['result']['evaluation']} / イベント{len(run['samples'])}件。"
                             ' 機体・環境パラメータは物理演算に未反映。位置・姿勢・速度は未計算です。')

    def _export(self, suffix, fn):
        if self.last_run is None:
            QMessageBox.warning(self,'未実行','先に仮想CAN試験を実行してください。'); return
        path,_ = QFileDialog.getSaveFileName(self,'結果出力',export_path(f'cansat_v11_run.{suffix}'),f'{suffix.upper()} (*.{suffix})')
        if not path: return
        try:
            Path(path).write_text(fn(self.last_run),encoding='utf-8-sig' if suffix=='csv' else 'utf-8',newline='')
            self.summary.setText(f'結果を出力しました: {Path(path).name}（物理演算未実施）')
        except (OSError,CommonFormatError) as exc:
            QMessageBox.warning(self,'出力エラー',str(exc))

    def export_json(self, *_): self._export('json',run_json)
    def export_csv(self, *_): self._export('csv',run_csv)
