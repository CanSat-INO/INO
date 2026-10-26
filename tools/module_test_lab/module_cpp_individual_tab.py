"""v10 PySide6 panel: choose separate trusted host C++ sources for each module."""
from __future__ import annotations
import csv
import io
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog, QMessageBox, QApplication,
    QPlainTextEdit, QSplitter,
)
from PySide6.QtCore import Qt

from module_cpp_individual import (
    ROLES, run_module, run_three_modules, IndividualCppError,
)
from module_network import SCENARIOS


class IndividualCppTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.paths = {}
        self.last_bundle = None
        self.last_modules = ()
        # The following are used by v9's results collector.
        self.last_result = None
        self.last_sha = ''
        self.last_source = ''
        self.last_notes = ''
        root = QVBoxLayout(self)
        title = QLabel('Main・CAM・Drive C++個別試験（v10）')
        title.setStyleSheet('font-size:18px; font-weight:bold; color:#17365e;')
        root.addWidget(title)
        guide = QLabel(
            '信頼できるPC向けC++ファイルをモジュール別にコンパイルし、各判断を検証します。'
            '「3モジュール一括試験」では判断結果を仮想CANに渡します。'
            'ESP32-S3/Arduinoファームウェアや実CANバスを直接実行・検証する機能ではありません。'
        )
        guide.setWordWrap(True)
        root.addWidget(guide)
        for role in ROLES:
            row = QHBoxLayout()
            row.addWidget(QLabel(f'{role} C++'))
            field = QLineEdit(str(Path(__file__).resolve().parent / 'cpp_module' /
                                  f'example_{role.lower()}_v10.cpp'))
            self.paths[role] = field
            row.addWidget(field, 1)
            browse = QPushButton('参照…')
            browse.clicked.connect(lambda checked=False, r=role: self.choose_file(r))
            row.addWidget(browse)
            root.addLayout(row)
        control = QHBoxLayout()
        control.addWidget(QLabel('試験対象'))
        self.mode = QComboBox()
        self.mode.addItem('3モジュール一括試験', 'all')
        for role in ROLES:
            self.mode.addItem(f'{role}のみ個別試験', role)
        control.addWidget(self.mode)
        control.addWidget(QLabel('通信シナリオ'))
        self.scenario = QComboBox()
        for option in SCENARIOS:
            self.scenario.addItem(option.name, option.key)
        control.addWidget(self.scenario, 1)
        self.run_button = QPushButton('▶ C++判断を試験')
        self.run_button.clicked.connect(self.run_case)
        control.addWidget(self.run_button)
        self.export_button = QPushButton('結果CSV出力')
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.save_csv)
        control.addWidget(self.export_button)
        root.addLayout(control)
        self.summary = QLabel('未実行：3モジュールそれぞれのサンプルコードから試験できます。')
        self.summary.setWordWrap(True)
        root.addWidget(self.summary)
        splitter = QSplitter(Qt.Vertical)
        self.decision_table = QTableWidget(0, 6)
        self.decision_table.setHorizontalHeaderLabels(
            ['モジュール', '判断キー', '指令番号', '着地入力', 'C++応答', '追加チェック'])
        self.decision_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.decision_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.decision_table.setAlternatingRowColors(True)
        self.decision_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        splitter.addWidget(self.decision_table)
        self.timeline = QTableWidget(0, 6)
        self.timeline.setHorizontalHeaderLabels(['時刻(ms)', '送信元', '宛先', 'メッセージ', 'イベント', '詳細'])
        self.timeline.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.timeline.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.timeline.setAlternatingRowColors(True)
        self.timeline.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.timeline.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        splitter.addWidget(self.timeline)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        splitter.addWidget(self.details)
        splitter.setSizes([180, 330, 120])
        root.addWidget(splitter, 1)

    def choose_file(self, role):
        selected, _ = QFileDialog.getOpenFileName(
            self, f'{role} C++ファイルを選択', self.paths[role].text(), 'C++ (*.cpp)')
        if selected:
            self.paths[role].setText(selected)

    def _clear_result(self):
        self.last_bundle = None
        self.last_modules = ()
        self.last_result = None
        self.last_sha = ''
        self.last_source = ''
        self.last_notes = ''
        self.export_button.setEnabled(False)
        self.decision_table.setRowCount(0)
        self.timeline.setRowCount(0)
        self.details.clear()

    def run_case(self, *_):
        self._clear_result()
        self.run_button.setEnabled(False)
        QApplication.processEvents()
        try:
            mode = self.mode.currentData()
            sources = {r: self.paths[r].text().strip() for r in ROLES}
            if mode == 'all':
                bundle = run_three_modules(sources, self.scenario.currentData())
                modules = bundle.modules
            else:
                bundle = None
                modules = (run_module(mode, sources[mode]),)
        except (OSError, ValueError, IndividualCppError, RuntimeError) as exc:
            self.summary.setText('試験エラー。前回の結果は保存対象から外しました。')
            QMessageBox.critical(self, 'C++個別試験エラー', str(exc))
            return
        finally:
            self.run_button.setEnabled(True)
        self.last_bundle = bundle
        self.last_modules = modules
        self.export_button.setEnabled(True)
        self.decision_table.setRowCount(sum(len(r.decisions) for r in modules))
        rowno = 0
        checks = []
        for run in modules:
            for d in run.decisions:
                val = {-1: '対象外(-1)', 0: '拒否(0)', 1: '許可(1)'}[d.value]
                cells = [run.role, d.key, str(d.command), str(d.landed), val, d.safety_check]
                for col, cell in enumerate(cells):
                    self.decision_table.setItem(rowno, col, QTableWidgetItem(cell))
                if d.safety_check == '要確認':
                    checks.append(f'{run.role}: {d.key} は期待値 {d.expected} に対して {d.value} です。')
                rowno += 1
        if bundle:
            self.last_result = bundle.simulation
            self.last_sha = bundle.provenance_sha256
            self.last_source = 'main_cam_drive_host_cpp'
            self.last_notes = bundle.source_notes + ('\n追加チェック: ' + ' / '.join(checks) if checks else '')
            sim = bundle.simulation
            self.summary.setText(
                f'一括試験：{sim.evaluation}　Main={sim.main_state} / CAM={sim.cam_state} / Drive={sim.drive_state}'
                f'　C++拒否={sum(e.event == "C++拒否" for e in sim.events)}件'
                f'　追加チェック={len(checks)}件')
            self.timeline.setRowCount(len(sim.events))
            for i, event in enumerate(sim.events):
                cols = [str(event.time_ms), event.source, event.target, event.message,
                        event.event, event.detail]
                for j, val in enumerate(cols):
                    self.timeline.setItem(i, j, QTableWidgetItem(val))
        else:
            self.summary.setText(f'{modules[0].role}単独試験：{len(modules[0].decisions)}件の判断を取得。'
                                 '仮想CAN連携とv9台帳への保存は3モジュール一括試験時のみ対応。'
                                 f'　追加チェック={len(checks)}件')
        self.details.setPlainText(
            '\n'.join(f'{r.role}: {Path(r.source).name}\n  SHA256={r.sha256}' for r in modules)
            + ('\n【確認事項】\n' + '\n'.join(checks) if checks else '\n【追加チェック】問題は検出されませんでした。')
            + '\n【注意】これらはPC向けC++ロジックと仮想CANの結果です。'
              '実機の動作を証明するものではありません。')

    def save_csv(self, *_):
        if not self.last_modules:
            QMessageBox.warning(self, '未実行', '先にC++試験を実行してください。')
            return
        filename, _ = QFileDialog.getSaveFileName(self, 'C++試験CSV出力',
                                                  'v10_module_cpp_decisions.csv', 'CSV (*.csv)')
        if not filename:
            return
        data = io.StringIO(newline='')
        writer = csv.writer(data, lineterminator='\n')
        writer.writerow(['record_type', 'role', 'cpp_filename', 'cpp_sha256', 'key', 'module',
                         'command', 'landed', 'decision', 'expected', 'check',
                         'scenario', 'time_ms', 'source', 'target', 'message', 'event', 'detail'])
        for run in self.last_modules:
            for d in run.decisions:
                writer.writerow(['decision',run.role,Path(run.source).name,run.sha256,
                                 d.key,d.module,d.command,d.landed,d.value,
                                 '' if d.expected is None else d.expected,d.safety_check,
                                 '', '', '', '', '', '', ''])
        if self.last_bundle:
            for event in self.last_bundle.simulation.events:
                writer.writerow(['virtual_event','','',self.last_sha,'','','','','','','',
                                 self.last_bundle.simulation.scenario.key,event.time_ms,
                                 event.source,event.target,event.message,event.event,event.detail])
        try:
            Path(filename).write_text(data.getvalue(), encoding='utf-8-sig')
        except OSError as exc:
            QMessageBox.critical(self, 'CSV保存失敗', str(exc))
            return
        QMessageBox.information(self, 'CSV出力完了',
                                'C++判断と仮想イベントを保存しました。GitHubへの自動送信は行いません。')
