"""v17 offline virtual phase transitions. No device access or real telemetry."""
from __future__ import annotations

from math import ceil

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QComboBox, QDoubleSpinBox, QSpinBox,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QAbstractItemView, QHeaderView,
)

from v17_phase_core import (
    MODES, SCENARIOS, PHASES, PhaseConfig, configuration,
    run_phase_test, save_csv, save_json,
)

COLORS = {
    'LANDING_WAIT': '#6B7280', 'GNSS_WAIT': '#2459C5',
    'GPS_GUIDANCE': '#0B7796', 'CAM_SEARCH': '#A16B14',
    'CAM_APPROACH': '#6E45A8', 'DONE': '#18806C', 'STOPPED': '#C04C42',
}


class PhaseTimeline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None
        self.setMinimumHeight(200)

    def set_result(self, result):
        self.result = result
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor('#FFFFFF'))
        painter.setPen(QColor('#274361'))
        painter.drawText(18, 20, 'フェーズの推移 / 仮想到達距離')
        if self.result is None or not self.result.rows:
            painter.setPen(QColor('#65758C'))
            painter.drawText(self.rect(), Qt.AlignCenter, '仮想試験を実行するとここに軌跡を表示します')
            painter.end()
            return
        rows = self.result.rows
        left, right = 76.0, max(90.0, self.width() - 30.0)
        width = max(1.0, right - left)
        max_t = max(0.5, float(rows[-1]['time_s']))
        bar_top, bar_h = 40.0, 31.0
        def xx(t):
            return left + width * float(t) / max_t
        painter.setPen(QColor('#3B526F'))
        painter.drawText(12, 59, 'フェーズ')
        for i, row in enumerate(rows):
            x1 = xx(row['time_s'])
            x2 = xx(rows[i+1]['time_s']) if i + 1 < len(rows) else right
            if x2 <= x1:
                x2 = x1 + 1
            painter.fillRect(int(x1), int(bar_top), max(1, int(x2 - x1 + 1)), int(bar_h),
                             QColor(COLORS.get(row['phase'], '#74869A')))
        for transition in self.result.transitions:
            x = xx(transition['time_s'])
            painter.setPen(QPen(QColor('#FFFFFF'), 1))
            painter.drawLine(QPointF(x, bar_top), QPointF(x, bar_top + bar_h))
        painter.setPen(QColor('#253D5B'))
        painter.drawText(int(left), 92, '0 s')
        painter.drawText(int(right) - 58, 92, f'{max_t:g} s')
        top = 109.0
        bottom = max(top + 28, float(self.height()) - 27)
        height = bottom - top
        max_dist = max(1.0, max(row['distance_m'] for row in rows))
        painter.setPen(QColor('#3B526F'))
        painter.drawText(7, int(top + 12), '距離[m]')
        painter.drawText(31, int(top + 25), f'{max_dist:g}')
        painter.drawText(43, int(bottom), '0')
        painter.setPen(QPen(QColor('#E1E9F3'), 1))
        for fraction in (0, .5, 1):
            y = top + fraction * height
            painter.drawLine(QPointF(left, y), QPointF(right, y))
        painter.setPen(QPen(QColor('#147C99'), 2.4))
        path = QPainterPath()
        for i, row in enumerate(rows):
            x = xx(row['time_s'])
            y = bottom - (float(row['distance_m']) / max_dist) * height
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.drawPath(path)
        painter.end()


