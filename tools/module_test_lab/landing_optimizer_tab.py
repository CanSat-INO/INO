"""v7 PySide6 tab: finite grid search with explainable outcomes."""
from __future__ import annotations

from pathlib import Path
from project_store import export_path
import tempfile

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QPushButton, QLineEdit, QFileDialog, QMessageBox, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QSplitter, QPlainTextEdit,
)

from dashboard import TimePlot
from landing_optimizer import (DEMO_TUNABLE, optimize, parse_values,
                               make_optimization_csv, make_optimization_cases_csv)
from landing_compare import diagnose
from records import new_record,add_record


def _show(value):
    return '—' if value is None else f'{value:.2f}'


class OptimizeWorker(QThread):
    completed=Signal(object)
    failed=Signal(str)
    progress_signal=Signal(int,int)
    def __init__(self,source,thresholds,holds,tolerance):
        super().__init__()
        self.source,self.thresholds,self.holds,self.tolerance=source,thresholds,holds,tolerance
    def run(self):
        try:
            report=optimize(self.source,self.thresholds,self.holds,
                            allowed_delay_s=self.tolerance,
                            progress=lambda done,total:self.progress_signal.emit(done,total))
        except Exception as exc:self.failed.emit(str(exc))
        else:self.completed.emit(report)


