"""v9 GUI: save existing v8.1/v8.2/v8.3 in-memory results to shared ledger."""
from __future__ import annotations

import json
from pathlib import Path
from project_store import export_path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QPlainTextEdit, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QHeaderView,
    QFileDialog, QMessageBox, QSplitter,
)

from records import load_records, export_bundle
from unified_results import SOURCES, list_integrated_records, save_result


class UnifiedResultsTab(QWidget):
    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self._saved_signatures = set()
        self.records = []
        root = QVBoxLayout(self)
        heading = QLabel('統合実験結果・記録（v9）')
        heading.setStyleSheet('font-size:18px; font-weight:bold; color:#17365e;')
        root.addWidget(heading)
        description = QLabel(
            '既存の「仮想CAN」「C++モジュール連携」「異常分析」で実行済みの結果を、'
            '実験記録・チーム共有と同じ台帳に保存します。保存後は結果ダッシュボードにも反映されます。'
            '記録は仮想試験であり実機データではありません。GitHubへの自動送信は行いません。')
        description.setWordWrap(True)
        root.addWidget(description)

        row = QHBoxLayout()
        row.addWidget(QLabel('保存対象'))
        self.source = QComboBox()
        for key, (module, _) in SOURCES.items():
            self.source.addItem(module, key)
        row.addWidget(self.source, 1)
        row.addWidget(QLabel('担当者'))
        self.tester = QLineEdit()
        self.tester.setPlaceholderText('任意')
        row.addWidget(self.tester, 1)
        self.save_button = QPushButton('現在の結果を台帳に保存')
        self.save_button.clicked.connect(self.save_current)
        row.addWidget(self.save_button)
        root.addLayout(row)
        self.status = QLabel('対象の試験画面で先に実行し、ここで保存対象を選択してください。')
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel('記録フィルター'))
        self.module_filter = QComboBox()
        self.module_filter.addItem('すべての試験', '')
        self.module_filter.currentIndexChanged.connect(self.reload)
        filter_bar.addWidget(self.module_filter)
        self.status_filter = QComboBox()
        for label, value in [('すべて', ''), ('成功', '成功'), ('失敗', '失敗'), ('未判定', '未判定')]:
            self.status_filter.addItem(label, value)
        self.status_filter.currentIndexChanged.connect(self.reload)
        filter_bar.addWidget(self.status_filter)
        self.keyword = QLineEdit()
        self.keyword.setPlaceholderText('担当者・シナリオ等を検索')
        self.keyword.textChanged.connect(self.reload)
        filter_bar.addWidget(self.keyword, 1)
        refresh = QPushButton('更新')
        refresh.clicked.connect(self.reload)
        filter_bar.addWidget(refresh)
        share = QPushButton('選択した記録を共有ZIPに出力')
        share.clicked.connect(self.share_selected)
        filter_bar.addWidget(share)
        root.addLayout(filter_bar)

        splitter = QSplitter(Qt.Vertical)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['日時','試験','シナリオ','評価','担当者','観測結果','ID'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for c, width in enumerate([165,180,170,65,100,290,120]):
            self.table.setColumnWidth(c, width)
        self.table.itemSelectionChanged.connect(self.show_details)
        splitter.addWidget(self.table)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        splitter.addWidget(self.details)
        splitter.setSizes([360, 170])
        root.addWidget(splitter, 1)
        self.total = QLabel('')
        root.addWidget(self.total)
        self.reload()

    def _source_result(self):
        kind = self.source.currentData()
        if kind == 'virtual_can':
            w = self.host.module_network_tab
            return kind, w.last_result, '', '', None
        if kind == 'cpp_module':
            w = self.host.cpp_module_tab
            return kind, w.last_result, w.last_sha or '', w.last_source or '', None
        if kind == 'fault_analysis':
            w = self.host.module_fault_tab
            return kind, w.result, w.cpp_sha or '', w.cpp_source or '', w.analysis
        if kind == 'cpp_individual':
            w = self.host.individual_cpp_tab
            return kind, w.last_result, w.last_sha or '', w.last_source or '', None
        raise ValueError('保存対象が不正です')

    def save_current(self, *_):
        kind, result, sha, source, analysis = self._source_result()
        if result is None:
            QMessageBox.warning(self, '未実行', '選択した機能で試験を実行してから保存してください。')
            return
        # Same in-memory result object: don't silently create duplicate snapshots.
        signature = (kind, id(result))
        if signature in self._saved_signatures:
            QMessageBox.information(self, '保存済み', 'この実行結果は保存済みです。再実行すると別の記録として保存できます。')
            return
        try:
            record = save_result(result, source_kind=kind,
                                 tester=self.tester.text().strip(),
                                 cpp_sha256=sha, cpp_source=source, analysis=analysis,
                                 notes=(self.host.individual_cpp_tab.last_notes
                                        if kind == 'cpp_individual' else ''))
        except (ValueError, TypeError, OSError, RuntimeError) as exc:
            QMessageBox.critical(self, '保存失敗', str(exc))
            return
        self._saved_signatures.add(signature)
        self.status.setText('保存完了：'+record['id']+'（ローカル台帳へ保存／GitHub未送信）')
        if hasattr(self.host, 'refresh_ledger'):
            self.host.refresh_ledger()
        self.reload()
        QMessageBox.information(self, '保存完了',
            '仮想試験結果と時系列CSVを、既存の実験台帳に保存しました。\n'
            '「実験記録・チーム共有」「結果ダッシュボード」からも確認できます。')

    def reload(self, *_):
        try:
            all_records = load_records()
            module = self.module_filter.currentData()
            status = self.status_filter.currentData()
            self.records = list_integrated_records(all_records, module=module or '',
                                                    status=status or '',
                                                    keyword=self.keyword.text())
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.status.setText('台帳読み込みエラー：'+str(exc))
            return
        modules = sorted({str(r.get('module') or 'その他') for r in all_records})
        previous = self.module_filter.currentData()
        self.module_filter.blockSignals(True)
        self.module_filter.clear()
        self.module_filter.addItem('すべての試験', '')
        for module in modules:
            self.module_filter.addItem(module, module)
        i = self.module_filter.findData(previous)
        self.module_filter.setCurrentIndex(i if i >= 0 else 0)
        self.module_filter.blockSignals(False)
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            values = [str(record.get('created_at',''))[:19], str(record.get('module','')),
                      str(record.get('scenario','')), str(record.get('status','')),
                      str(record.get('tester','')), str(record.get('observed','')),
                      str(record.get('id',''))[:12]]
            for col, val in enumerate(values):
                self.table.setItem(row,col,QTableWidgetItem(val))
        self.table.blockSignals(False)
        self.details.clear()
        self.total.setText(f'表示 {len(self.records)}件 / 全記録 {len(all_records)}件。'
                           '着地とCANの異なる試験指標は同一の数値グラフで比較しません。')

    def show_details(self):
        row = self.table.currentRow()
        if not (0 <= row < len(self.records)):
            self.details.clear()
            return
        r = self.records[row]
        attachments = ', '.join(a.get('name','') for a in r.get('attachments', []))
        self.details.setPlainText(
            '【実験ID】'+str(r.get('id',''))+'\n'
            '【種類】'+str(r.get('module',''))+' / '+str(r.get('mode',''))+'\n'
            '【条件】'+str(r.get('expected',''))+'\n'
            '【観測】'+str(r.get('observed',''))+'\n'
            '【注記】'+str(r.get('notes',''))+'\n'
            '【指標】\n'+json.dumps(r.get('metrics',{}),ensure_ascii=False,indent=2)+'\n'
            '【添付ファイル】'+(attachments or 'なし')+'\n'
            'CSVの実体は台帳の添付フォルダに保存されています。')

    def share_selected(self, *_):
        selected = sorted({x.row() for x in self.table.selectedIndexes()})
        ids = [self.records[i]['id'] for i in selected if i < len(self.records)]
        if not ids:
            QMessageBox.warning(self, '未選択', '共有する記録を一覧から選択してください。')
            return
        file, _ = QFileDialog.getSaveFileName(self, '共有ZIPを保存',
                                              export_path('cansat_module_records_v9.zip'), 'ZIP (*.zip)')
        if not file:
            return
        try:
            count = export_bundle(ids, Path(file))
        except (OSError, ValueError, RuntimeError) as exc:
            QMessageBox.critical(self, '出力失敗', str(exc))
            return
        QMessageBox.information(self, '共有ZIP出力', f'{count}件を共有ZIPに保存しました。GitHubへは送信していません。')
