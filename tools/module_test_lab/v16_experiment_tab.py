"""v16 journal UI: register breadboard experiments in the existing local ledger.

No serial port, GPIO, simulation execution, code compiling, or upload.
"""
from __future__ import annotations

from pathlib import Path
from project_store import export_path
from workspace_ui_state import FormSaveState

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QComboBox, QPlainTextEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QTableWidget,
    QTableWidgetItem, QFileDialog, QMessageBox, QSplitter,
    QAbstractItemView, QHeaderView, QScrollArea,
)

from records import export_bundle
from v15_sensor_core import read_sensor_csv, summary_dict, quality_report
from v16_experiment_core import (
    MODULES, PHASES, STATUSES, save_experiment, experiment_records,
    summary_counts, record_details, export_experiment_csv,
)


class ExperimentJournalV16Tab(QWidget):
    record_saved = Signal(dict)
    form_state_changed = Signal()

    def __init__(self, *, host=None, parent=None):
        super().__init__(parent)
        self.host = host
        self.visible_records = []
        self.form_save_state = FormSaveState()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setMinimumSize(0, 0)
        outer.addWidget(self.scroll)

        body = QWidget()
        self.scroll.setWidget(body)
        root = QVBoxLayout(body)

        title = QLabel('v16｜ブレッドボード実験・コード版・ログ管理')
        title.setStyleSheet('font-size: 19px; color: #17365e; font-weight: bold;')
        root.addWidget(title)
        intro = QLabel(
            'センサー単体→機能単体→フェーズ別→統合前試験の記録を残します。'
            'CSVやソースコードは「コピーして添付」し、SHA256を記録します。'
            '成功・失敗は担当者の手動判定です。既存の実験記録台帳と同じ保存先を使用します。'
        )
        intro.setWordWrap(True)
        root.addWidget(intro)
        self.form_status = QLabel()
        self.form_status.setObjectName('v16FormSaveState')
        self.form_status.setWordWrap(True)
        self.form_status.setTextFormat(Qt.PlainText)
        root.addWidget(self.form_status)

        form = QGroupBox('新しい実験の記録（保存ボタンを押すまで登録されません）')
        grid = QGridLayout(form)
        self.name = QLineEdit()
        self.name.setPlaceholderText('例：BNO055 加速度の静止試験 01')
        self.module = QComboBox(); self.module.addItems(MODULES)
        self.phase = QComboBox(); self.phase.addItems(PHASES)
        self.tester = QLineEdit(); self.tester.setPlaceholderText('任意：担当者')
        self.board = QLineEdit('ESP32-S3')
        self.code_version = QLineEdit(); self.code_version.setPlaceholderText('例：imu_test_v01 / Git commit')
        self.status = QComboBox(); self.status.addItems(STATUSES)
        self.hardware = QLineEdit(); self.hardware.setPlaceholderText('例：BNO055、3.3V')
        self.wiring = QLineEdit(); self.wiring.setPlaceholderText('例：SDA=GPIO8、SCL=GPIO9（実際の配線を記載）')
        self.expected = QLineEdit(); self.expected.setPlaceholderText('例：静止時の合成加速度が約9.8 m/s²')
        self.observed = QLineEdit(); self.observed.setPlaceholderText('例：平均9.81 m/s²、ログに異常なし')
        self.notes = QPlainTextEdit(); self.notes.setMaximumHeight(58)
        self.notes.setPlaceholderText('実験環境、再現手順、問題点、次回の改善案など')
        row_items = [
            ('実験名', self.name, '対象機能', self.module),
            ('開発段階', self.phase, '担当者', self.tester),
            ('使用基板', self.board, 'コード版', self.code_version),
            ('使用機器', self.hardware, '結果（手動）', self.status),
            ('配線', self.wiring, '期待する動作', self.expected),
        ]
        for i, (label1, field1, label2, field2) in enumerate(row_items):
            grid.addWidget(QLabel(label1), i, 0)
            grid.addWidget(field1, i, 1)
            grid.addWidget(QLabel(label2), i, 2)
            grid.addWidget(field2, i, 3)
        grid.addWidget(QLabel('観測結果'), 5, 0)
        grid.addWidget(self.observed, 5, 1, 1, 3)
        grid.addWidget(QLabel('メモ'), 6, 0)
        grid.addWidget(self.notes, 6, 1, 1, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        root.addWidget(form)

        files_box = QGroupBox('任意の添付資料（読込専用・実行しません／各10MB以内）')
        files_layout = QGridLayout(files_box)
        self.csv_path = QLineEdit()
        self.csv_path.setPlaceholderText('v15で対応したセンサーログCSV（任意）')
        self.code_path = QLineEdit()
        self.code_path.setPlaceholderText('Arduino .ino または共通C++ .cpp/.h（任意）')
        for row, (label, edit, file_types) in enumerate([
            ('ログCSV', self.csv_path, 'CSV (*.csv)'),
            ('コードファイル', self.code_path, 'Arduino / C++ (*.ino *.cpp *.hpp *.h *.c *.txt)'),
        ]):
            files_layout.addWidget(QLabel(label), row, 0)
            files_layout.addWidget(edit, row, 1)
            btn = QPushButton('参照…')
            btn.clicked.connect(lambda checked=False, e=edit, t=file_types: self.browse(e, t))
            files_layout.addWidget(btn, row, 2)
        files_layout.setColumnStretch(1, 1)
        root.addWidget(files_box)

        actions = QHBoxLayout()
        for text, method in [
            ('サンプル入力をセット', self.load_sample),
            ('CSVを事前確認', self.preview_csv),
            ('実験記録を保存', self.save),
            ('一覧更新', self.reload),
        ]:
            btn = QPushButton(text)
            btn.clicked.connect(method)
            actions.addWidget(btn)
        actions.addStretch(1)
        root.addLayout(actions)
        share_row = QHBoxLayout()
        share_row.addWidget(QLabel('GitHub共有：'))
        self.github_buttons = []
        for label, action in [
            ('接続確認', 'check'),
            ('選択した実験をGitHubに送信', 'upload'),
            ('チームの実験をGitHubから取得', 'download'),
        ]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, a=action: self.github_action(a))
            self.github_buttons.append(button)
            share_row.addWidget(button)
        share_row.addStretch(1)
        root.addLayout(share_row)
        self.github_message = QLabel('手動共有です。送信する記録を選び、内容を確認してから操作してください。')
        self.github_message.setWordWrap(True)
        self.github_message.setStyleSheet('color: #4D6583; font-size: 12px;')
        root.addWidget(self.github_message)
        # Keep delete/restore above the expandable history list.
        cleanup_row = QHBoxLayout()
        cleanup_row.addWidget(QLabel('ローカル整理：削除前にZIP退避／GitHub上の記録は維持'))
        cleanup_row.addStretch(1)
        delete_button = QPushButton('選択記録を削除（退避）')
        delete_button.clicked.connect(self.delete_selected_local)
        cleanup_row.addWidget(delete_button)
        restore_button = QPushButton('退避ZIPから復元')
        restore_button.clicked.connect(self.restore_local)
        cleanup_row.addWidget(restore_button)
        root.addLayout(cleanup_row)
        self.message = QLabel('実験を記録する際は、実機で確認した結果とコードの版を記入してください。')
        self.message.setObjectName('v13ExperimentStatus')
        self.message.setWordWrap(True)
        root.addWidget(self.message)

        splitter = QSplitter(Qt.Vertical)
        journal = QWidget()
        journal_layout = QVBoxLayout(journal)
        journal_layout.setContentsMargins(0, 0, 0, 0)
        filters = QHBoxLayout()
        self.keyword = QLineEdit()
        self.keyword.setPlaceholderText('実験名・担当者・コード版・配線・メモで検索')
        self.keyword.textChanged.connect(self.reload)
        filters.addWidget(QLabel('実験履歴'))
        filters.addWidget(self.keyword, 1)
        self.module_filter = QComboBox()
        self.module_filter.addItem('全モジュール', '')
        for module in MODULES: self.module_filter.addItem(module, module)
        self.module_filter.currentIndexChanged.connect(self.reload)
        filters.addWidget(self.module_filter)
        self.phase_filter = QComboBox()
        self.phase_filter.addItem('全段階', '')
        for phase in PHASES: self.phase_filter.addItem(phase, phase)
        self.phase_filter.currentIndexChanged.connect(self.reload)
        filters.addWidget(self.phase_filter)
        journal_layout.addLayout(filters)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ('日時', '実験名', '機能', '開発段階', '担当者', 'コード版', '結果'))
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(220)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        for col, width in [(0,150), (2,125), (3,135), (4,80), (5,110), (6,75)]:
            self.table.setColumnWidth(col, width)
        self.table.itemSelectionChanged.connect(self.show_details)
        journal_layout.addWidget(self.table)
        export_row = QHBoxLayout()
        self.count = QLabel('')
        export_row.addWidget(self.count, 1)
        for title, action in [('表示した記録をCSV出力', self.export_csv),
                              ('選択した記録を共有ZIPに出力', self.export_zip)]:
            button = QPushButton(title); button.clicked.connect(action)
            export_row.addWidget(button)
        journal_layout.addLayout(export_row)
        splitter.addWidget(journal)
        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMinimumHeight(100)
        self.details.setPlaceholderText('一覧の行を選択すると、CSVのSHA256や配線メモが表示されます。')
        splitter.addWidget(self.details)
        splitter.setChildrenCollapsible(False)
        splitter.setMinimumHeight(430)
        splitter.setSizes([310, 110])
        root.addWidget(splitter, 1)
        self.reload()
        for name in ('name','tester','board','code_version','hardware','wiring','expected','observed','csv_path','code_path'):
            getattr(self,name).textChanged.connect(self._refresh_form_state)
        for combo in (self.module,self.phase,self.status):
            combo.currentTextChanged.connect(self._refresh_form_state)
        self.notes.textChanged.connect(self._refresh_form_state)
        self._refresh_form_state()

    def _refresh_form_state(self, *_):
        state = self.form_save_state.state(self._form_data())
        record_id = self.form_save_state.record_id
        if state == 'unsaved':
            text = '実験結果：未保存。「実験記録を保存」でこのPCの台帳に登録します。'
        elif state == 'changed':
            text = '実験結果：前回の保存後に未保存の変更があります。'
        else:
            text = '実験結果：この入力をこのPCの台帳に保存済み。'
        self.form_status.setText(text + (f' 前回のID：{record_id[:8]}' if record_id else ''))
        self.form_status.setToolTip(record_id or '')
        self.form_state_changed.emit()

    def github_action(self, action):
        """Use the already-existing host GitHub worker, never run Git in the UI."""
        if self.host is None or not hasattr(self.host, 'start_github_sync'):
            QMessageBox.warning(self, 'GitHub共有', '共有機能を持つTest Lab本体から開いてください。')
            return
        if action == 'upload':
            selected = self._selected_records()
            if not selected:
                QMessageBox.information(self, '記録未選択', '履歴から共有する実験の行を選択してください。')
                return
            self.host.start_github_sync('upload', record_ids=[r['id'] for r in selected])
        else:
            self.host.start_github_sync(action)

    def set_sync_busy(self, busy: bool):
        for button in self.github_buttons:
            button.setEnabled(not busy)

    def set_sync_status(self, message: str):
        self.github_message.setText(message.replace('\n', '  |  '))

    def browse(self, edit, type_spec):
        selection, _ = QFileDialog.getOpenFileName(self, '添付ファイルを選択', '', type_spec)
        if selection: edit.setText(selection)

    def load_sample(self, *_):
        path = Path(__file__).resolve().parent / 'v15_samples' / 'imu_bno055_sample.csv'
        self.name.setText('サンプル：BNO055静止・振動ログ（未検証）')
        self.module.setCurrentIndex(0)
        self.phase.setCurrentIndex(1)
        self.status.setCurrentText('未判定')
        self.board.setText('ESP32-S3（サンプル・実機未使用）')
        self.hardware.setText('BNO055（模擬データ）')
        self.wiring.setText('サンプルのため配線なし')
        self.code_version.setText('demo-v15')
        self.expected.setText('CSVの読込・記録方法を試す')
        self.observed.setText('模擬ログ（実機での成功ではない）')
        self.notes.setPlainText('これは操作デモです。試験結果は未判定で保存してください。')
        self.csv_path.setText(str(path))
        self.code_path.clear()
        self.message.setText('サンプル入力をセットしました。保存する場合は「未判定」のままにしてください。')

    def _form_data(self):
        return dict(name=self.name.text(), module=self.module.currentText(),
                    phase=self.phase.currentText(), tester=self.tester.text(),
                    board=self.board.text(), code_version=self.code_version.text(),
                    hardware=self.hardware.text(), wiring=self.wiring.text(),
                    expected=self.expected.text(), observed=self.observed.text(),
                    notes=self.notes.toPlainText(), status=self.status.currentText(),
                    csv_path=self.csv_path.text().strip() or None,
                    code_path=self.code_path.text().strip() or None)

    def preview_csv(self, *_):
        path = self.csv_path.text().strip()
        if not path:
            QMessageBox.information(self, 'CSV未選択', 'ログCSVを選択してください。')
            return
        try:
            log = read_sensor_csv(path)
            report = summary_dict(log)
        except (ValueError, OSError, UnicodeError) as exc:
            QMessageBox.warning(self, 'CSVを読み込めません', str(exc)); return
        issues = quality_report(log)
        self.message.setText(
            f"事前確認：{log.row_count}行・{len(log.signals)}信号。"
            ' CSV品質の参考チェックであり、実機の合否判定ではありません。')
        self.details.setPlainText(
            f"CSV: {log.source_name}\nSHA256: {log.source_sha256}\n"
            f"信号: {', '.join(log.signals)}\n"
            + '\n'.join('・' + note for note in issues))

    def save(self, *_):
        try:
            result = save_experiment(**self._form_data())
        except (ValueError, OSError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, '実験記録を保存できません', str(exc))
            return
        self.message.setText('記録を保存しました。ID: ' + result['id'] + '（ローカル台帳）')
        self.form_save_state.mark_saved(self._form_data(), result['id'])
        self._refresh_form_state()
        self.record_saved.emit(result)
        self.reload()
        if self.host is not None and hasattr(self.host, 'refresh_ledger'):
            self.host.refresh_ledger()

    def reload(self, *_):
        try:
            self.visible_records = experiment_records(
                search=self.keyword.text(), module=self.module_filter.currentData() or '',
                phase=self.phase_filter.currentData() or '')
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.message.setText('履歴読み込みエラー：' + str(exc))
            return
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.visible_records))
        for row, rec in enumerate(self.visible_records):
            info = rec.get('metrics', {}).get('v16', {})
            cells = (rec.get('created_at','')[:19], rec.get('scenario',''),
                     rec.get('module',''), info.get('phase',''),
                     rec.get('tester',''), rec.get('code_version',''), rec.get('status',''))
            for col, value in enumerate(cells):
                self.table.setItem(row, col, QTableWidgetItem(str(value)))
        self.table.blockSignals(False)
        counts = summary_counts(self.visible_records)
        self.count.setText('表示 {}件｜成功 {}・失敗 {}・未判定 {}'.format(
            counts['total'], counts['成功'], counts['失敗'], counts['未判定']))

    def _selected_records(self):
        rows = sorted({cell.row() for cell in self.table.selectedIndexes()})
        return [self.visible_records[i] for i in rows if 0 <= i < len(self.visible_records)]

    def show_details(self):
        selected = self._selected_records()
        if selected:
            self.details.setPlainText(record_details(selected[0]))
        else:
            self.details.clear()

    def restore_local(self):
        if self.host is None or not hasattr(self.host, 'restore_local_archive'):
            QMessageBox.warning(self, '復元', 'Test Lab本体から開いてください。')
            return
        self.host.restore_local_archive()

    def delete_selected_local(self):
        if self.host is None or not hasattr(self.host, 'delete_local_selected'):
            QMessageBox.warning(self, 'ローカル削除', 'Test Lab本体から開いてください。')
            return
        ids = [r['id'] for r in self._selected_records()]
        self.host.delete_local_selected(record_ids=ids)

    def export_csv(self, *_):
        if not self.visible_records:
            QMessageBox.information(self, '出力対象なし', '表示中の実験記録がありません。'); return
        path, _ = QFileDialog.getSaveFileName(self, '実験一覧CSVを保存', export_path('cansat_experiments_v16.csv'), 'CSV (*.csv)')
        if not path: return
        try:
            n = export_experiment_csv(self.visible_records, Path(path))
        except (ValueError, OSError, TypeError) as exc:
            QMessageBox.warning(self, 'CSV出力に失敗', str(exc)); return
        self.message.setText(f'{n}件の一覧CSVを出力しました。添付ファイルは含まれません。')

    def export_zip(self, *_):
        chosen = self._selected_records()
        if not chosen:
            QMessageBox.information(self, '記録未選択', '履歴から出力する行を選択してください。'); return
        path, _ = QFileDialog.getSaveFileName(self, '実験資料ZIPを保存', export_path('cansat_experiment_v16.zip'), 'ZIP (*.zip)')
        if not path: return
        try:
            n = export_bundle([r['id'] for r in chosen], Path(path))
        except (ValueError, OSError, TypeError, KeyError) as exc:
            QMessageBox.warning(self, 'ZIP出力に失敗', str(exc)); return
        self.message.setText(f'{n}件をZIPに出力しました。外部共有前にログ・ソースの内容を確認してください。')
