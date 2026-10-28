"""v19: offline comparison of experiment CSV versus virtual or reference CSV."""
from __future__ import annotations

from math import ceil
from pathlib import Path

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QGroupBox,
    QPushButton, QLineEdit, QDoubleSpinBox, QCheckBox, QFileDialog,
    QMessageBox, QScrollArea, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)

from v19_compare_core import read_log, compare_logs, common_signals, save_result

ROOT = Path(__file__).resolve().parent


class ComparePlot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None
        self.setMinimumHeight(270)

    def set_result(self, result):
        self.result = result
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor('#FFFFFF'))
        painter.setPen(QColor('#19345C'))
        painter.drawText(20, 25, '実験CSVと参考CSVの重ね合わせ（比較可能な時刻のみ）')
        if not self.result:
            painter.setPen(QColor('#66758B'))
            painter.drawText(self.rect(), Qt.AlignCenter, 'CSVを読み込み「比較」を押すとグラフが表示されます')
            painter.end()
            return
        pts = self.result.points
        if not pts:
            painter.end()
            return
        l, r, top, bottom = 72., max(74., self.width()-28.), 56., max(80., self.height()-35.)
        xmin, xmax = pts[0].time_s, pts[-1].time_s
        if xmax <= xmin:
            xmax = xmin + 1
        values = [v for p in pts for v in (p.measured, p.reference)]
        ymin, ymax = min(values), max(values)
        if ymax-ymin < 1e-9:
            ymax += 1
            ymin -= 1
        else:
            margin = (ymax-ymin)*.08
            ymin -= margin
            ymax += margin
        def x(t): return l + (t-xmin)/(xmax-xmin)*(r-l)
        def y(v): return bottom - (v-ymin)/(ymax-ymin)*(bottom-top)
        painter.setPen(QPen(QColor('#E1E9F3'), 1))
        for i in range(5):
            yy = top + i*(bottom-top)/4
            painter.drawLine(QPointF(l, yy), QPointF(r, yy))
        painter.setPen(QColor('#4D647F'))
        painter.drawText(6, int(top+10), f'{ymax:.3g}')
        painter.drawText(6, int(bottom), f'{ymin:.3g}')
        painter.drawText(int(l), int(bottom+23), f'{xmin:.2f} s')
        painter.drawText(int(r)-70, int(bottom+23), f'{xmax:.2f} s')
        stride = max(1, ceil(len(pts)/1200))
        sampled = list(pts[::stride])
        if sampled[-1] is not pts[-1]:
            sampled.append(pts[-1])
        for field, color in [('reference', '#087E9A'), ('measured', '#2357C5')]:
            painter.setPen(QPen(QColor(color), 2.2))
            path = QPainterPath()
            for i, p in enumerate(sampled):
                pt = QPointF(x(p.time_s), y(getattr(p, field)))
                if i == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
            painter.drawPath(path)
        painter.setPen(QColor('#2357C5'))
        painter.drawText(int(l), 44, '● 測定CSV')
        painter.setPen(QColor('#087E9A'))
        painter.drawText(int(l+110), 44, '● 参考CSV（線形補間）')
        painter.end()


