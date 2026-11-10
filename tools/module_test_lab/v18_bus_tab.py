"""v18 offline virtual message-bus simulation UI (no hardware access)."""
from __future__ import annotations

from pathlib import Path
from project_store import export_path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QPushButton, QComboBox, QDoubleSpinBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QFileDialog, QMessageBox,
    QAbstractItemView, QHeaderView,
)
from v18_bus_core import SCENARIOS, BusConfig, run_bus_test, csv_text, json_text, scenario_signature


class VirtualBusV18Tab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(14, 10, 14, 16)
        root.setSpacing(10)

        h = QLabel('v18｜Main・CAM・Drive 仮想メッセージ連携試験')
        h.setStyleSheet('font-size: 20px; color: #143B6D; font-weight: bold;')
        root.addWidget(h)
        desc = QLabel(
            'オフラインの仮想送受信で、指令・ACK・CAM検出通知・重複・欠損・遅延を検証します。'
            '実際のCAN/TWELITE通信、ESP32-S3のコード、地上局、モーター、ROS 2/Gazeboとは接続しません。'
            'これは通信仕様を考えるための簡略モデルです。')
        desc.setWordWrap(True)
        root.addWidget(desc)

        how = QGroupBox('仮想プロトコル（予定仕様の例）')
        hl = QVBoxLayout(how)
        flow = QLabel('Main ──走行指令──▶ Drive  ／  Drive ──ACK──▶ Main  ／  CAM ──検出・異常通知──▶ Main')
        flow.setWordWrap(True)
        flow.setStyleSheet('color: #173C69; font-weight: bold;')
        hl.addWidget(flow)
        help_label = QLabel('実機側の通信形式・ID・再送方針は未確定です。この仮想プロトコルはチームの実機仕様ではありません。')
        help_label.setWordWrap(True)
        hl.addWidget(help_label)
        root.addWidget(how)

        opts = QHBoxLayout()
        opts.addWidget(QLabel('試験ケース'))
        self.scenario = QComboBox()
        for key, label in SCENARIOS.items():
            self.scenario.addItem(label, key)
        self.scenario.currentIndexChanged.connect(self.clear_results)
        opts.addWidget(self.scenario, 1)
        root.addLayout(opts)

        group = QGroupBox('仮想ネットワーク条件（実機の校正値ではありません）')
        form = QFormLayout(group)
        self.fields = {}
        for key, label, low, high, initial in (
            ('latency_s', '片道遅延 [s]', 0.01, 1.5, .1),
            ('ack_timeout_s', 'Drive応答待機期限 [s]', .1, 5.0, .8),
            ('target_deadline_s', 'CAM検出通知の期限 [s]', 16.5, 20.0, 17.5),
            ('max_age_s', '受信データの有効期間 [s]', .1, 10.0, 1.0),
        ):
            field = QDoubleSpinBox()
            field.setDecimals(2)
            field.setSingleStep(.1)
            field.setRange(low, high)
            field.setValue(initial)
            field.valueChanged.connect(self.clear_results)
            form.addRow(label, field)
            self.fields[key] = field
        root.addWidget(group)

        buttons = QHBoxLayout()
        self.run_btn = QPushButton('▶ 仮想通信を試験')
        self.run_btn.clicked.connect(self.run)
        self.csv_btn = QPushButton('送受信ログCSV保存')
        self.csv_btn.clicked.connect(self.export_csv)
        self.json_btn = QPushButton('条件・結果JSON保存')
        self.json_btn.clicked.connect(self.export_json)
        self.csv_btn.setEnabled(False)
        self.json_btn.setEnabled(False)
        for btn in (self.run_btn, self.csv_btn, self.json_btn):
            buttons.addWidget(btn)
        buttons.addStretch()
        root.addLayout(buttons)

        self.status = QLabel('未実行：シナリオを選んで試験してください。')
        self.status.setObjectName('v13ExperimentStatus')
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.detail = QLabel('受信数 0 ／ 欠損数 0 ／ 重複除外 0 ／ 未確認ACK 0')
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet('font-weight: 650; color: #31537B;')
        root.addWidget(self.detail)
        root.addWidget(QLabel('メッセージの送信・受信・失敗イベント（シミュレーションログ）'))
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['時刻[s]', '送信元', '宛先', '種類', 'SEQ', '状態', '内容'])
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        for i, width in enumerate((75, 87, 87, 125, 65, 92)):
            self.table.setColumnWidth(i, width)
        self.table.setMinimumHeight(390)
        root.addWidget(self.table)
        note = QLabel('※ PASSは仮想通信の確認条件の成立を意味します。停止要求も実機の停止動作の保証ではありません。')
        note.setWordWrap(True)
        note.setStyleSheet('color: #6A5260;')
        root.addWidget(note)

    def clear_results(self, *args):
        self.result = None
        self.table.setRowCount(0)
        self.status.setText('設定変更あり：仮想通信を再実行してください。')
        self.detail.setText('受信数 0 ／ 欠損数 0 ／ 重複除外 0 ／ 未確認ACK 0')
        self.csv_btn.setEnabled(False)
        self.json_btn.setEnabled(False)

    def run(self):
        try:
            config = BusConfig(**{k: w.value() for k, w in self.fields.items()})
            result = run_bus_test(self.scenario.currentData(), config)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, '設定エラー', str(exc))
            return
        self.result = result
        self.status.setText(
            f'仮想通信 {result.status} | {result.final_time_s:g}秒 | {result.reason}  ※実機検証ではありません。')
        self.detail.setText(
            f'受信数 {result.delivered} ／ 欠損数 {result.dropped} ／ '
            f'重複除外 {result.duplicates} ／ 未確認ACK {result.pending_ack}  '
            f'| 記録SHA256: {scenario_signature(result)[:16]}…')
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(len(result.events))
            for i, row in enumerate(result.events):
                for col, key in enumerate(('time_s', 'src', 'dst', 'kind', 'seq', 'state', 'detail')):
                    item = QTableWidgetItem(str(row[key]))
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.table.setItem(i, col, item)
        finally:
            self.table.setUpdatesEnabled(True)
        self.csv_btn.setEnabled(True)
        self.json_btn.setEnabled(True)

    def _save(self, data, suffix, filter_name):
        if self.result is None:
            return
        name = f'v18_{self.result.scenario}.{suffix}'
        output, _ = QFileDialog.getSaveFileName(self, '仮想試験ログを保存', export_path(name), filter_name)
        if not output:
            return
        try:
            Path(output).write_text(data, encoding='utf-8-sig' if suffix == 'csv' else 'utf-8')
        except OSError as exc:
            QMessageBox.warning(self, '保存失敗', str(exc))
            return
        self.status.setText(f'保存完了: {output}  ※シミュレーションのログです。')

    def export_csv(self):
        if self.result is not None:
            self._save(csv_text(self.result), 'csv', 'CSV (*.csv)')

    def export_json(self):
        if self.result is not None:
            self._save(json_text(self.result), 'json', 'JSON (*.json)')
