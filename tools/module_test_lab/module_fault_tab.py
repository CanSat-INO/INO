"""v8.3 GUI: first observed abnormal event and subsequent virtual effects."""
from __future__ import annotations

import hashlib
from pathlib import Path
from project_store import export_path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView,
    QPlainTextEdit, QFileDialog, QMessageBox, QSplitter, QLineEdit,
    QCheckBox, QApplication,
)

from module_network import SCENARIOS, simulate
from module_fault_analysis import analyze_result, make_analysis_csv
from cpp_module_bridge import run_cpp_decisions, CppModuleError


class ModuleFaultTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result = None
        self.analysis = None
        self.cpp_source = ''
        self.cpp_sha = ''
        root = QVBoxLayout(self)
        title = QLabel('異常発生の追跡・原因分析（v8.3）')
        title.setStyleSheet('font-size:17px;font-weight:bold;color:#17365e;')
        root.addWidget(title)
        info = QLabel('仮想CANとPC用C++のイベントログから、最初に記録された異常とその後の影響を追います。'
                      ' 時刻順の関係は表示しますが、実機での因果関係を断定しません。')
        info.setWordWrap(True)
        root.addWidget(info)
        row = QHBoxLayout()
        row.addWidget(QLabel('通信シナリオ'))
        self.scenario = QComboBox()
        for item in SCENARIOS:
            self.scenario.addItem(item.name, item.key)
        row.addWidget(self.scenario, 1)
        self.run_button = QPushButton('▶ 原因を分析')
        self.run_button.clicked.connect(self.run_case)
        row.addWidget(self.run_button)
        self.csv_button = QPushButton('分析ログCSV出力')
        self.csv_button.setEnabled(False)
        self.csv_button.clicked.connect(self.export_csv)
        row.addWidget(self.csv_button)
        root.addLayout(row)
        options = QHBoxLayout()
        self.use_cpp = QCheckBox('PC用C++判断を接続する')
        self.use_cpp.setChecked(True)
        options.addWidget(self.use_cpp)
        self.source = QLineEdit(str(Path(__file__).resolve().parent /
                                    'cpp_module' / 'example_module_controller.cpp'))
        options.addWidget(self.source, 1)
        choose = QPushButton('参照…')
        choose.clicked.connect(self.choose_source)
        options.addWidget(choose)
        root.addLayout(options)
        self.use_cpp.toggled.connect(self.source.setEnabled)
        self.use_cpp.toggled.connect(choose.setEnabled)
        self.scenario_description = QLabel('')
        self.scenario_description.setWordWrap(True)
        root.addWidget(self.scenario_description)
        self.scenario.currentIndexChanged.connect(self.update_description)
        self.update_description()
        self.overview = QLabel('未実行です。例えば「Drive走行指令の欠落」を選択して分析してください。')
        self.overview.setWordWrap(True)
        root.addWidget(self.overview)
        splitter = QSplitter(Qt.Vertical)
        self.chain_table = QTableWidget(0, 5)
        self.chain_table.setHorizontalHeaderLabels(['段階', '時刻(ms)', 'モジュール', 'イベント', '説明'])
        self.chain_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.chain_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.chain_table.setAlternatingRowColors(True)
        self.chain_table.verticalHeader().setVisible(False)
        self.chain_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.chain_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        splitter.addWidget(self.chain_table)
        self.all_table = QTableWidget(0, 6)
        self.all_table.setHorizontalHeaderLabels(['時刻(ms)', '送信元', '宛先', 'メッセージ', 'イベント', '詳細'])
        self.all_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.all_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.all_table.setAlternatingRowColors(True)
        self.all_table.verticalHeader().setVisible(False)
        self.all_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.all_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        splitter.addWidget(self.all_table)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText('観測された発端と影響、確認すべきログを表示します。')
        splitter.addWidget(self.details)
        splitter.setSizes([260, 300, 170])
        root.addWidget(splitter, 1)
        self.chain_table.itemSelectionChanged.connect(self.focus_event)

    def update_description(self, *_):
        key = self.scenario.currentData()
        scenario = next((x for x in SCENARIOS if x.key == key), None)
        self.scenario_description.setText('【試験目的】' + (scenario.description if scenario else ''))

    def choose_source(self, *_):
        name, _ = QFileDialog.getOpenFileName(self, 'C++ファイルを選択',
                                              self.source.text(), 'C++ (*.cpp)')
        if name:
            self.source.setText(name)

    def run_case(self, *_):
        self.run_button.setEnabled(False)
        QApplication.processEvents()
        try:
            decisions = None
            source = sha = ''
            if self.use_cpp.isChecked():
                outcome = run_cpp_decisions(self.source.text().strip())
                source = str(outcome.source)
                sha = hashlib.sha256(Path(outcome.source).read_bytes()).hexdigest()
                decisions = outcome.decisions
            result = simulate(self.scenario.currentData(), cpp_policy=decisions)
            analysis = analyze_result(result)
        except (OSError, ValueError, RuntimeError, CppModuleError) as exc:
            self.result = self.analysis = None
            self.csv_button.setEnabled(False)
            self.chain_table.setRowCount(0)
            self.all_table.setRowCount(0)
            QMessageBox.critical(self, '分析実行エラー', str(exc))
            return
        finally:
            self.run_button.setEnabled(True)
        self.result, self.analysis = result, analysis
        self.cpp_source, self.cpp_sha = source, sha
        self.csv_button.setEnabled(True)
        self.overview.setText(
            f'評価={analysis.evaluation}　分類={analysis.classification}　'
            f'{analysis.primary_title}　{analysis.state_summary}')
        self.chain_table.setRowCount(len(analysis.steps))
        for row, step in enumerate(analysis.steps):
            e = result.events[step.event_index]
            values = (step.role, str(e.time_ms), f'{e.source} → {e.target}',
                      e.event, step.explanation)
            for col, value in enumerate(values):
                self.chain_table.setItem(row, col, QTableWidgetItem(value))
            self.chain_table.item(row, 0).setData(Qt.UserRole, step.event_index)
        self.all_table.setRowCount(len(result.events))
        for row, e in enumerate(result.events):
            values = (str(e.time_ms), e.source, e.target, e.message, e.event, e.detail)
            for col, value in enumerate(values):
                self.all_table.setItem(row, col, QTableWidgetItem(value))
        self.details.setPlainText(
            f'【試験目的】\n{result.scenario.description}\n\n'
            f'【最初の異常／判断】\n{analysis.primary_title}\n'
            f'{analysis.primary_explanation}\n\n'
            f'【最終状態】\n{analysis.state_summary}\n\n'
            '【確認ポイント】\n・「発端」の行を選ぶと元ログの該当イベントに移動します。\n'
            '・異常が発生した条件と、後から生じたタイムアウトを区別してください。\n'
            '・C++拒否があればソースの許可条件、欠落があれば仮想通信条件を確認します。\n\n'
            f'【C++ファイル】\n{source or "未使用"}\n'
            f'{"SHA256: " + sha if sha else ""}\n\n'
            f'【検証範囲】\n{analysis.caution}')
        if analysis.steps:
            self.chain_table.selectRow(0)

    def focus_event(self):
        if self.result is None:
            return
        row = self.chain_table.currentRow()
        if row < 0:
            return
        item = self.chain_table.item(row, 0)
        if item is None:
            return
        idx = item.data(Qt.UserRole)
        if type(idx) is int and 0 <= idx < len(self.result.events):
            self.all_table.selectRow(idx)
            self.all_table.scrollToItem(self.all_table.item(idx, 0))

    def export_csv(self, *_):
        if self.result is None or self.analysis is None:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, '異常分析ログを保存',
            export_path(f'v8_3_fault_{self.result.scenario.key}.csv'), 'CSV (*.csv)')
        if not filename:
            return
        data = make_analysis_csv(self.result, self.analysis,
                                 cpp_source=self.cpp_source, cpp_sha256=self.cpp_sha)
        try:
            Path(filename).write_text(data, encoding='utf-8-sig')
        except OSError as exc:
            QMessageBox.critical(self, 'CSV保存失敗', str(exc))
            return
        QMessageBox.information(self, '保存完了', '時系列ログと分析結果をCSVに保存しました。GitHubへの送信はしていません。')
