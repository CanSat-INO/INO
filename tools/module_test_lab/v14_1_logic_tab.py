"""v14.1 portable module-specific host logic GUI, independent from hardware."""
from __future__ import annotations

from pathlib import Path
from project_store import export_path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QLineEdit, QCheckBox, QPushButton, QFileDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QMessageBox,
    QSplitter, QPlainTextEdit,
)

from v14_1_logic_runner import (
    SPECS, examples_for, run_module_suite, export_module_report,
    ModuleValidationError,
)


class ModuleWorker(QThread):
    success = Signal(object)
    failure = Signal(str)

    def __init__(self, module: str, source: str, csv_path: str, parent=None):
        super().__init__(parent)
        self.module = module
        self.source = source
        self.csv_path = csv_path

    def run(self):
        try:
            self.success.emit(run_module_suite(self.module, self.source, self.csv_path))
        except Exception as exc:
            self.failure.emit(str(exc))


class PortableModulesTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.last_report = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)
        heading = QLabel('v14.1 | モジュール別 C++ 判断ロジック検証')
        heading.setStyleSheet('font-size: 20px; font-weight: 800; color: #123766;')
        lay.addWidget(heading)
        note = QLabel('チームの実コードからArduino非依存の判断処理を取り出してPCで試験します。'
                      ' 下記のサンプルは動作確認用であり、実機・画像処理・GNSS測位・駆動回路の正しさは検証できません。'
                      ' 信頼できるソースだけコンパイル・実行してください（隔離実行ではありません）。')
        note.setWordWrap(True)
        lay.addWidget(note)

        row = QHBoxLayout()
        row.addWidget(QLabel('対象モジュール'))
        self.module = QComboBox()
        for key, spec in SPECS.items():
            self.module.addItem(spec.title, key)
        row.addWidget(self.module, 1)
        self.demo_button = QPushButton('サンプルを選択')
        self.demo_button.setToolTip('入力欄のパスを同梱サンプルに戻します。実コードやCSVは削除しません。')
        self.demo_button.clicked.connect(self.select_examples)
        row.addWidget(self.demo_button)
        lay.addLayout(row)

        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setStyleSheet('color: #29547E;')
        lay.addWidget(self.description)
        for label, attr, caption, filter_text in (
            ('C++アダプター', 'source', '信頼できるC++アダプター', 'C++ (*.cpp)'),
            ('試験ケースCSV', 'csv_path', '試験ケース', 'CSV (*.csv)'),
        ):
            line = QHBoxLayout()
            line.addWidget(QLabel(label))
            entry = QLineEdit()
            setattr(self, attr, entry)
            line.addWidget(entry, 1)
            choose = QPushButton('参照…')
            choose.clicked.connect(lambda checked=False, edit=entry, title=caption, flt=filter_text:
                                   self.choose_file(edit, title, flt))
            line.addWidget(choose)
            lay.addLayout(line)

        commands = QHBoxLayout()
        self.trusted = QCheckBox('選択したC++を信頼し、PCでコンパイル・実行することを理解しました')
        self.trusted.toggled.connect(self.update_buttons)
        commands.addWidget(self.trusted, 1)
        self.run_button = QPushButton('▶ モジュール試験を実行')
        self.run_button.clicked.connect(self.start_test)
        commands.addWidget(self.run_button)
        self.save_button = QPushButton('結果をCSV/JSON保存')
        self.save_button.clicked.connect(self.save_report)
        commands.addWidget(self.save_button)
        lay.addLayout(commands)

        self.summary = QLabel('未実行：モジュールを選び、サンプルで動作を確認してください。')
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet('color: #245083; font-weight: 700;')
        lay.addWidget(self.summary)
        split = QSplitter(Qt.Vertical)
        self.table = QTableWidget(0, 1)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        split.addWidget(self.table)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        split.addWidget(self.details)
        split.setSizes((410, 160))
        lay.addWidget(split, 1)

        self.source.textChanged.connect(self.invalidate_report)
        self.csv_path.textChanged.connect(self.invalidate_report)
        self.module.currentIndexChanged.connect(self.on_module_changed)
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.wait_for_worker)
        self.on_module_changed()
        self.update_buttons()

    def wait_for_worker(self):
        if self.worker and self.worker.isRunning():
            self.worker.wait(90_000)

    def on_module_changed(self, *_):
        key = self.module.currentData()
        spec = SPECS[key]
        self.description.setText(spec.description + '　|　判定値: ' + spec.output_meanings)
        self.select_examples()
        self.invalidate_report()
        self.details.clear()
        self.summary.setText('未実行：'+spec.title+'のサンプルを実行できます。')

    def select_examples(self):
        source, csv_path = examples_for(self.module.currentData())
        self.source.setText(str(source))
        self.csv_path.setText(str(csv_path))
        self.invalidate_report()

    def choose_file(self, entry: QLineEdit, title: str, file_filter: str):
        path, _ = QFileDialog.getOpenFileName(self, title, entry.text(), file_filter)
        if path:
            entry.setText(path)
            self.invalidate_report()

    def invalidate_report(self, *_):
        self.last_report = None
        self.save_button.setEnabled(False)
        self.table.setRowCount(0)

    def update_buttons(self, *_):
        self.run_button.setEnabled(self.trusted.isChecked() and self.worker is None)

    def start_test(self):
        if self.worker or not self.trusted.isChecked():
            return
        self.invalidate_report()
        self.details.clear()
        self.summary.setText('ホストC++をコンパイルして試験中…')
        self.module.setEnabled(False)
        self.source.setEnabled(False)
        self.csv_path.setEnabled(False)
        self.demo_button.setEnabled(False)
        self.worker = ModuleWorker(self.module.currentData(), self.source.text().strip(),
                                   self.csv_path.text().strip(), self)
        self.worker.success.connect(self.on_success)
        self.worker.failure.connect(self.on_failure)
        self.worker.finished.connect(self.on_finished)
        self.update_buttons()
        self.worker.start()

    def on_success(self, report):
        self.last_report = report
        self.summary.setText(f'{SPECS[report.module].title} {report.status}: {report.passed}/{len(report.results)}件適合'
                             f'　実行 {report.elapsed_seconds:.2f}秒  ※実機保証ではありません')
        spec = SPECS[report.module]
        columns = ['ケース名', *(f.label for f in spec.fields), '期待値', '実際値', '判定']
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(report.results))
        for i, result in enumerate(report.results):
            values = (result.case.case_id, *result.case.arguments,
                      str(result.case.expected), str(result.actual),
                      'PASS' if result.passed else 'FAIL')
            for c, val in enumerate(values):
                self.table.setItem(i, c, QTableWidgetItem(str(val)))
        self.details.setPlainText('【ホスト判断ロジックのみ】.inoのビルドやESP32-S3の実機試験ではありません。\n'
                                  f'アダプター: {report.source}\nCSV: {report.cases_csv}\n'
                                  f'コードSHA256: {report.source_sha256}\n'
                                  f'CSV SHA256: {report.csv_sha256}\n'
                                  f'依存物込みSHA256: {report.manifest_sha256}\n'
                                  '依存ファイル:\n' + '\n'.join('  '+name+' '+digest for name, digest in report.dependencies)
                                  + '\nコンパイルログ:\n' + (report.compile_log or '（なし）'))
        self.save_button.setEnabled(True)

    def on_failure(self, reason):
        self.summary.setText('試験失敗：保存できる結果はありません。')
        self.details.setPlainText(reason)
        QMessageBox.warning(self, 'v14.1 ホスト検証エラー', reason[:3000])

    def on_finished(self):
        done = self.worker
        self.worker = None
        self.module.setEnabled(True)
        self.source.setEnabled(True)
        self.csv_path.setEnabled(True)
        self.demo_button.setEnabled(True)
        self.update_buttons()
        if done is not None:
            done.deleteLater()

    def save_report(self):
        if self.last_report is None:
            return
        name, file_type = QFileDialog.getSaveFileName(self, '試験結果を保存',
                                                     export_path(f'cansat_{self.last_report.module}_v14_1.csv'),
                                                     'CSV (*.csv);;JSON (*.json)')
        if not name:
            return
        target = Path(name)
        if not target.suffix:
            target = target.with_suffix('.json' if 'JSON' in file_type else '.csv')
        try:
            saved = export_module_report(self.last_report, target)
        except (ModuleValidationError, OSError) as exc:
            QMessageBox.warning(self, '保存失敗', str(exc))
            return
        QMessageBox.information(self, '保存完了', f'{saved} に保存しました。実験台帳登録・クラウド送信は行いません。')
