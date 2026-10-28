"""v21 read-only preflight and archive integrity viewer for PySide6."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QVBoxLayout, QWidget,
)

from v21_quality_core import (
    Finding, check_bundle, check_installed_files, check_local_ledger, report_json,
)
from v20_workflow_core import inspect_csv

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path.home() / 'cansat_module_lab_data'


class QualityV21Tab(QWidget):
    """No import, overwrite, archive extraction, or changes to existing experiment data."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.findings: list[Finding] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 18)
        layout.setSpacing(12)

        title = QLabel('v21｜全体品質チェック・安定化')
        title.setStyleSheet('font-size: 22px; font-weight: 800; color: #143B74;')
        layout.addWidget(title)
        note = QLabel('点検は読み取り専用です。実験記録の削除・変更、ZIPの展開・取り込み、コード実行は行いません。'
                      '  「OK」はファイル整合性の確認であり、実機・通信・ミッションの安全性や正常動作を保証しません。')
        note.setWordWrap(True)
        layout.addWidget(note)

        group = QGroupBox('点検する対象を選ぶ')
        buttons = QHBoxLayout(group)
        for label, callback in (
            ('実験台帳・添付ファイル', self.inspect_ledger),
            ('共有ZIPを選んで点検', self.inspect_zip),
            ('インストール構成', self.inspect_install),
            ('BNO055サンプルCSV', self.inspect_sample),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addWidget(group)

        self.summary = QLabel('未点検です。まず「実験台帳・添付ファイル」を押してください。')
        self.summary.setObjectName('v13ExperimentStatus')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(('判定', '対象', '結果・確認事項'))
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 95)
        self.table.setColumnWidth(1, 140)
        layout.addWidget(self.table, 1)

        action_row = QHBoxLayout()
        self.save_button = QPushButton('点検結果をJSONに保存')
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_report)
        action_row.addWidget(self.save_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)
        foot = QLabel('参考：実験記録の保存・復元はv16、作業JSONの保存・復元はv20、CSV解析はv15で行います。'
                      '問題が検出された場合は元データを変更せず、バックアップを確認してください。')
        foot.setWordWrap(True)
        foot.setStyleSheet('color: #546783; font-size: 12px;')
        layout.addWidget(foot)

    def display(self, findings: list[Finding]):
        self.findings = findings
        self.table.setRowCount(len(findings))
        symbols = {'OK': 'OK', 'WARN': '注意', 'ERROR': '問題'}
        for row, f in enumerate(findings):
            for col, value in enumerate((symbols.get(f.level, f.level), f.area, f.message)):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if col == 0:
                    item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row, col, item)
        bad = sum(f.level == 'ERROR' for f in findings)
        warn = sum(f.level == 'WARN' for f in findings)
        good = sum(f.level == 'OK' for f in findings)
        self.summary.setText(f'点検完了：OK {good}件、注意 {warn}件、問題 {bad}件。'
                             ' 問題があってもファイルは変更していません。')
        self.save_button.setEnabled(bool(findings))

    def inspect_ledger(self):
        self.display(check_local_ledger(DATA_DIR))

    def inspect_zip(self):
        path, _ = QFileDialog.getOpenFileName(self, '読み取り専用で点検する共有ZIPを選択', '', 'ZIP (*.zip)')
        if path:
            self.display(check_bundle(path))

    def inspect_install(self):
        self.display(check_installed_files(ROOT))

    def inspect_sample(self):
        path = ROOT / 'v15_samples' / 'imu_bno055_sample.csv'
        try:
            info = inspect_csv(path)
            self.display([Finding('OK', 'サンプルCSV', f'{info.name}：{info.rows}行／{info.signals}信号／SHA256算出。')])
        except (ValueError, OSError, UnicodeError, TypeError) as exc:
            self.display([Finding('ERROR', 'サンプルCSV', f'読込に失敗しました：{exc}')])

    def save_report(self):
        if not self.findings:
            return
        path, _ = QFileDialog.getSaveFileName(self, '点検結果を保存', 'cansat_v21_quality_report.json', 'JSON (*.json)')
        if not path:
            return
        p = Path(path)
        if p.suffix.lower() != '.json':
            QMessageBox.warning(self, '保存不可', '拡張子 .json を指定してください。')
            return
        if p.is_symlink():
            QMessageBox.warning(self, '保存不可', 'シンボリックリンクには保存できません。')
            return
        try:
            from v21_quality_core import atomic_write_text
            atomic_write_text(p, report_json(self.findings))
            self.summary.setText('点検結果をJSONに保存しました。実験データは含まれていません。')
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, '保存できませんでした', str(exc))
