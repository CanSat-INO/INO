"""v8.2 GUI: trusted host C++ module decisions + v8.1 virtual message bus."""
from __future__ import annotations

from pathlib import Path
from project_store import export_path
import csv
import hashlib
import io

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QPlainTextEdit, QFileDialog, QMessageBox, QSplitter, QLineEdit,
    QApplication,
)
from cpp_module_bridge import run_cpp_decisions, CppModuleError
from module_network import SCENARIOS, simulate

NAMES = {
    'main_landing': 'Main：着地後の走行許可',
    'drive_move': 'Drive：走行指令の受理',
    'cam_capture': 'CAM：撮影指令の受理',
    'drive_stop': 'Drive：停止指令の受理',
}


class CppModuleTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_result = None
        self.last_source = None
        self.last_decisions = None
        self.last_sha = None
        root = QVBoxLayout(self)
        title = QLabel('C++制御ロジック × 3モジュール連携試験（v8.2）')
        title.setStyleSheet('font-size:17px;font-weight:bold;color:#17365e;')
        root.addWidget(title)
        info = QLabel('信頼できるPC用C++コードをコンパイルして判断結果を取得し、v8.1の仮想CANに反映します。'
                      ' C++拒否／通信欠落／タイムアウトを区別して表示します。'
                      ' 実機Arduinoや物理CANは実行・検証しません。')
        info.setWordWrap(True)
        root.addWidget(info)
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel('C++ソース'))
        self.source = QLineEdit(str(Path(__file__).resolve().parent /
                                    'cpp_module' / 'example_module_controller.cpp'))
        source_row.addWidget(self.source, 1)
        browse = QPushButton('参照…')
        browse.clicked.connect(self.choose_source)
        source_row.addWidget(browse)
        root.addLayout(source_row)
        row = QHBoxLayout()
        row.addWidget(QLabel('通信シナリオ'))
        self.scenario = QComboBox()
        for scenario in SCENARIOS:
            self.scenario.addItem(scenario.name, scenario.key)
        row.addWidget(self.scenario, 1)
        self.run_button = QPushButton('▶ C++連携で実行')
        self.run_button.clicked.connect(self.run_case)
        row.addWidget(self.run_button)
        self.csv_button = QPushButton('CSV出力')
        self.csv_button.setEnabled(False)
        self.csv_button.clicked.connect(self.export_csv)
        row.addWidget(self.csv_button)
        root.addLayout(row)
        self.summary = QLabel('未実行です。まず通常のサンプルC++で正常連携を試してください。')
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        self.policy_table = QTableWidget(4, 2)
        self.policy_table.setHorizontalHeaderLabels(['C++判断対象', '実行結果'])
        self.policy_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.policy_table.verticalHeader().setVisible(False)
        self.policy_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.policy_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        for i, name in enumerate(NAMES.values()):
            self.policy_table.setItem(i, 0, QTableWidgetItem(name))
        self.policy_table.setMaximumHeight(160)
        root.addWidget(self.policy_table)
        splitter = QSplitter(Qt.Vertical)
        self.event_table = QTableWidget(0, 6)
        self.event_table.setHorizontalHeaderLabels(['時刻(ms)', '送信元', '宛先', 'メッセージ', 'イベント', '詳細'])
        self.event_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.event_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.event_table.setAlternatingRowColors(True)
        self.event_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.event_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        splitter.addWidget(self.event_table)
        self.explain = QPlainTextEdit()
        self.explain.setReadOnly(True)
        self.explain.setPlaceholderText('C++判断と仮想CANの異常原因をここに表示します。')
        splitter.addWidget(self.explain)
        splitter.setSizes([400, 150])
        root.addWidget(splitter, 1)

    def choose_source(self, *_):
        selected, _ = QFileDialog.getOpenFileName(self, 'C++ファイルを選択',
                                                   self.source.text(), 'C++ (*.cpp)')
        if selected:
            self.source.setText(selected)

    def run_case(self, *_):
        self.run_button.setEnabled(False)
        QApplication.processEvents()
        try:
            outcome = run_cpp_decisions(self.source.text().strip())
            result = simulate(self.scenario.currentData(), cpp_policy=outcome.decisions)
            normal = simulate(self.scenario.currentData())
            source_hash = hashlib.sha256(Path(outcome.source).read_bytes()).hexdigest()
        except (OSError, ValueError, RuntimeError, CppModuleError) as exc:
            # Do not export stale test outcomes after failed compile/run.
            self.last_result = self.last_source = self.last_decisions = self.last_sha = None
            self.csv_button.setEnabled(False)
            QMessageBox.critical(self, 'C++試験エラー', str(exc))
            return
        finally:
            self.run_button.setEnabled(True)
        self.last_result = result
        self.last_source = outcome.source
        self.last_decisions = outcome.decisions
        self.last_sha = source_hash
        self.csv_button.setEnabled(True)
        self.summary.setText(
            f'通常モデル={normal.evaluation} ／ C++接続={result.evaluation}　'
            f'Main={result.main_state} / CAM={result.cam_state} / Drive={result.drive_state}　'
            f'C++拒否={sum(e.event == "C++拒否" for e in result.events)}件　'
            f'欠落={result.loss_count}件　タイムアウト={result.timeout_count}件')
        for i, key in enumerate(NAMES):
            self.policy_table.setItem(i, 1, QTableWidgetItem(
                '許可' if outcome.decisions[key] else '拒否'))
        self.event_table.setRowCount(len(result.events))
        for i, e in enumerate(result.events):
            for j, val in enumerate((str(e.time_ms), e.source, e.target,
                                     e.message, e.event, e.detail)):
                self.event_table.setItem(i, j, QTableWidgetItem(val))
        cpp_reject = any(e.event == 'C++拒否' for e in result.events)
        network_issue = any(e.event in ('欠落', 'タイムアウト') for e in result.events)
        causes = []
        if cpp_reject:
            causes.append('・C++判断による指令拒否が記録されています。制御条件・状態管理を確認してください。')
        if network_issue:
            causes.append('・仮想CANで欠落またはタイムアウトが記録されています。通信シナリオを確認してください。')
        if not causes:
            causes.append('・拒否や通信タイムアウトは検出されませんでした。各状態遷移を確認してください。')
        self.explain.setPlainText(
            '【検証条件】\n' + result.scenario.name + '\n'
            '【C++ソース】\n' + outcome.source + '\nSHA256: ' + source_hash + '\n'
            '【原因の切り分け】\n' + '\n'.join(causes) + '\n'
            '【モデル側の診断】\n' + '\n'.join('・'+d for d in result.diagnostics) + '\n'
            '【制限】\n仮想通信とPC実行用C++ロジックのみを評価しています。'
            '本番CAN仕様、実機のモーター停止、ESP32-S3の実行は検証していません。')

    def export_csv(self, *_):
        if self.last_result is None:
            return
        selected, _ = QFileDialog.getSaveFileName(
            self, 'C++連携通信ログCSVを保存',
            export_path(f'v8_2_cpp_can_{self.last_result.scenario.key}.csv'), 'CSV (*.csv)')
        if not selected:
            return
        output = io.StringIO(newline='')
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(['scenario', 'cpp_source', 'cpp_sha256', 'time_ms',
                         'source', 'target', 'message', 'event', 'detail'])
        for e in self.last_result.events:
            writer.writerow([self.last_result.scenario.key, self.last_source,
                             self.last_sha, e.time_ms, e.source, e.target,
                             e.message, e.event, e.detail])
        try:
            Path(selected).write_text(output.getvalue(), encoding='utf-8-sig')
        except OSError as exc:
            QMessageBox.critical(self, 'CSV保存失敗', str(exc))
            return
        QMessageBox.information(self, '保存完了', '通信ログと使用C++のSHA256を保存しました。GitHubへの送信はしていません。')
