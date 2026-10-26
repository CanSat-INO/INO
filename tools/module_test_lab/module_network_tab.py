"""v8.1 GUI for explanatory, synthetic Main/CAM/Drive message fault tests."""
from __future__ import annotations

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QPlainTextEdit, QFileDialog, QMessageBox, QSplitter,
)
from PySide6.QtCore import Qt
from module_network import SCENARIOS, simulate, make_log_csv


class ModuleNetworkTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_result = None
        root = QVBoxLayout(self)
        heading = QLabel('3モジュール・仮想CAN通信試験（v8.1）')
        heading.setStyleSheet('font-size:17px; font-weight:bold; color:#17365e;')
        root.addWidget(heading)
        info = QLabel('Main / CAM / Drive間の仮想メッセージを再現します。送信・受信・欠落・タイムアウトと状態遷移を追跡できます。'
                      ' ※本番CAN IDや実機ファームウェアは使用せず、論理レベルの仮想試験です。')
        info.setWordWrap(True)
        root.addWidget(info)
        row = QHBoxLayout()
        row.addWidget(QLabel('試験シナリオ'))
        self.scenario = QComboBox()
        for scenario in SCENARIOS:
            self.scenario.addItem(scenario.name, scenario.key)
        self.scenario.currentIndexChanged.connect(self.update_description)
        row.addWidget(self.scenario, 1)
        self.run_button = QPushButton('▶ シミュレーション実行')
        self.run_button.clicked.connect(self.run_scenario)
        row.addWidget(self.run_button)
        self.csv_button = QPushButton('通信ログをCSV出力')
        self.csv_button.setEnabled(False)
        self.csv_button.clicked.connect(self.export_csv)
        row.addWidget(self.csv_button)
        root.addLayout(row)
        self.description = QLabel('')
        self.description.setWordWrap(True)
        root.addWidget(self.description)
        self.summary = QLabel('未実行です。まず試験シナリオを選んでください。')
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        splitter = QSplitter(Qt.Vertical)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['時刻(ms)','送信元','宛先','メッセージ','イベント','内容'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(5,QHeaderView.Stretch)
        splitter.addWidget(self.table)
        self.explain = QPlainTextEdit()
        self.explain.setReadOnly(True)
        self.explain.setPlaceholderText('実行すると状態遷移・判定根拠と確認すべき点を表示します。')
        splitter.addWidget(self.explain)
        splitter.setSizes([540,180])
        root.addWidget(splitter,1)
        self.update_description()

    def update_description(self, *_):
        key = self.scenario.currentData()
        selected = next((s for s in SCENARIOS if s.key == key), None)
        self.description.setText('確認内容：' + (selected.description if selected else ''))

    def run_scenario(self, *_):
        try:
            result = simulate(self.scenario.currentData())
        except (ValueError, RuntimeError) as exc:
            QMessageBox.critical(self,'実行失敗',str(exc))
            return
        self.last_result = result
        self.csv_button.setEnabled(True)
        self.summary.setText(
            f'評価：{result.evaluation}　 Main={result.main_state} / CAM={result.cam_state} / Drive={result.drive_state}'
            f'　 欠落={result.loss_count}件 / タイムアウト={result.timeout_count}件')
        self.table.setRowCount(len(result.events))
        for i,e in enumerate(result.events):
            for j,value in enumerate((str(e.time_ms),e.source,e.target,e.message,e.event,e.detail)):
                self.table.setItem(i,j,QTableWidgetItem(value))
        self.explain.setPlainText(
            '【検証条件】\n' + result.scenario.name + '\n' + result.scenario.description +
            '\n\n【観測結果と確認すべき点】\n' + '\n'.join('・'+d for d in result.diagnostics) +
            '\n\n【注意】\nこの結果は仮想メッセージと模擬ロジックの評価です。'
            '実CAN配線・物理バスの通信品質・ESP32-S3の実行結果を保証しません。'
        )

    def export_csv(self, *_):
        if self.last_result is None:
            return
        suggested = 'v8_can_' + self.last_result.scenario.key + '.csv'
        filename,_ = QFileDialog.getSaveFileName(self,'通信ログCSVを保存',suggested,'CSV (*.csv)')
        if not filename:
            return
        try:
            Path(filename).write_text(make_log_csv(self.last_result), encoding='utf-8-sig')
        except OSError as exc:
            QMessageBox.critical(self,'CSV保存失敗',str(exc))
            return
        QMessageBox.information(self,'保存完了','通信ログCSVを保存しました。GitHubへの送信はしていません。')
