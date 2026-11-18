"""Optional GUI tab: batch evaluations of explicit trusted C++ landing detector."""
from __future__ import annotations

from pathlib import Path
from project_store import export_path
import tempfile

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox,
    QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSplitter, QPlainTextEdit,
    QScrollArea, QFrame,
)

from landing_batch import run_batch, make_summary_csv
from cpp_landing_runner import DEMO_SOURCE
from dashboard import TimePlot
from records import new_record, add_record


class LandingBatchTab(QWidget):
    def __init__(self, on_saved=None, parent=None):
        super().__init__(parent)
        self.on_saved = on_saved
        self.batch = None
        self.saved_run = False
        layout = QVBoxLayout(self)
        title = QLabel('着地検知の一括試験（v5）')
        title.setStyleSheet('font-size:17px; font-weight:bold; color:#17365e;')
        layout.addWidget(title)
        note = QLabel('仮想条件を8種類生成して、選択したローカルのC++判定コードを評価します。'
                      '仮想シナリオは実機の精度を保証しません。C++は実際に実行されるため、信頼できるコードのみ指定してください。')
        note.setWordWrap(True)
        layout.addWidget(note)

        controls = QGroupBox('判定コードと試験設定')
        form = QFormLayout(controls)
        source_row = QWidget(); row = QHBoxLayout(source_row); row.setContentsMargins(0,0,0,0)
        self.cpp_path = QLineEdit(str(DEMO_SOURCE)); self.cpp_path.setReadOnly(True)
        row.addWidget(self.cpp_path, 1)
        select = QPushButton('参照…'); select.clicked.connect(self.choose_cpp); row.addWidget(select)
        form.addRow('C++判定コード', source_row)
        self.tester = QLineEdit('TEST'); form.addRow('担当者', self.tester)
        self.version = QLineEdit('batch_demo_v1'); form.addRow('コード版/コミット', self.version)
        self.tolerance = QDoubleSpinBox(); self.tolerance.setRange(0,600000)
        self.tolerance.setDecimals(0); self.tolerance.setValue(5000); self.tolerance.setSuffix(' ms')
        form.addRow('検知許容遅延', self.tolerance)
        layout.addWidget(controls)

        buttons = QHBoxLayout()
        self.run_btn = QPushButton('▶ 8条件を一括実行')
        self.run_btn.clicked.connect(self.run_cases)
        buttons.addWidget(self.run_btn)
        self.export_btn = QPushButton('一覧をCSV出力'); self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.export_summary); buttons.addWidget(self.export_btn)
        self.save_btn = QPushButton('各結果を実験記録へ保存'); self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_records); buttons.addWidget(self.save_btn)
        layout.addLayout(buttons)

        self.summary = QLabel('未実行です。'); self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        split = QSplitter(Qt.Horizontal)
        table_container = QWidget(); tl = QVBoxLayout(table_container)
        tl.setContentsMargins(2,2,2,2)
        self.table = QTableWidget(0,5)
        self.table.setHorizontalHeaderLabels(['試験条件', '評価', '接地(s)', '検知(s)', '遅延(s)'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.select_case)
        tl.addWidget(self.table)
        split.addWidget(table_container)

        right = QWidget(); rl = QVBoxLayout(right); rl.setContentsMargins(2,2,2,2)
        self.detail = QPlainTextEdit(); self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(115); rl.addWidget(self.detail)
        self.plot = TimePlot(); rl.addWidget(self.plot,1)
        split.addWidget(right)
        split.setSizes([490,600])

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(split)
        layout.addWidget(scroll, 1)

        self._batch_scroll = scroll
        self._batch_splitter = split
        self._batch_narrow = None
        self._update_responsive_layout()
        self.cpp_path.textChanged.connect(self.invalidate)
        self.tolerance.valueChanged.connect(self.invalidate)
        self.tester.textChanged.connect(self.invalidate_save)
        self.version.textChanged.connect(self.invalidate_save)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_batch_splitter"):
            self._update_responsive_layout()

    def _update_responsive_layout(self):
        narrow = self.width() < 900

        if self._batch_narrow == narrow:
            return

        self._batch_narrow = narrow
        splitter = self._batch_splitter

        splitter.setOrientation(
            Qt.Vertical if narrow else Qt.Horizontal
        )

        # Narrow windows preserve space for the table and plots.
        splitter.setMinimumHeight(720 if narrow else 0)
        splitter.setSizes(
            [310, 410] if narrow else [490, 600]
        )

    def invalidate(self, *_):
        self.batch = None
        self.saved_run = False
        self.export_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.summary.setText('設定を変更しました。再実行してください。')
        self.table.setRowCount(0)
        self.plot.set_data({'trace': []})
        self.detail.clear()

    def invalidate_save(self, *_):
        if self.batch is not None and not self.saved_run:
            self.save_btn.setEnabled(True)

    def choose_cpp(self):
        src, _ = QFileDialog.getOpenFileName(self, '信頼できるC++ソースを選択',
                                             str(DEMO_SOURCE.parent), 'C++ (*.cpp)')
        if src:
            self.cpp_path.setText(src)

    def run_cases(self):
        self.invalidate()
        self.run_btn.setEnabled(False)
        try:
            batch = run_batch(self.cpp_path.text(),
                              allowed_delay_s=self.tolerance.value()/1000.0)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, '一括試験エラー', str(exc))
            return
        finally:
            self.run_btn.setEnabled(True)
        self.batch = batch
        counts = batch.counts
        self.summary.setText(f'合計{len(batch.outcomes)}条件：成功{counts["成功"]} / '
                             f'失敗{counts["失敗"]} / 未判定{counts["未判定"]} / '
                             f'入力エラー{counts["入力エラー"]} / 実行エラー{counts["実行エラー"]}。'
                             '失敗条件も検証上重要な結果です。')
        self.table.setRowCount(len(batch.outcomes))
        for i, item in enumerate(batch.outcomes):
            summary = item.summary
            columns = [item.case.title, item.status,
                       _s(summary.get('true_contact_s')),
                       _s(summary.get('detected_time_s')),
                       _s(summary.get('delay_s'))]
            for j, label in enumerate(columns):
                cell = QTableWidgetItem(label)
                if j >= 2:
                    cell.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
                self.table.setItem(i,j,cell)
        self.export_btn.setEnabled(True)
        self.save_btn.setEnabled(any(o.result for o in batch.outcomes))
        if batch.outcomes:
            self.table.selectRow(0)

    def select_case(self):
        selected = self.table.selectedItems()
        if not selected or self.batch is None:
            return
        index = selected[0].row()
        if index >= len(self.batch.outcomes):
            return
        item = self.batch.outcomes[index]
        self.detail.setPlainText(f'{item.case.title}: {item.case.description}\n'
                                 f'判定: {item.status}\n理由: {item.reason}')
        if item.result is not None:
            data = item.summary
            self.plot.set_data({'trace': list(item.result.log.rows),
                                'contact_time': data.get('true_contact_s'),
                                'detected_time': data.get('detected_time_s')})
        else:
            self.plot.set_data({'trace': []})

    def export_summary(self):
        if self.batch is None:
            return
        dest, _ = QFileDialog.getSaveFileName(self, '一括試験結果CSV',
                                              export_path('landing_batch_summary.csv'), 'CSV (*.csv)')
        if not dest:
            return
        try:
            Path(dest).write_text('\ufeff'+make_summary_csv(self.batch),encoding='utf-8')
        except OSError as exc:
            QMessageBox.critical(self,'出力エラー',str(exc))

    def save_records(self):
        if self.batch is None or self.saved_run:
            return
        completed = 0
        try:
            with tempfile.TemporaryDirectory(prefix='cansat-batch-save-') as temp:
                for item in self.batch.outcomes:
                    if item.result is None:
                        continue
                    folder = Path(temp)
                    inputs = folder/f'{item.case.key}_input.csv'
                    outputs = folder/f'{item.case.key}_cpp_output.csv'
                    inputs.write_text(item.input_csv,encoding='utf-8')
                    outputs.write_text(item.result.csv_text,encoding='utf-8')
                    summary = item.summary
                    record = new_record(
                        module='着地検知', mode='外部シミュレーション',
                        tester=self.tester.text().strip() or '未入力',
                        scenario='バッチ: '+item.case.title,
                        code_version=self.version.text().strip() or item.result.source_name,
                        status=item.status,
                        expected=f'接地から{self.batch.tolerance_s:g}秒以内に検知',
                        observed=item.reason,
                        notes='v5一括仮想試験。実機試験ではありません。'
                              f' C++={item.result.source_name} SHA256={item.result.source_sha256}',
                        metrics={**{k: summary.get(k) for k in (
                            'true_contact_s', 'detected_time_s', 'delay_s',
                            'allowed_delay_s', 'log_rows', 'extra_detection_events',
                            'starts_detected')}, 'code_sha256': item.result.source_sha256},
                    )
                    add_record(record,[outputs, inputs])
                    completed += 1
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, '保存エラー', f'{completed}件保存後にエラーが発生しました。\n{exc}')
            return
        self.saved_run = True
        self.save_btn.setEnabled(False)
        if self.on_saved:
            self.on_saved()
        QMessageBox.information(self,'保存完了',
                                f'{completed}件を実験記録へ保存しました。入力エラーの条件は除外しました。'
                                'GitHubへは自動送信されません。')


def _s(value):
    return '—' if value is None else f'{value:.2f}'