class PhaseSimulationV17Tab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None
        frame = QVBoxLayout(self)
        frame.setContentsMargins(0, 0, 0, 0)
        self.scroller = QScrollArea()
        self.scroller.setWidgetResizable(True)
        self.scroller.setFrameShape(QScrollArea.NoFrame)
        frame.addWidget(self.scroller)
        body = QWidget()
        self.scroller.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(12, 8, 12, 16)
        root.setSpacing(8)

        title = QLabel('v17｜フェーズ別ミッション・仮想試験')
        title.setStyleSheet('font-size: 20px; color: #143B6D; font-weight: bold;')
        root.addWidget(title)
        intro = QLabel('着地→GNSS測位→GPS誘導→カメラ探索・接近の状態遷移を、仮の数値だけで試します。'
                       '物理モデル・実機コード・通信・ROS 2/Gazeboは使用しません。'
                       'PASSは仮想ルール上の一致であり、実機での成功を保証しません。')
        intro.setWordWrap(True)
        root.addWidget(intro)

        picker = QHBoxLayout()
        self.mode = QComboBox()
        for key, label in MODES.items():
            self.mode.addItem(label, key)
        self.scenario = QComboBox()
        for key, label in SCENARIOS.items():
            self.scenario.addItem(label, key)
        self.scenario.currentIndexChanged.connect(self.reset_scenario)
        self.mode.currentIndexChanged.connect(self.reset_result)
        picker.addWidget(QLabel('実行するフェーズ'))
        picker.addWidget(self.mode, 1)
        picker.addWidget(QLabel('仮想ケース'))
        picker.addWidget(self.scenario, 1)
        root.addLayout(picker)

        group = QGroupBox('仮想パラメータ（実機の校正値ではありません）')
        grid = QGridLayout(group)
        self.controls = {}
        fields = (
            ('landing_impact_mps2', '着地加速度 [m/s²]', 0, 150, 18, 1),
            ('landing_gyro_dps', '着地角速度 [°/s]', 0, 360, 2, 1),
            ('stable_ms', '安定時間 [ms]', 0, 10000, 800, 0),
            ('gnss_fix_delay_s', 'GNSS測位まで [s]', 0, 180, 3, 1),
            ('gps_start_distance_m', 'GPS初期距離 [m]', .5, 500, 12, 1),
            ('gps_speed_mps', 'GPS仮想速度 [m/s]', .1, 10, 1, 1),
            ('cam_detection_delay_s', 'CAM検出まで [s]', 0, 180, 2, 1),
            ('cam_speed_mps', 'CAM仮想速度 [m/s]', .1, 10, .5, 1),
            ('obstacle_after_s', '障害物発生 [s]', -1, 180, -1, 1),
            ('emergency_after_s', '緊急停止 [s]', -1, 180, -1, 1),
            ('max_time_s', '最大実行時間 [s]', 5, 180, 90, 1),
        )
        for i, (key, label, low, high, value, decimals) in enumerate(fields):
            spin = QSpinBox() if decimals == 0 else QDoubleSpinBox()
            if decimals:
                spin.setDecimals(decimals)
            spin.setRange(low, high)
            spin.setValue(value)
            if key in ('obstacle_after_s', 'emergency_after_s'):
                spin.setSpecialValueText('OFF')
            col = i % 2
            row = i // 2
            grid.addWidget(QLabel(label), row, col * 2)
            grid.addWidget(spin, row, col * 2 + 1)
            self.controls[key] = spin
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        root.addWidget(group)

        actions = QHBoxLayout()
        self.run_button = QPushButton('▶ 仮想試験を実行')
        self.run_button.clicked.connect(self.run_simulation)
        self.save_csv_button = QPushButton('時系列CSV保存')
        self.save_csv_button.clicked.connect(self.export_csv)
        self.save_json_button = QPushButton('条件・結果JSON保存')
        self.save_json_button.clicked.connect(self.export_json)
        self.save_csv_button.setEnabled(False)
        self.save_json_button.setEnabled(False)
        actions.addWidget(self.run_button)
        actions.addWidget(self.save_csv_button)
        actions.addWidget(self.save_json_button)
        actions.addStretch(1)
        root.addLayout(actions)
        self.status_label = QLabel('未実行：試験モードとケースを選び「仮想試験を実行」を押してください。')
        self.status_label.setObjectName('v13ExperimentStatus')
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)
        self.timeline = PhaseTimeline()
        root.addWidget(self.timeline)
        self.transitions_label = QLabel('状態遷移：未実行')
        self.transitions_label.setWordWrap(True)
        root.addWidget(self.transitions_label)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ['時刻[s]', 'フェーズ', '仮想距離[m]', 'GNSS', '目標', '指令', 'イベント'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        for col, width in [(0, 80), (1, 116), (2, 108), (3, 70), (4, 70), (5, 138)]:
            self.table.setColumnWidth(col, width)
        self.table.setMinimumHeight(220)
        root.addWidget(self.table)
        foot = QLabel('※ 数値は説明用の単純化モデルです。実際の安全判断・機体制御・着地保証には利用しないでください。')
        foot.setWordWrap(True)
        foot.setStyleSheet('color: #64748B; font-size: 12px;')
        root.addWidget(foot)
        self.reset_scenario()

    def reset_result(self, *_):
        self.result = None
        self.timeline.set_result(None)
        self.table.setRowCount(0)
        self.transitions_label.setText('状態遷移：未実行')
        self.status_label.setText('未実行：仮想試験を実行してください。')
        self.save_csv_button.setEnabled(False)
        self.save_json_button.setEnabled(False)

    def reset_scenario(self, *_):
        conf = configuration(self.mode.currentData(), self.scenario.currentData())
        for key, widget in self.controls.items():
            widget.setValue(getattr(conf, key))
        self.reset_result()

    def run_simulation(self, *_):
        try:
            overrides = {key: widget.value() for key, widget in self.controls.items()}
            conf = configuration(self.mode.currentData(), self.scenario.currentData(), **overrides)
            result = run_phase_test(self.mode.currentData(), self.scenario.currentData(), conf)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, '仮想試験を実行できません', str(exc))
            return
        self.result = result
        self.timeline.set_result(result)
        self.save_csv_button.setEnabled(True)
        self.save_json_button.setEnabled(True)
        summary = '仮想試験' + (' PASS' if result.status == 'PASS' else ' 停止 / 未達')
        self.status_label.setText(
            f'{summary}｜{result.duration_s:g} 秒｜{len(result.rows)}サンプル｜'
            f'{result.reason}　※実機検証ではありません。')
        display = ' → '.join(
            f"{step['time_s']:g}s {PHASES[step['phase']]}" for step in result.transitions)
        self.transitions_label.setText('状態遷移：' + display)
        stride = max(1, ceil(len(result.rows) / 160))
        shown = result.rows[::stride]
        if shown and shown[-1] is not result.rows[-1]:
            shown = list(shown) + [result.rows[-1]]
        self.table.setRowCount(len(shown))
        for index, sample in enumerate(shown):
            vals = (f"{sample['time_s']:g}", sample['phase_ja'],
                    f"{sample['distance_m']:.2f}", str(sample['gnss_fixed']),
                    str(sample['target_visible']), sample['command'], sample['event'])
            for col, value in enumerate(vals):
                item = QTableWidgetItem(value)
                self.table.setItem(index, col, item)
        if stride > 1:
            self.status_label.setText(self.status_label.text() + f'　（表は{stride}サンプルごとに表示、CSVは全件）')

    def export_csv(self, *_):
        self._export('csv')

    def export_json(self, *_):
        self._export('json')

    def _export(self, kind):
        if self.result is None:
            return
        suffix = 'csv' if kind == 'csv' else 'json'
        filetypes = ('CSV (*.csv)' if kind == 'csv' else 'JSON (*.json)')
        suggested = export_path(f'v17_virtual_{self.result.mode}_{self.result.scenario}.{suffix}')
        path, _ = QFileDialog.getSaveFileName(self, '仮想試験結果の保存', suggested, filetypes)
        if not path:
            return
        try:
            (save_csv if kind == 'csv' else save_json)(self.result, path)
        except (OSError, UnicodeError, ValueError) as exc:
            QMessageBox.warning(self, '保存失敗', str(exc))
            return
        QMessageBox.information(self, '保存完了', '仮想試験の結果を保存しました。実機ログではありません。')