class ExperimentCompareV19Tab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.measured_log = None
        self.reference_log = None
        self.result = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(self.scroll)
        body = QWidget()
        self.scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(16, 10, 16, 18)
        root.setSpacing(10)
        title = QLabel('v19｜実験ログ・仮想結果の時系列比較')
        title.setStyleSheet('font-size: 20px; font-weight: 800; color: #183A69;')
        root.addWidget(title)
        intro = QLabel('実験CSVとv17の仮想試験CSVなどをオフラインで比較します。'
                       '同じ物理量・単位である2信号を選び、経過時間を合わせて参考値を線形補間します。'
                       'これは実機制御やシミュレーションの妥当性を保証する試験ではありません。')
        intro.setWordWrap(True)
        root.addWidget(intro)
        paths_group = QGroupBox('読み込むCSV（時間列は time_s / time_ms 等、単位を必ず確認）')
        path_form = QFormLayout(paths_group)
        self.measured_path = QLineEdit()
        self.reference_path = QLineEdit()
        self.measured_path.setPlaceholderText('実験担当者のログ.csv')
        self.reference_path.setPlaceholderText('v17「時系列CSV保存」で出力したファイル.csv')
        for label, field, callback in [
            ('実験・測定CSV', self.measured_path, lambda: self.choose_path('measured')),
            ('仮想・参考CSV', self.reference_path, lambda: self.choose_path('reference')),
        ]:
            line = QHBoxLayout()
            line.addWidget(field, 1)
            pick = QPushButton('参照...')
            pick.clicked.connect(callback)
            line.addWidget(pick)
            path_form.addRow(label, line)
        root.addWidget(paths_group)
        actions = QHBoxLayout()
        demo = QPushButton('比較サンプルをセット')
        demo.clicked.connect(self.use_demo)
        load = QPushButton('CSVを読み込む')
        load.clicked.connect(self.load_files)
        actions.addWidget(demo)
        actions.addWidget(load)
        actions.addStretch(1)
        root.addLayout(actions)
        fields = QGroupBox('比較条件')
        field_grid = QFormLayout(fields)
        self.measured_signal = QComboBox()
        self.reference_signal = QComboBox()
        self.measured_signal.currentIndexChanged.connect(self.invalidate)
        self.reference_signal.currentIndexChanged.connect(self.invalidate)
        field_grid.addRow('測定側の信号', self.measured_signal)
        field_grid.addRow('参考側の信号', self.reference_signal)
        self.shift = QDoubleSpinBox()
        self.shift.setDecimals(2)
        self.shift.setRange(-86400, 86400)
        self.shift.setSingleStep(0.5)
        self.shift.setSuffix(' 秒')
        self.shift.valueChanged.connect(self.invalidate)
        field_grid.addRow('参考CSVの時間ずらし（+で後ろへ）', self.shift)
        self.unit_check = QCheckBox('2つの信号の物理量・単位が同一であることを確認しました')
        self.unit_check.toggled.connect(self.invalidate)
        field_grid.addRow(self.unit_check)
        root.addWidget(fields)
        line = QHBoxLayout()
        self.compare_button = QPushButton('▶ 時系列を比較')
        self.compare_button.clicked.connect(self.do_compare)
        self.export_csv_button = QPushButton('差分CSV保存')
        self.export_json_button = QPushButton('指標・条件JSON保存')
        self.export_csv_button.clicked.connect(lambda: self.export_result('csv'))
        self.export_json_button.clicked.connect(lambda: self.export_result('json'))
        self.export_csv_button.setEnabled(False)
        self.export_json_button.setEnabled(False)
        line.addWidget(self.compare_button)
        line.addWidget(self.export_csv_button)
        line.addWidget(self.export_json_button)
        line.addStretch(1)
        root.addLayout(line)
        self.status = QLabel('未読込：比較サンプルをセットするかCSVを選んでください。')
        self.status.setObjectName('v13ExperimentStatus')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.plot = ComparePlot()
        root.addWidget(self.plot)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['時刻[s]', '測定値', '参考値（補間）', '差（測定−参考）'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(200)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table)
        caution = QLabel('比較結果は「一致度の参考値」です。時間ずれ、校正、センサーの誤差、'
                         '座標系、条件の違いを考慮せずに合否判定しないでください。'
                         '時刻が重ならない部分は補間・外挿せず除外します。')
        caution.setWordWrap(True)
        caution.setStyleSheet('color: #64748B; font-size: 12px;')
        root.addWidget(caution)

    def invalidate(self, *_):
        self.result = None
        self.export_csv_button.setEnabled(False)
        self.export_json_button.setEnabled(False)
        self.plot.set_result(None)
        self.table.setRowCount(0)

    def choose_path(self, which):
        path, _ = QFileDialog.getOpenFileName(self, 'CSVファイルを選択', '', 'CSV (*.csv)')
        if path:
            (self.measured_path if which == 'measured' else self.reference_path).setText(path)
            self.measured_log = None
            self.reference_log = None
            self.invalidate()

    def use_demo(self):
        self.measured_path.setText(str(ROOT / 'v19_samples' / 'example_measured.csv'))
        self.reference_path.setText(str(ROOT / 'v19_samples' / 'example_v17_reference.csv'))
        self.shift.setValue(0.0)
        self.unit_check.setChecked(False)
        self.load_files()

    def load_files(self):
        self.invalidate()
        try:
            m = read_log(self.measured_path.text().strip())
            r = read_log(self.reference_path.text().strip())
        except (OSError, ValueError, TypeError) as exc:
            self.measured_log = self.reference_log = None
            QMessageBox.warning(self, 'CSVの読込に失敗', str(exc))
            self.status.setText('CSVの読込に失敗しました。時間列・数値・ファイルパスを確認してください。')
            return
        self.measured_log, self.reference_log = m, r
        self.measured_signal.blockSignals(True)
        self.reference_signal.blockSignals(True)
        self.measured_signal.clear()
        self.reference_signal.clear()
        for key in m.signals:
            self.measured_signal.addItem(f'{key}  [{m.units.get(key, "")}]', key)
        for key in r.signals:
            self.reference_signal.addItem(f'{key}  [{r.units.get(key, "")}]', key)
        common = common_signals(m, r)
        preferred = 'distance_m' if 'distance_m' in common else (common[0] if common else None)
        if preferred:
            self.measured_signal.setCurrentIndex(list(m.signals).index(preferred))
            self.reference_signal.setCurrentIndex(list(r.signals).index(preferred))
        self.measured_signal.blockSignals(False)
        self.reference_signal.blockSignals(False)
        self.status.setText(f'読込完了：測定側 {m.row_count}行／参考側 {r.row_count}行。'
                            '確認欄にチェック後「時系列を比較」を押してください。')

    def do_compare(self):
        if self.measured_log is None or self.reference_log is None:
            QMessageBox.information(self, 'CSV未読込', '先に「CSVを読み込む」を押してください。')
            return
        try:
            result = compare_logs(
                self.measured_log, self.reference_log,
                self.measured_signal.currentData(), self.reference_signal.currentData(),
                unit_confirmed=self.unit_check.isChecked(), time_shift_s=self.shift.value(),
            )
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, '比較できません', str(exc))
            return
        self.result = result
        self.plot.set_result(result)
        self.export_csv_button.setEnabled(True)
        self.export_json_button.setEnabled(True)
        self.status.setText(
            f'比較完了（合否判定ではありません）｜比較 {result.matched}/{result.measured_valid}件 '
            f'({result.coverage_fraction:.1%})｜MAE {result.mae:.4g}｜RMSE {result.rmse:.4g}｜'
            f'平均差 {result.bias:.4g}｜最大絶対差 {result.max_abs_error:.4g}｜単位：{result.unit}')
        stride = max(1, ceil(len(result.points)/170))
        rows = list(result.points[::stride])
        if rows[-1] is not result.points[-1]:
            rows.append(result.points[-1])
        self.table.setRowCount(len(rows))
        for i, p in enumerate(rows):
            for j, val in enumerate((p.time_s, p.measured, p.reference, p.error)):
                self.table.setItem(i, j, QTableWidgetItem(f'{val:.5g}'))

    def export_result(self, kind):
        if self.result is None:
            return
        suggested = str(Path.home() / f'cansat_v19_comparison.{kind}')
        path, _ = QFileDialog.getSaveFileName(self, '比較結果の保存', suggested,
                                              'CSV (*.csv)' if kind == 'csv' else 'JSON (*.json)')
        if not path:
            return
        try:
            save_result(self.result, path, kind)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, '保存エラー', str(exc))
            return
        QMessageBox.information(self, '保存完了', f'保存しました：{path}')