class LandingOptimizerTab(QWidget):
    def __init__(self,on_saved=None,parent=None):
        super().__init__(parent)
        self.on_saved=on_saved
        self.result=None;self.worker=None;self.saved=False
        layout=QVBoxLayout(self)
        title=QLabel('着地判定パラメータの一括探索・評価（v7）')
        title.setStyleSheet('font-size:17px; font-weight:bold; color:#17365e;')
        layout.addWidget(title)
        msg=QLabel('加速度閾値と静止継続時間を変え、v5の8条件で同じC++を自動比較します。'
                   'v7専用の landing_configure() に対応したC++のみ使用できます。'
                   '良い設定は仮想データに対する候補で、実機の最適値・安全性を意味しません。')
        msg.setWordWrap(True);layout.addWidget(msg)
        setting=QGroupBox('コード・探索パラメータ（カンマ区切り、最大16組）')
        form=QFormLayout(setting)
        self.source=QLineEdit(str(DEMO_TUNABLE));self.source.setReadOnly(True)
        sr=QHBoxLayout();sr.addWidget(self.source,1)
        browse=QPushButton('参照…');browse.clicked.connect(self.pick_cpp);sr.addWidget(browse)
        form.addRow('パラメータ対応C++',sr)
        self.thresholds=QLineEdit('12, 14, 18')
        form.addRow('加速度閾値 (m/s²)',self.thresholds)
        self.holds=QLineEdit('0, 300, 700')
        form.addRow('静止判定時間 (ms)',self.holds)
        self.tolerance=QDoubleSpinBox();self.tolerance.setRange(0,600)
        self.tolerance.setDecimals(2);self.tolerance.setValue(5.0)
        self.tolerance.setSuffix(' s')
        form.addRow('許容検知遅延',self.tolerance)
        self.tester=QLineEdit('TEST');form.addRow('担当者',self.tester)
        self.version=QLineEdit('v7_parameter_grid');form.addRow('コード版/コミット',self.version)
        layout.addWidget(setting)

        btns=QHBoxLayout()
        self.run_btn=QPushButton('▶ パラメータ組を一括試験')
        self.run_btn.clicked.connect(self.start);btns.addWidget(self.run_btn)
        self.csv_btn=QPushButton('結果CSVを出力');self.csv_btn.setEnabled(False)
        self.csv_btn.clicked.connect(self.export_csv);btns.addWidget(self.csv_btn)
        self.save_btn=QPushButton('レポートを実験記録へ保存');self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_record);btns.addWidget(self.save_btn)
        layout.addLayout(btns)
        self.summary=QLabel('未実行です。サンプルC++と3×3条件で試験できます。')
        self.summary.setWordWrap(True);layout.addWidget(self.summary)
        split=QSplitter(Qt.Vertical)
        self.table=QTableWidget(0,7)
        self.table.setHorizontalHeaderLabels(['順位','閾値 (m/s²)','静止 (ms)','成功','失敗','早期誤検知','成功時の平均遅延 (s)'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.show_candidate)
        split.addWidget(self.table)
        lower=QWidget(); ll=QVBoxLayout(lower);ll.setContentsMargins(0,0,0,0)
        self.cases=QTableWidget(0,4)
        self.cases.setHorizontalHeaderLabels(['試験条件','判定','検知 (s)','遅延 (s)'])
        self.cases.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.cases.setSelectionMode(QAbstractItemView.SingleSelection)
        self.cases.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cases.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.cases.itemSelectionChanged.connect(self.show_case)
        ll.addWidget(self.cases,2)
        self.detail=QPlainTextEdit();self.detail.setReadOnly(True);self.detail.setMinimumHeight(100)
        ll.addWidget(self.detail,2)
        self.plot=TimePlot();self.plot.setMinimumHeight(160)
        ll.addWidget(self.plot,3)
        split.addWidget(lower);split.setSizes([180,440])
        layout.addWidget(split,1)
        for field in (self.source,self.thresholds,self.holds):field.textChanged.connect(self.invalidate)
        self.tolerance.valueChanged.connect(self.invalidate)
        QApplication.instance().aboutToQuit.connect(self._shutdown)

    def _shutdown(self):
        if self.worker and self.worker.isRunning():self.worker.wait()

    def pick_cpp(self):
        filename,_=QFileDialog.getOpenFileName(self,'信頼できるC++コードを選択',
                                               str(DEMO_TUNABLE.parent),'C++ (*.cpp)')
        if filename:self.source.setText(filename)

    def invalidate(self,*_):
        self.result=None;self.saved=False
        self.table.setRowCount(0);self.cases.setRowCount(0)
        self.detail.clear();self.plot.set_data({'trace':[]})
        self.csv_btn.setEnabled(False);self.save_btn.setEnabled(False)
        self.summary.setText('設定を変更しました。再実行してください。')

    def start(self):
        if self.worker and self.worker.isRunning():return
        try:
            threshold=parse_values(self.thresholds.text(),name='加速度閾値',minimum=1,maximum=100)
            holds=parse_values(self.holds.text(),name='静止判定時間',minimum=0,maximum=5000)
            if len(threshold)*len(holds)>16:
                raise ValueError('組み合わせは最大16通りです。')
        except ValueError as exc:
            QMessageBox.warning(self,'パラメータ入力エラー',str(exc));return
        self.invalidate()
        self.run_btn.setEnabled(False)
        self.summary.setText('C++を1回コンパイルし、各条件で判定しています。')
        self.worker=OptimizeWorker(self.source.text(),threshold,holds,self.tolerance.value())
        self.worker.progress_signal.connect(lambda n,total:self.summary.setText(f'パラメータ試験中：{n}/{total}組'))
        self.worker.completed.connect(self._complete)
        self.worker.failed.connect(self._failed)
        self.worker.finished.connect(lambda:self.run_btn.setEnabled(True))
        self.worker.start()

    def _failed(self,error):
        self.summary.setText('試験を実行できませんでした。C++のAPI対応を確認してください。')
        self.detail.setPlainText(error)
        QMessageBox.warning(self,'試験エラー',error)

    def _complete(self,result):
        self.result=result;self.saved=False
        best=result.best
        if best:
            self.summary.setText(f'{len(result.candidates)}組を評価。推奨候補: 閾値{best.threshold:g} m/s²、'
                                 f'静止時間{best.hold_ms:g} ms、成功{best.counts["成功"]}件、'
                                 f'早期誤検知{best.false_early}件、平均遅延{_show(best.mean_delay_s)}秒。'
                                 '順位は成功数→早期誤検知→成功時平均遅延の順です。仮想条件限定。')
        else:
            self.summary.setText('評価できる組み合わせがありません。各行の実行エラーを確認してください。')
        self.table.setRowCount(len(result.ranked))
        for row,c in enumerate(result.ranked):
            fields=[str(row+1),f'{c.threshold:g}',f'{c.hold_ms:g}',str(c.counts['成功']),
                    str(c.counts['失敗']),str(c.false_early),_show(c.mean_delay_s)]
            for col,value in enumerate(fields):
                item=QTableWidgetItem(value);self.table.setItem(row,col,item)
                if row==0 and best is not None:
                    item.setBackground(QBrush(QColor('#e7f5ec')))
        self.csv_btn.setEnabled(True);self.save_btn.setEnabled(True)
        if result.ranked:self.table.selectRow(0)

    def _selected(self):
        rows=self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows or self.result is None:return None
        idx=rows[0].row()
        return self.result.ranked[idx] if idx < len(self.result.ranked) else None

    def show_candidate(self):
        c=self._selected();self.cases.setRowCount(0)
        self.detail.clear();self.plot.set_data({'trace':[]})
        if c is None:return
        self.cases.setRowCount(len(c.outcomes))
        for row,o in enumerate(c.outcomes):
            fields=[o.case.title,o.status,_show(o.summary.get('detected_time_s')),
                    _show(o.summary.get('delay_s'))]
            for col,txt in enumerate(fields):self.cases.setItem(row,col,QTableWidgetItem(txt))
        if c.outcomes:self.cases.selectRow(0)

    def show_case(self):
        c=self._selected();rows=self.cases.selectionModel().selectedRows() if self.cases.selectionModel() else []
        if c is None or not rows:return
        i=rows[0].row()
        if i>=len(c.outcomes):return
        o=c.outcomes[i]
        self.detail.setPlainText(f'【パラメータ】閾値{c.threshold:g} m/s² / 静止{c.hold_ms:g} ms\n'
                                 +diagnose(o,self.result.tolerance_s).as_text())
        if o.result is None:self.plot.set_data({'trace':[]})
        else:self.plot.set_data({'trace':list(o.result.log.rows),
                                 'contact_time':o.summary.get('true_contact_s'),
                                 'detected_time':o.summary.get('detected_time_s')})

    def export_csv(self):
        if self.result is None:return
        name,_=QFileDialog.getSaveFileName(self,'パラメータ比較結果',
                export_path('landing_optimization_v7.csv'),'CSV (*.csv)')
        if not name:return
        try:Path(name).write_text('\ufeff'+make_optimization_csv(self.result),encoding='utf-8')
        except OSError as exc:QMessageBox.critical(self,'CSV書き出し失敗',str(exc))

    def save_record(self):
        if self.result is None or self.saved:return
        best=self.result.best
        result=self.result
        observed=(f'仮想{len(result.candidates)}組を比較。'
                  + (f'候補：閾値{best.threshold:g} m/s²、静止{best.hold_ms:g} ms、'
                     f'成功{best.counts["成功"]}件。' if best else '評価可能な候補なし。'))
        try:
            with tempfile.TemporaryDirectory(prefix='cansat-v7-report-') as td:
                path=Path(td)
                report=path/'landing_optimization_v7.csv'
                cases=path/'landing_optimization_cases_v7.csv'
                report.write_text('\ufeff'+make_optimization_csv(result),encoding='utf-8')
                cases.write_text('\ufeff'+make_optimization_cases_csv(result),encoding='utf-8')
                rec=new_record(module='着地検知',mode='外部シミュレーション',
                    tester=self.tester.text().strip() or '未入力',
                    scenario=f'v7: パラメータ比較（{len(result.candidates)}組）',
                    code_version=self.version.text().strip() or 'v7_parameter_grid',
                    status='未判定',expected='合成8条件で設定の成功数・早期誤検知・遅延を比較',
                    observed=observed,
                    notes='仮想条件での探索で実機最適値ではありません。'
                          f' CPP={Path(result.source).name} SHA256={result.source_sha256}',
                    metrics={'combinations':len(result.candidates),
                             'best_success':best.counts['成功'] if best else None,
                             'best_threshold_mps2':best.threshold if best else None,
                             'best_hold_ms':best.hold_ms if best else None})
                add_record(rec,[report,cases])
        except (OSError,ValueError) as exc:
            QMessageBox.critical(self,'保存失敗',str(exc));return
        self.saved=True;self.save_btn.setEnabled(False)
        if self.on_saved:self.on_saved()
        QMessageBox.information(self,'保存完了','v7の比較レポートと条件別結果を保存しました。GitHubへの送信はしていません。')
