"""Offline experiment workspace using the existing v15/v16/v19 screens."""
from __future__ import annotations
from pathlib import Path
from project_store import export_path, active_id
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QComboBox, QFileDialog, QMessageBox, QPlainTextEdit, QScrollArea,
)
from v20_workflow_core import (
    CONTEXT_LIMITS, inspect_csv, load_session, make_session, save_session, verify_session_file,
)

ROOT = Path(__file__).resolve().parent
WORKSPACE_LABEL = '共通基盤・実験ワークフロー（v20）'
CONTEXT_LABELS = {'name': '実験名', 'tester': '担当者', 'hardware': '使用機器', 'code_version': 'コード版'}


class WorkflowV20Tab(QWidget):
    LINKS = (
        ('センサーを確認', ('センサー実験・ログ解析', '実験記録・コード版管理（v16）')),
        ('コードを検証', ('着地・Drive・CAM・Main ロジック検証', 'Main・CAM・Drive C++実コード検証')),
        ('ミッションを試す', ('フェーズ別ミッション・仮想試験', 'Main・CAM・Drive 仮想通信検証（v18）')),
        ('記録を比較', ('実験管理・仮想ログ比較（v19）', '統合実験結果')),
    )

    def __init__(self, *, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.measured_info = self.reference_info = self.imported = None
        self.session_path = self.saved_snapshot = self.record_id = None
        self.sent = set()
        self.context_panels = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        summary = QGroupBox('今回の実験・作業状況')
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(12, 8, 12, 8)
        summary_layout.setSpacing(4)
        self.progress, self.next_step, self.save_status = QLabel(), QLabel(), QLabel()
        for label in (self.progress, self.next_step, self.save_status):
            label.setWordWrap(True)
            label.setTextFormat(Qt.PlainText)
            summary_layout.addWidget(label)
        layout.addWidget(summary)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        layout.addWidget(self.scroll)
        body = QWidget()
        self.scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(17, 10, 17, 20)
        root.setSpacing(10)
        title = QLabel('v20｜実験ワークスペース')
        title.setStyleSheet('font-size: 22px; font-weight: 800; color: #143B74;')
        root.addWidget(title)
        subtitle = QLabel('共通情報 → CSV確認 → 解析 → 記録票で保存。比較は必要なときに行います。実機・地上局・ROS 2には接続しません。')
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)
        common = QGroupBox('1．共通の実験情報')
        grid = QGridLayout(common)
        self.context_fields = {}
        placeholders = ('例：BNO055 静止試験 01', '任意：担当者', '例：ESP32-S3 / BNO055', '例：imu_test_v01 / Git commit')
        for i, ((key, name), placeholder) in enumerate(zip(CONTEXT_LABELS.items(), placeholders)):
            edit = QLineEdit()
            edit.setObjectName('v20_' + key)
            edit.setMaxLength(CONTEXT_LIMITS[key])
            edit.setPlaceholderText(placeholder)
            label = QLabel(name)
            label.setBuddy(edit)
            grid.addWidget(label, i // 2, (i % 2) * 2)
            grid.addWidget(edit, i // 2, (i % 2) * 2 + 1)
            self.context_fields[key] = edit
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        root.addWidget(common)
        intake = QGroupBox('2．実験CSVを選んで確認')
        fields = QVBoxLayout(intake)
        for name, attr, ref in (('実験・測定CSV', 'measured_path', False), ('仮想・参考CSV（任意）', 'reference_path', True)):
            line = QHBoxLayout()
            line.addWidget(QLabel(name))
            edit = QLineEdit()
            edit.setObjectName('v20' + attr)
            edit.setReadOnly(True)
            edit.setPlaceholderText('未選択')
            setattr(self, attr, edit)
            line.addWidget(edit, 1)
            button = QPushButton('選択…')
            button.clicked.connect(lambda checked=False, r=ref: self.pick_csv(r))
            line.addWidget(button)
            if ref:
                clear = QPushButton('解除')
                clear.clicked.connect(lambda: self.set_path('', is_reference=True))
                line.addWidget(clear)
            fields.addLayout(line)
        meta = QHBoxLayout()
        meta.addWidget(QLabel('データ種別'))
        self.kind = QComboBox()
        self.kind.addItems(('サンプル', '実測', '仮想'))
        meta.addWidget(self.kind)
        demo = QPushButton('BNO055デモCSVをセット')
        demo.clicked.connect(self.use_demo)
        meta.addWidget(demo)
        meta.addStretch(1)
        fields.addLayout(meta)
        self.verify_button = QPushButton('CSVを確認（件数・SHA256）')
        self.verify_button.clicked.connect(self.verify_csvs)
        fields.addWidget(self.verify_button)
        self.status = QLabel('CSVを選択してください。情報だけを先にJSON保存することもできます。')
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        self.status.setObjectName('v13ExperimentStatus')
        fields.addWidget(self.status)
        root.addWidget(intake)
        actions = QGroupBox('3．解析・記録へ進む')
        row = QHBoxLayout(actions)
        for text, callback in (('① 解析画面へ', self.to_sensor), ('② 実験記録票へ', self.to_journal), ('③ ログ比較へ（任意）', self.to_compare)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            row.addWidget(button)
        layout.addWidget(actions)
        warning = QLabel('共通情報とCSVを引き継ぎます。台帳への保存はv16で「実験記録を保存」を押してください。実機の合否・比較の信号と単位は担当者が確認します。')
        warning.setWordWrap(True)
        root.addWidget(warning)
        saved = QGroupBox('4．作業情報を保存・再開')
        saved_layout = QVBoxLayout(saved)
        self.memo = QPlainTextEdit()
        self.memo.setPlaceholderText('次の作業や配線変更のメモ（3000文字以内）')
        self.memo.setMaximumHeight(65)
        saved_layout.addWidget(self.memo)
        saves = QHBoxLayout()
        for text, callback in (('作業情報をJSON保存', self.export_session), ('作業情報をJSON読込', self.import_session)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            saves.addWidget(button)
        saved_layout.addLayout(saves)
        tip = QLabel('作業JSONは共通情報・メモ・CSVのパスとSHA256を保存します。CSV本体・台帳の記録は含みません。JSON読込後はCSVを再確認してください。共有前に担当者名やパスを確認してください。')
        tip.setWordWrap(True)
        saved_layout.addWidget(tip)
        root.addWidget(saved)
        more = QPushButton('その他の既存機能を表示')
        more.setCheckable(True)
        root.addWidget(more)
        guide = QGroupBox('目的から機能を選ぶ')
        guide_grid = QGridLayout(guide)
        for i, (name, labels) in enumerate(self.LINKS):
            group = QGroupBox(name)
            col = QVBoxLayout(group)
            for target in labels:
                button = QPushButton('開く：' + target)
                button.clicked.connect(lambda checked=False, label=target: self.open_label(label))
                col.addWidget(button)
            guide_grid.addWidget(group, i // 2, i % 2)
        more.toggled.connect(guide.setVisible)
        guide.hide()
        root.addWidget(guide)
        root.addStretch(1)
        self.last_identity = self._identity()
        for edit in self.context_fields.values():
            edit.textChanged.connect(self._edited)
        self.kind.currentTextChanged.connect(self._edited)
        self.memo.textChanged.connect(self._edited)
        self.host.v16_journal_tab.record_saved.connect(self._record_saved)
        self._refresh_state()

    def context(self):
        return {key: edit.text() for key, edit in self.context_fields.items()}

    def _identity(self):
        return (tuple(self.context().items()), self.measured_path.text(), self.reference_path.text(), self.kind.currentText())

    def _snapshot(self):
        def digest(key, info):
            previous = (self.imported or {}).get(key)
            return info.sha256 if info else previous['sha256'] if previous else None
        return (self._identity(), self.memo.toPlainText(), digest('measured', self.measured_info), digest('reference', self.reference_info))

    def _edited(self, *_):
        identity = self._identity()
        if identity != self.last_identity:
            self.sent.clear()
            self.record_id = None
            self.last_identity = identity
        self._refresh_state()

    def _refresh_state(self):
        self.progress.setText('CSV：' + ('確認済み' if self.measured_info else '未確認')
                              + ' ｜ 解析：' + ('引継ぎ済み' if 'sensor' in self.sent else '未引継ぎ')
                              + ' ｜ 台帳：' + (f'保存済み（ID: {self.record_id}）' if self.record_id else '未保存')
                              + ' ｜ 比較（任意）：' + ('引継ぎ済み' if 'compare' in self.sent else '未引継ぎ'))
        if not self.measured_info:
            step = 'CSVを選び「CSVを確認」を押してください。'
        elif 'sensor' not in self.sent:
            step = '「① 解析画面へ」でグラフ・統計を確認してください。'
        elif not self.record_id:
            step = '「② 実験記録票へ」で条件・結果を確認し、v16で保存してください。'
        else:
            step = '台帳の保存を確認しました。必要なら比較、作業を再開するならJSON保存を行ってください。'
        self.next_step.setText('次の操作：' + step)
        state = '未保存' if self.saved_snapshot is None else ('保存内容と一致' if self.saved_snapshot == self._snapshot() else '未保存の変更あり')
        self.save_status.setText('作業JSON：' + state + (f' ｜ {Path(self.session_path).name[:80]}' if self.session_path else '') + '（台帳とは別）')
        self.save_status.setToolTip(str(self.session_path or ''))

    def _show_context(self, tab):
        if tab not in self.context_panels:
            panel = QWidget()
            row = QHBoxLayout(panel)
            row.setContentsMargins(0, 0, 0, 0)
            label = QLabel()
            label.setWordWrap(True)
            label.setTextFormat(Qt.PlainText)
            row.addWidget(label, 1)
            back = QPushButton('実験ワークスペースへ戻る')
            back.clicked.connect(lambda: self.open_label(WORKSPACE_LABEL))
            row.addWidget(back)
            tab.layout().insertWidget(0, panel)
            self.context_panels[tab] = label
        text = ' ｜ '.join(f'{CONTEXT_LABELS[key]}：{value or "未入力"}' for key, value in self.context().items())
        self.context_panels[tab].setText('v20から引継ぎ時の実験情報：' + text)

    def open_label(self, label):
        for index in range(self.host.tabs.count()):
            if self.host.tabs.tabText(index) == label:
                self.host.navigation.open_tab(index)
                return True
        QMessageBox.warning(self, '機能が見つかりません', f'対象機能がありません：{label}')
        return False

    def pick_csv(self, is_reference=False):
        choice, _ = QFileDialog.getOpenFileName(self, 'CSVを選択', '', 'CSV (*.csv)')
        if choice:
            self.set_path(choice, is_reference=is_reference)

    def set_path(self, path, *, is_reference=False):
        (self.reference_path if is_reference else self.measured_path).setText(str(path))
        if is_reference:
            self.reference_info = None
        else:
            self.measured_info = None
        if self.imported:
            self.imported['reference' if is_reference else 'measured'] = None
        self.sent.clear()
        self.record_id = None
        self.status.setText('CSVの選択を変更しました。「CSVを確認」で内容をチェックしてください。')
        self._edited()

    def use_demo(self):
        self.set_path(ROOT / 'v15_samples' / 'imu_bno055_sample.csv')
        self.set_path('', is_reference=True)
        self.kind.setCurrentText('サンプル')
        self.status.setText('架空のBNO055サンプルです。CSV確認後、解析・記録へ送れます。')

    def verify_csvs(self):
        try:
            if not self.measured_path.text().strip():
                raise ValueError('実験・測定CSVを選択してください。')
            measured = inspect_csv(self.measured_path.text())
            reference = inspect_csv(self.reference_path.text()) if self.reference_path.text().strip() else None
            for key, found in (('measured', measured), ('reference', reference)):
                previous = (self.imported or {}).get(key)
                if previous and (not found or previous['sha256'] != found.sha256):
                    raise ValueError(f'{key} のCSVが保存時と異なります。手動で選び直してください。')
            if self.measured_info and self.measured_info.sha256 != measured.sha256:
                self.sent.clear()
                self.record_id = None
            self.measured_info, self.reference_info = measured, reference
            self.imported = None
            self.status.setText(f'CSV確認済み（実機合否ではありません）：{measured.name} / {measured.rows}行・{measured.signals}信号 / SHA256 {measured.sha256[:14]}…'
                                + (f'　参考：{reference.rows}行・{reference.signals}信号' if reference else ''))
            self._refresh_state()
            return True
        except (ValueError, OSError, UnicodeError, TypeError) as exc:
            self.measured_info = self.reference_info = None
            self.sent.clear()
            self.record_id = None
            self.status.setText('CSV確認失敗：' + str(exc))
            self._refresh_state()
            QMessageBox.warning(self, 'CSV確認失敗', str(exc))
            return False

    def _ensure_fresh(self):
        if self.measured_info is None or (self.reference_path.text() and self.reference_info is None):
            return self.verify_csvs()
        try:
            for info in (self.measured_info, self.reference_info):
                if info:
                    verify_session_file({'path': info.path, 'sha256': info.sha256})
            return True
        except (OSError, ValueError, UnicodeError) as exc:
            self.measured_info = self.reference_info = None
            self.sent.clear()
            self.record_id = None
            self.status.setText('ファイル変更を検出：' + str(exc))
            self._refresh_state()
            QMessageBox.warning(self, 'CSV再確認が必要', str(exc))
            return False

    def to_sensor(self):
        if not self._ensure_fresh(): return
        tab = self.host.v15_sensor_tab
        tab.open_file(Path(self.measured_info.path))
        if tab.log is None: return
        self._show_context(tab)
        if self.open_label('センサー実験・ログ解析'):
            self.sent.add('sensor')
        self._refresh_state()

    def to_journal(self):
        if not self._ensure_fresh(): return
        tab = self.host.v16_journal_tab
        values = {**self.context(), 'csv_path': self.measured_info.path}
        values['name'] = values['name'].strip() or f'CSV実験：{Path(self.measured_info.path).stem}'[:120]
        conflicts = [key for key, value in values.items() if getattr(tab, key).text().strip() and getattr(tab, key).text() != value]
        if (conflicts or tab.status.currentText() != '未判定') and QMessageBox.question(
            self, '記録票の入力を確認',
            '記録票には別の入力があります。共通4項目とCSVを今回の情報に置き換え、結果を未判定に戻しますか？'
            '\n配線・観測結果・添付コードなど、他の入力は残ります。保存前に今回の実験に合うか確認してください。',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes: return
        for key, value in values.items():
            getattr(tab, key).setText(value)
        tab.status.setCurrentText('未判定')
        self._show_context(tab)
        self.open_label('実験記録・コード版管理（v16）')
        tab.message.setText('v20から共通情報とCSVを引き継ぎました。配線・観測結果・添付を確認してから手動保存してください。')
        self.sent.add('journal')
        self._refresh_state()

    def _record_saved(self, record):
        if 'journal' not in self.sent or self.measured_info is None: return
        context = self.context()
        name = context['name'].strip() or f'CSV実験：{Path(self.measured_info.path).stem}'[:120]
        meta = record.get('metrics', {}).get('v16', {})
        if (record.get('scenario') == name and record.get('tester') == context['tester'].strip()
                and record.get('code_version') == context['code_version'].strip()
                and meta.get('hardware') == context['hardware'].strip()
                and meta.get('log', {}).get('sha256') == self.measured_info.sha256):
            self.record_id = record['id']
            self._refresh_state()

    def to_compare(self):
        if not self._ensure_fresh(): return
        tab = self.host.v19_compare_tab
        tab.measured_path.setText(self.measured_info.path)
        tab.reference_path.setText(self.reference_info.path if self.reference_info else '')
        tab.measured_log = tab.reference_log = None
        tab.measured_signal.clear()
        tab.reference_signal.clear()
        tab.shift.setValue(0)
        tab.unit_check.setChecked(False)
        tab.invalidate()
        self._show_context(tab)
        tab.status.setText('v20から共通情報とCSVを引き継ぎました。「CSVを読み込む」→信号・単位確認→比較してください。')
        if self.open_label('実験管理・仮想ログ比較（v19）'):
            self.sent.add('compare')
        self._refresh_state()

    def export_session(self):
        if (self.measured_path.text() or self.reference_path.text()) and not self._ensure_fresh(): return
        dest, _ = QFileDialog.getSaveFileName(self, '作業情報を保存', export_path('cansat_v20_workflow.json', session=True), 'JSON (*.json)')
        if not dest: return
        try:
            item = make_session(self.measured_info, self.reference_info, kind=self.kind.currentText(), memo=self.memo.toPlainText(), context=self.context())
            item["project_id"] = active_id() or "legacy"
            save_session(item, dest)
            self.session_path = dest
            self.saved_snapshot = self._snapshot()
            self._refresh_state()
        except (ValueError, OSError, TypeError) as exc:
            QMessageBox.warning(self, '作業情報の保存失敗', str(exc))

    def import_session(self):
        source, _ = QFileDialog.getOpenFileName(self, '作業情報を選択', '', 'JSON (*.json)')
        if not source: return
        try:
            item = load_session(source)
            if item.get("project_id", active_id() or "legacy") != (active_id() or "legacy"):
                raise ValueError("別プロジェクトの作業JSONです。対応するプロジェクトへ切り替えてください。")
        except (ValueError, OSError, UnicodeError, TypeError) as exc:
            QMessageBox.warning(self, '作業情報の読込失敗', str(exc))
            return
        has_draft = any(self.context().values()) or self.measured_path.text() or self.reference_path.text() or self.memo.toPlainText() or self.kind.currentText() != 'サンプル'
        if has_draft and self.saved_snapshot != self._snapshot() and QMessageBox.question(
            self, '未保存の変更', '現在の未保存の作業情報を、読み込むJSONで置き換えますか？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        ) != QMessageBox.Yes: return
        self.measured_info = self.reference_info = None
        self.measured_path.setText(item['measured']['path'] if item['measured'] else '')
        self.reference_path.setText(item['reference']['path'] if item['reference'] else '')
        for key, edit in self.context_fields.items():
            edit.setText(item.get('context', {}).get(key, ''))
        self.kind.setCurrentText(item['classification'])
        self.memo.setPlainText(item['memo'])
        self.imported = item
        self.sent.clear()
        self.record_id = None
        self.last_identity = self._identity()
        self.session_path = source
        self.saved_snapshot = self._snapshot()
        self._refresh_state()
        self.status.setText('JSON読込済み。CSVは未確認です。「CSVを確認」で元CSVのSHA256を照合してください。')
