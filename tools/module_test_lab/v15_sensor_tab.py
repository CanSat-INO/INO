"""v15 offline sensor CSV viewer. No ROS/serial/Arduino/network dependency."""
from __future__ import annotations

from pathlib import Path
import math

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QHeaderView, QAbstractItemView,
)
from v15_sensor_core import SensorLog, read_sensor_csv, quality_report, stats_for, export_summary

EXAMPLES = {
    'BNO055 / IMU': 'imu_bno055_sample.csv',
    'BME280 / 気圧・温度': 'bme280_sample.csv',
    'GNSS / 緯度・経度': 'gnss_sample.csv',
    'Drive / モーター': 'drive_sample.csv',
    'CAM / 認識率': 'camera_sample.csv',
}


class SensorTimeline(QWidget):
    """Two small pure-Qt plots, each on its own numeric scale and unit."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.log: SensorLog | None = None
        self.selected: tuple[str | None, str | None] = (None, None)
        self.setMinimumSize(420, 340)

    def set_content(self, log: SensorLog | None, first: str | None, second: str | None):
        self.log = log
        self.selected = (first, second)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor('#FFFFFF'))
        if not self.log or not self.selected[0]:
            painter.setPen(QColor('#65758B'))
            painter.drawText(self.rect(), Qt.AlignCenter, 'CSVを読み込むとグラフが表示されます')
            painter.end()
            return
        outer_h = max(280, self.height() - 35)
        panel_h = outer_h / 2
        for idx, signal in enumerate(self.selected):
            box_top = 8 + idx * (panel_h + 4)
            if not signal:
                continue
            values = self.log.signals.get(signal, ())
            valid = [v for v in values if v is not None]
            painter.setPen(QColor('#17375F'))
            painter.setFont(QFont('Sans Serif', 10, QFont.Bold))
            painter.drawText(63, int(box_top + 15), f'{signal}  [{self.log.units.get(signal, "")}]')
            if not valid:
                painter.drawText(60, int(box_top + 75), '有効な測定値がありません')
                continue
            left, right = 67.0, float(max(105, self.width() - 20))
            top = box_top + 26
            bottom = box_top + panel_h - 30
            minimum, maximum = min(valid), max(valid)
            if minimum == maximum:
                margin = max(0.1, abs(maximum) * 0.06)
                minimum -= margin
                maximum += margin
            else:
                margin = (maximum - minimum) * 0.07
                minimum -= margin
                maximum += margin
            time_min, time_max = self.log.times[0], self.log.times[-1]
            if time_max <= time_min:
                time_min = min(self.log.times)
                time_max = max(self.log.times)
            if time_max <= time_min:
                time_max = time_min + 1.0
            painter.setFont(QFont('Sans Serif', 9))
            painter.setPen(QPen(QColor('#E4EAF2'), 1))
            for tick in range(4):
                y = top + (bottom - top) * tick / 3
                painter.drawLine(QPointF(left, y), QPointF(right, y))
                v = maximum - (maximum - minimum) * tick / 3
                painter.setPen(QColor('#536782'))
                painter.drawText(1, int(y + 3), f'{v:.5g}')
                painter.setPen(QPen(QColor('#E4EAF2'), 1))
            painter.setPen(QColor('#536782'))
            painter.drawText(int(left), int(bottom + 17), f'{time_min:.4g}')
            painter.drawText(int(right - 60), int(bottom + 17), f'{time_max:.4g}')
            painter.drawText(int((left + right) / 2 - 32), int(bottom + 26),
                             '時間 [s]' if self.log.time_kind != 'sample' else 'サンプル番号')

            def pos(i, value):
                x = left + (right - left) * (self.log.times[i] - time_min) / (time_max - time_min)
                y = bottom - (bottom - top) * (value - minimum) / (maximum - minimum)
                return QPointF(x, y)

            painter.setPen(QPen(QColor('#1264CE' if idx == 0 else '#087B70'), 1.8))
            # Downsample > ~2400 records while retaining per-bin maxima/minima.
            stride = max(1, math.ceil(len(values) / 1200))
            previous = None
            for start in range(0, len(values), stride):
                portion = [(j, values[j]) for j in range(start, min(start + stride, len(values)))
                           if values[j] is not None]
                if not portion:
                    previous = None
                    continue
                if stride > 1 and len(portion) > 2:
                    low = min(portion, key=lambda p: p[1])
                    high = max(portion, key=lambda p: p[1])
                    portion = sorted({low[0]: low, high[0]: high}.values())
                for index, value in portion:
                    point = pos(index, value)
                    if previous is not None:
                        painter.drawLine(previous, point)
                    previous = point
        painter.end()


class SensorCsvV15Tab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.log: SensorLog | None = None
        self.path: Path | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 10, 7, 9)
        layout.setSpacing(9)

        title = QLabel('v15 | センサー実験・CSVログ解析')
        title.setStyleSheet('font-size: 20px; font-weight: 800; color: #143766;')
        layout.addWidget(title)
        subtitle = QLabel(
            'ESP32-S3 / Arduino IDEで保存したCSVをオフライン解析。加速度・角速度・気圧・GNSS・モーター・CAMなどの数値列に対応。'
            ' この画面で実機通信・コード実行・合否判定はしません。')
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet('font-size: 12px; color: #4F6481;')
        layout.addWidget(subtitle)

        file_row = QHBoxLayout()
        self.path_field = QLineEdit()
        self.path_field.setReadOnly(True)
        self.path_field.setPlaceholderText('CSVファイルを選択してください（UTF-8 / CP932）')
        file_row.addWidget(self.path_field, 1)
        browse = QPushButton('CSVを開く…')
        browse.clicked.connect(self.choose_file)
        file_row.addWidget(browse)
        self.demo_combo = QComboBox()
        self.demo_combo.addItems(EXAMPLES)
        self.demo_combo.setToolTip('同梱の架空データを選択できます')
        file_row.addWidget(self.demo_combo)
        demo = QPushButton('サンプル読込')
        demo.clicked.connect(self.load_sample)
        file_row.addWidget(demo)
        layout.addLayout(file_row)

        toolbar = QHBoxLayout()
        self.status = QLabel('CSV未読込。まずは右上の「サンプル読込」を押してください。')
        self.status.setStyleSheet('color: #254B7B; font-weight: 700;')
        toolbar.addWidget(self.status, 1)
        self.save_button = QPushButton('解析結果をCSV / JSON保存')
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_report)
        toolbar.addWidget(self.save_button)
        layout.addLayout(toolbar)

        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(2, 2, 2, 2)

        controls = QGroupBox('表示する信号')
        form = QFormLayout(controls)
        self.first = QComboBox()
        self.second = QComboBox()
        self.first.currentIndexChanged.connect(self.update_chart)
        self.second.currentIndexChanged.connect(self.update_chart)
        form.addRow('上のグラフ', self.first)
        form.addRow('下のグラフ', self.second)
        left_layout.addWidget(controls)

        stats_title = QLabel('基本統計（元CSVの単位のまま）')
        stats_title.setStyleSheet('font-weight: 700; color: #193C70;')
        left_layout.addWidget(stats_title)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['信号', '件数', '欠損', '平均'])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        left_layout.addWidget(self.table, 2)
        left_layout.addWidget(QLabel('データ品質チェック（故障の断定ではありません）'))
        self.quality = QPlainTextEdit()
        self.quality.setReadOnly(True)
        self.quality.setPlaceholderText('時間の欠損や重複などを表示します。')
        left_layout.addWidget(self.quality, 1)
        split.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(2, 2, 2, 2)
        self.plot = SensorTimeline()
        right_layout.addWidget(self.plot, 1)
        footnote = QLabel('各グラフは独立した縦軸を使用。極値を残して間引いて描画します。'
                          ' 測定の妥当性・センサー校正・ESP32-S3実機動作は別途確認してください。')
        footnote.setWordWrap(True)
        footnote.setStyleSheet('color: #60728A; font-size: 11px;')
        right_layout.addWidget(footnote)
        split.addWidget(right)
        split.setSizes([445, 650])
        layout.addWidget(split, 1)

    def choose_file(self):
        selected, _ = QFileDialog.getOpenFileName(self, 'センサーログCSVを選択', str(Path.home()), 'CSVファイル (*.csv)')
        if selected:
            self.open_file(Path(selected))

    def load_sample(self):
        source = Path(__file__).resolve().parent / 'v15_samples' / EXAMPLES[self.demo_combo.currentText()]
        self.open_file(source)

    def open_file(self, source: Path):
        # Leave all prior results invalid on failure; never save stale reports.
        self.log = None
        self.path = None
        self.path_field.clear()
        self.save_button.setEnabled(False)
        self.table.setRowCount(0)
        self.quality.clear()
        self.plot.set_content(None, None, None)
        self.first.blockSignals(True)
        self.second.blockSignals(True)
        self.first.clear()
        self.second.clear()
        self.first.blockSignals(False)
        self.second.blockSignals(False)
        try:
            log = read_sensor_csv(source)
        except (OSError, ValueError, UnicodeError) as exc:
            self.status.setText('CSV読込失敗')
            QMessageBox.warning(self, 'センサーCSV読込エラー', str(exc))
            return
        self.log = log
        self.path = source
        self.path_field.setText(str(source))
        self.status.setText(f'{log.source_name} | {log.row_count:,}行・{len(log.signals)}信号・{log.encoding}')
        self.first.blockSignals(True)
        self.second.blockSignals(True)
        names = list(log.signals)
        self.first.addItems(names)
        self.second.addItem('（表示しない）', '')
        self.second.addItems(names)
        if len(names) > 1:
            self.second.setCurrentIndex(2)
        self.first.blockSignals(False)
        self.second.blockSignals(False)
        for stat in stats_for(log):
            i = self.table.rowCount()
            self.table.insertRow(i)
            for column, value in enumerate((stat.name + (' [' + stat.unit + ']' if stat.unit else ''),
                                            stat.count, stat.missing,
                                            f'{stat.mean:.6g}' if stat.mean is not None else '—')):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                self.table.setItem(i, column, item)
        self.quality.setPlainText('\n'.join('・' + msg for msg in quality_report(log)))
        self.save_button.setEnabled(True)
        self.update_chart()

    def update_chart(self, *_):
        if not self.log:
            return
        a = self.first.currentText() if self.first.count() else None
        b = self.second.currentData() if self.second.count() else None
        if b is None and self.second.count() > 1 and self.second.currentIndex() > 0:
            b = self.second.currentText()
        self.plot.set_content(self.log, a, b)

    def save_report(self):
        if self.log is None:
            return
        selected, selected_filter = QFileDialog.getSaveFileName(
            self, '解析レポートを保存', str(Path.home() / 'cansat_sensor_summary_v15.json'),
            'JSONレポート (*.json);;CSV基本統計 (*.csv)')
        if not selected:
            return
        out = Path(selected)
        if out.suffix.lower() not in ('.csv', '.json'):
            out = out.with_suffix('.csv' if selected_filter.startswith('CSV') else '.json')
        try:
            export_summary(self.log, out)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, '保存できませんでした', str(exc))
            return
        QMessageBox.information(self, '保存完了', f'解析結果を保存しました。\n{out}\n元CSVは変更していません。')
