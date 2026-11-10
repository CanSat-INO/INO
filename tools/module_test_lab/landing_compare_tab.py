"""v6 PySide6 tab: evidence-based comparison of trusted C++ landing code."""
from __future__ import annotations

from pathlib import Path
from project_store import export_path
import tempfile

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox,
    QDoubleSpinBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSplitter, QPlainTextEdit, QTabWidget,
)

from cpp_landing_runner import DEMO_SOURCE
from landing_compare import compare_sources, diagnose, make_comparison_csv
from dashboard import TimePlot
from records import new_record, add_record


DEMO_V2 = DEMO_SOURCE.with_name('example_detector_v2.cpp')


class CompareWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, before, after, tolerance):
        super().__init__()
        self.before, self.after, self.tolerance = before, after, tolerance

    def run(self):
        try:
            result = compare_sources(self.before, self.after, allowed_delay_s=self.tolerance)
        except Exception as exc:
            self.failed.emit(str(exc))
        else:
            self.completed.emit(result)


class LandingCompareTab(QWidget):
    def __init__(self, on_saved=None, parent=None):
        super().__init__(parent)
        self.on_saved = on_saved
        self.comparison = None
        self.saved_run = False
        self.worker = None
        layout = QVBoxLayout(self)
        title = QLabel('着地判定コードの比較・原因分析（v6）')
        title.setStyleSheet('font-size:17px; font-weight:bold; color:#17365e;')
        layout.addWidget(title)
        note = QLabel('2つの信頼できるC++コードを、v5と同じ8条件で自動試験します。'
                      '合否・検知遅延・観測事実と原因候補を比較できます。'
                      'C++はPC上で実行します。実機保証やコードの自動修正はしません。')
        note.setWordWrap(True)
        layout.addWidget(note)

        settings = QGroupBox('比較するコードと条件')
        form = QFormLayout(settings)
        self.before_path = QLineEdit(str(DEMO_SOURCE))
        self.after_path = QLineEdit(str(DEMO_V2))
        for label, widget in [('旧コード', self.before_path),('新コード', self.after_path)]:
            widget.setReadOnly(True)
            holder = QWidget(); row=QHBoxLayout(holder); row.setContentsMargins(0,0,0,0)
            row.addWidget(widget,1)
            btn = QPushButton('参照…')
            btn.clicked.connect(lambda checked=False,w=widget:self.choose_cpp(w))
            row.addWidget(btn)
            form.addRow(label, holder)
        self.tolerance = QDoubleSpinBox()
        self.tolerance.setRange(0,600000)
        self.tolerance.setDecimals(0)
        self.tolerance.setValue(5000)
        self.tolerance.setSuffix(' ms')
        form.addRow('許容検知遅延',self.tolerance)
        self.tester=QLineEdit('TEST'); form.addRow('担当者',self.tester)
        self.version=QLineEdit('v6_cpp_comparison');form.addRow('比較版/コミット',self.version)
        layout.addWidget(settings)

        buttons=QHBoxLayout()
        self.run_btn=QPushButton('▶ 2コードを8条件で比較')
        self.run_btn.clicked.connect(self.start_comparison);buttons.addWidget(self.run_btn)
        self.export_btn=QPushButton('比較CSVを出力');self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.export_csv);buttons.addWidget(self.export_btn)
        self.save_btn=QPushButton('比較レポートを実験記録へ保存')
        self.save_btn.setEnabled(False);self.save_btn.clicked.connect(self.save_record)
        buttons.addWidget(self.save_btn)
        layout.addLayout(buttons)

        self.summary=QLabel('未実行です。まずはサンプルの旧・新コードを比較できます。')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)

        split=QSplitter(Qt.Vertical)
        self.table=QTableWidget(0,7)
        self.table.setHorizontalHeaderLabels(['試験条件','旧判定','新判定','変化',
                                             '旧検知(s)','新検知(s)','遅延差(s)'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.show_case)
        split.addWidget(self.table)

        detail_container=QWidget(); dlay=QVBoxLayout(detail_container)
        dlay.setContentsMargins(0,0,0,0)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True)
        self.detail.setMinimumHeight(130)
        dlay.addWidget(self.detail,1)
        self.plots=QTabWidget()
        self.plot_a=TimePlot();self.plot_b=TimePlot()
        self.plots.addTab(self.plot_a,'旧コードのセンサーグラフ')
        self.plots.addTab(self.plot_b,'新コードのセンサーグラフ')
        dlay.addWidget(self.plots,2)
        split.addWidget(detail_container)
        split.setSizes([230,360])
        layout.addWidget(split,1)

        self.before_path.textChanged.connect(self.invalidate)
        self.after_path.textChanged.connect(self.invalidate)
        self.tolerance.valueChanged.connect(self.invalidate)
        self.tester.textChanged.connect(self.invalidate_save)
        self.version.textChanged.connect(self.invalidate_save)
        QApplication.instance().aboutToQuit.connect(self._wait_for_worker)

    def _wait_for_worker(self):
        # Close safely; Qt must not destroy an actively running QThread.
        if self.worker is not None and self.worker.isRunning():
            self.worker.wait()

    def choose_cpp(self, field):
        path,_=QFileDialog.getOpenFileName(self,'信頼できるC++ソースを指定',
                                          str(DEMO_SOURCE.parent),'C++ (*.cpp)')
        if path: field.setText(path)

    def invalidate(self,*_):
        self.comparison=None
        self.saved_run=False
        self.table.setRowCount(0)
        self.detail.clear()
        self.plot_a.set_data({'trace': []})
        self.plot_b.set_data({'trace': []})
        self.export_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.summary.setText('設定を変更しました。再実行してください。')

    def invalidate_save(self,*_):
        if self.comparison is not None and not self.saved_run:
            self.save_btn.setEnabled(True)

    def start_comparison(self):
        if self.worker is not None and self.worker.isRunning():return
        self.invalidate()
        self.run_btn.setEnabled(False)
        self.summary.setText('比較試験を実行中です。C++をコンパイルしているため、完了まで他のタブを操作できます。')
        self.worker=CompareWorker(self.before_path.text(),self.after_path.text(),
                                  self.tolerance.value()/1000.0)
        self.worker.completed.connect(self._on_complete)
        self.worker.failed.connect(self._on_fail)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_worker_finished(self):
        self.run_btn.setEnabled(True)

    def _on_fail(self,msg):
        self.summary.setText('比較できませんでした。下のエラー詳細を確認してください。')
        self.detail.setPlainText(msg)
        QMessageBox.warning(self,'比較試験エラー',msg)

    def _on_complete(self,comparison):
        self.comparison=comparison
        self.summary.setText(comparison.summary_text())
        self.table.setRowCount(len(comparison.cases))
        for i,c in enumerate(comparison.cases):
            old=c.before.summary
            new=c.after.summary
            cells=[c.title,c.before.status,c.after.status,c.change,
                   _fmt(old.get('detected_time_s')),
                   _fmt(new.get('detected_time_s')),
                   _fmt(c.delay_delta_s, signed=True)]
            for col,value in enumerate(cells):
                item=QTableWidgetItem(value)
                if col>=4:item.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter)
                self.table.setItem(i,col,item)
        self.export_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        if comparison.cases:self.table.selectRow(0)

    def show_case(self):
        selection=self.table.selectedItems()
        if not selection or self.comparison is None:return
        i=selection[0].row()
        if i>=len(self.comparison.cases):return
        c=self.comparison.cases[i]
        a=diagnose(c.before,self.comparison.before.tolerance_s)
        b=diagnose(c.after,self.comparison.after.tolerance_s)
        self.detail.setPlainText(
            f'【試験条件】{c.title}　｜　変化：{c.change}\n'
            f'【旧コード】\n{a.as_text()}\n\n'
            f'【新コード】\n{b.as_text()}\n\n'
            '※ Z加速度のみでは実際の姿勢・接地を断定できません。'
            '各条件の正解時刻は仮想CSV中のラベルです。')
        for outcome,plot in ((c.before,self.plot_a),(c.after,self.plot_b)):
            if outcome.result is None:
                plot.set_data({'trace': []})
            else:
                row=outcome.summary
                plot.set_data({'trace':list(outcome.result.log.rows),
                               'contact_time':row.get('true_contact_s'),
                               'detected_time':row.get('detected_time_s')})

    def export_csv(self):
        if self.comparison is None:return
        filename,_=QFileDialog.getSaveFileName(self,'比較結果CSV',
                    export_path('landing_comparison_v6.csv'),'CSV (*.csv)')
        if not filename:return
        try:Path(filename).write_text('\ufeff'+make_comparison_csv(self.comparison),encoding='utf-8')
        except OSError as exc:QMessageBox.critical(self,'CSV出力失敗',str(exc))

    def save_record(self):
        if self.comparison is None or self.saved_run:return
        run=self.comparison
        ch=run.changes
        status='未判定'  # A comparison report is not a single landing pass/fail.
        try:
            with tempfile.TemporaryDirectory(prefix='cansat-v6-report-') as td:
                report=Path(td)/'landing_comparison_v6.csv'
                report.write_text('\ufeff'+make_comparison_csv(run),encoding='utf-8')
                def first_sha(batch):
                    return next((o.result.source_sha256 for o in batch.outcomes if o.result),'')
                rec=new_record(
                    module='着地検知',mode='外部シミュレーション',
                    tester=self.tester.text().strip() or '未入力',
                    scenario='v6: C++コード比較（8条件）',
                    code_version=self.version.text().strip() or 'v6_comparison',
                    status=status,
                    expected='同一の仮想条件で2コードの合否・検知遅延を比較',
                    observed=f'改善{ch["改善"]}件、悪化{ch["悪化"]}件、同判定{ch["同判定"]}件、比較対象外{ch["比較対象外"]}件',
                    notes='v6比較レポート。合否とは独立した分析記録のため未判定として保存。'
                          '仮想条件であり実機保証なし。'
                          f' 旧CPP={Path(run.before.source).name} SHA256={first_sha(run.before)}'
                          f' 新CPP={Path(run.after.source).name} SHA256={first_sha(run.after)}',
                    metrics={'improved_cases':ch['改善'],'regressed_cases':ch['悪化'],
                             'unchanged_cases':ch['同判定'],
                             'not_comparable_cases':ch['比較対象外'],
                             'before_sha256':first_sha(run.before),'after_sha256':first_sha(run.after)})
                add_record(rec,[report])
        except (OSError,ValueError) as exc:
            QMessageBox.critical(self,'比較レポート保存失敗',str(exc));return
        self.saved_run=True;self.save_btn.setEnabled(False)
        if self.on_saved:self.on_saved()
        QMessageBox.information(self,'保存完了',
                '比較レポート1件を実験記録へ保存しました。結果CSVが添付されています。'
                'GitHubへの送信は行いません。')


def _fmt(value,signed=False):
    if value is None:return '—'
    return f'{value:+.2f}' if signed else f'{value:.2f}'
