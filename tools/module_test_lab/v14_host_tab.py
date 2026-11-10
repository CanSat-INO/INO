"""v14 host-portable C++ verification panel; completely separate from device IO."""
from __future__ import annotations

from pathlib import Path
from project_store import export_path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QCheckBox, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QPlainTextEdit, QMessageBox, QSplitter, QApplication,
)

from v14_host_runner import (
    EXAMPLE, DEFAULT_CASES, HostValidationError, run_host_suite, export_report,
)


class HostWorker(QThread):
    success = Signal(object)
    failure = Signal(str)

    def __init__(self, source, cases, parent=None):
        super().__init__(parent)
        self.source = source
        self.cases = cases

    def run(self):
        try:
            self.success.emit(run_host_suite(self.source, self.cases))
        except Exception as exc:
            self.failure.emit(str(exc))


class HostCppV14Tab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.last_run = None
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self._wait_for_worker_on_exit)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        heading = QLabel('v14 | Arduino共有ロジック・C++ホスト検証')
        heading.setStyleSheet('font-size: 20px; font-weight: 800; color: #123766;')
        lay.addWidget(heading)
        warning = QLabel(
            'ESP32-S3の.ino全体をPCで実行する機能ではありません。'
            'Arduino依存部分を除いた共有C++判断ロジックをアダプター経由で検証します。'
            'コンパイルしたコードはPC上で実行され、隔離されません。信頼できるソースだけ選んでください。'
        )
        warning.setWordWrap(True)
        lay.addWidget(warning)

        source_row = QHBoxLayout()
        source_row.addWidget(QLabel('C++アダプター'))
        self.source = QLineEdit(str(EXAMPLE))
        self.source.setToolTip('cansat_allow_command(module, command, landed) を定義した信頼できる .cpp')
        source_row.addWidget(self.source, 1)
        choose_src = QPushButton('参照…')
        choose_src.clicked.connect(self.choose_source)
        source_row.addWidget(choose_src)
        lay.addLayout(source_row)

        case_row = QHBoxLayout()
        case_row.addWidget(QLabel('試験ケースCSV'))
        self.case_csv = QLineEdit(str(DEFAULT_CASES))
        case_row.addWidget(self.case_csv, 1)
        choose_csv = QPushButton('参照…')
        choose_csv.clicked.connect(self.choose_csv)
        case_row.addWidget(choose_csv)
        lay.addLayout(case_row)

        bar = QHBoxLayout()
        self.trusted = QCheckBox('選択したC++ソースを信頼し、PC上でコンパイル・実行することを理解しました')
        self.trusted.toggled.connect(self._update_button)
        bar.addWidget(self.trusted, 1)
        self.run_button = QPushButton('▶ ホスト試験を実行')
        self.run_button.setEnabled(False)
        self.run_button.clicked.connect(self.start_run)
        bar.addWidget(self.run_button)
        self.save_button = QPushButton('結果をCSV/JSON保存')
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self.save_report)
        bar.addWidget(self.save_button)
        lay.addLayout(bar)

        self.summary = QLabel('未実行：同梱のデモコードとサンプルCSVで操作を確認できます。')
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet('color: #1C4B7D; font-weight: 700;')
        lay.addWidget(self.summary)
        split = QSplitter(Qt.Vertical)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(('ケース名', 'モジュール', '指令', '着地', '期待値', '実際値', '判定'))
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        split.addWidget(self.table)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        split.addWidget(self.detail)
        split.setSizes((450, 145))
        lay.addWidget(split, 1)

    def _wait_for_worker_on_exit(self):
        # Native C++ is bounded by compile/run timeouts. Avoid deleting QThread
        # while an active compile/test is still running as the app closes.
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait(35_000)

    def choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, '信頼できるホスト用C++アダプター',
                                             self.source.text(), 'C++ (*.cpp)')
        if path:
            self.source.setText(path)

    def choose_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, 'テストCSV',
                                             self.case_csv.text(), 'CSV (*.csv)')
        if path:
            self.case_csv.setText(path)

    def _update_button(self):
        self.run_button.setEnabled(self.trusted.isChecked() and self.worker is None)

    def start_run(self):
        if self.worker is not None or not self.trusted.isChecked():
            return
        self.last_run = None
        self.save_button.setEnabled(False)
        self.table.setRowCount(0)
        self.detail.clear()
        self.summary.setText('g++でホストコードをコンパイル・検証しています…')
        self.worker = HostWorker(self.source.text().strip(), self.case_csv.text().strip(), self)
        self.worker.success.connect(self._complete)
        self.worker.failure.connect(self._failed)
        self.worker.finished.connect(self._finish_worker)
        self._update_button()
        self.worker.start()

    def _complete(self, result):
        self.last_run = result
        self.save_button.setEnabled(True)
        self.summary.setText(f'ホスト検証 {result.status}: {result.passed}/{len(result.results)}件適合'
                             f'　実行時間 {result.elapsed_seconds:.2f}秒  ※実機保証ではありません')
        self.table.setRowCount(len(result.results))
        for i, item in enumerate(result.results):
            c = item.case
            values = (c.case_id, {1: 'Main', 2: 'CAM', 3: 'Drive'}[c.module],
                      str(c.command), str(c.landed), str(c.expected), str(item.actual),
                      'PASS' if item.passed else 'FAIL')
            for col, value in enumerate(values):
                self.table.setItem(i, col, QTableWidgetItem(value))
        dep_names = '\n'.join(f'  {name}  SHA256={digest}' for name, digest in result.dependencies)
        self.detail.setPlainText(
            '【PC上のロジック試験のみ】Arduino/ESP32実機・GPIO・CANの検証ではありません。\n'
            f'ソース: {result.source}\nソースSHA256: {result.source_sha256}\n'
            f'ケースSHA256: {result.cases_sha256}\n'
            f'依存ファイル込み識別子: {result.manifest_sha256}\n'
            f'依存ファイル:\n{dep_names}\n'
            f'コンパイラ出力:\n{result.compile_log or "（なし）"}')

    def _failed(self, message):
        self.summary.setText('試験失敗：結果は保存対象から外しました。')
        self.detail.setPlainText(message)
        QMessageBox.warning(self, 'v14 C++ホスト試験エラー', message[:4000])

    def _finish_worker(self):
        old = self.worker
        self.worker = None
        self._update_button()
        if old is not None:
            old.deleteLater()

    def save_report(self):
        if self.last_run is None:
            return
        chosen, selected_filter = QFileDialog.getSaveFileName(
            self, '検証結果を保存', export_path('cansat_v14_host_report.csv'),
            'CSV (*.csv);;JSON (*.json)')
        if not chosen:
            return
        path = Path(chosen)
        if not path.suffix:
            path = path.with_suffix('.json' if 'JSON' in selected_filter else '.csv')
        try:
            saved = export_report(self.last_run, path)
        except (OSError, HostValidationError) as exc:
            QMessageBox.warning(self, '出力失敗', str(exc))
            return
        QMessageBox.information(self, '保存完了',
                                f'{saved} に保存しました。アップロードや実験台帳登録は行っていません。')
