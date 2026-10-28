"""v20 guided offline workflow; reuse v15/v16/v19 instead of duplicating analyzers."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox, QLabel,
    QLineEdit, QPushButton, QComboBox, QFileDialog, QMessageBox,
    QPlainTextEdit, QScrollArea,
)
from v20_workflow_core import (
    inspect_csv, load_session, make_session, save_session, verify_session_file,
)

ROOT = Path(__file__).resolve().parent


class WorkflowV20Tab(QWidget):
    """Does not save experiments, run C++, or infer hardware pass/fail."""

    LINKS = (
        ('センサーを確認', ('センサー実験・ログ解析', '実験記録・コード版管理（v16）')),
        ('コードを検証', ('着地・Drive・CAM・Main ロジック検証', 'Main・CAM・Drive C++実コード検証')),
        ('ミッションを試す', ('フェーズ別ミッション・仮想試験', 'Main・CAM・Drive 仮想通信検証（v18）')),
        ('記録を比較', ('実験管理・仮想ログ比較（v19）', '統合実験結果')),
    )

    def __init__(self, *, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.measured_info = None
        self.reference_info = None
        self.imported = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        layout.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        root = QVBoxLayout(body)
        root.setContentsMargins(17, 10, 17, 20)
        root.setSpacing(12)

        title = QLabel('v20｜CanSat 個別実験ワークフロー')
        title.setStyleSheet('font-size: 22px; font-weight: 800; color: #143B74;')
        root.addWidget(title)
        subtitle = QLabel('ブレッドボード実験 → CSV解析 → 実験記録 → 仮想試験・比較を、既存の機能で順番に進めます。'
                          '地上局・実機・ROS 2への接続は行いません。')
        subtitle.setWordWrap(True)
        root.addWidget(subtitle)

        guide = QGroupBox('目的から機能を選ぶ（既存機能への案内）')
        grid = QGridLayout(guide)
        for index, (name, labels) in enumerate(self.LINKS):
            group = QGroupBox(f'{index+1}．{name}')
            col = QVBoxLayout(group)
            for target in labels:
                b = QPushButton('開く：' + target)
                b.clicked.connect(lambda checked=False, label=target: self.open_label(label))
                col.addWidget(b)
            grid.addWidget(group, index // 2, index % 2)
        root.addWidget(guide)

        intake = QGroupBox('実験CSVの受け渡し（ここでは判定も保存もしません）')
        fields = QVBoxLayout(intake)
        for name, attr, sample, callback in (
            ('実験・測定CSV', 'measured_path', True, lambda: self.pick_csv(False)),
            ('仮想・参考CSV（任意）', 'reference_path', False, lambda: self.pick_csv(True)),
        ):
            line = QHBoxLayout()
            line.addWidget(QLabel(name))
            edit = QLineEdit()
            edit.setObjectName('v20' + attr)
            edit.setReadOnly(True)
            edit.setPlaceholderText('未選択')
            setattr(self, attr, edit)
            line.addWidget(edit, 1)
            button = QPushButton('選択…')
            button.clicked.connect(callback)
            line.addWidget(button)
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
        self.status = QLabel('未選択。まずCSVを選ぶかサンプルをセットしてください。')
        self.status.setWordWrap(True)
        self.status.setObjectName('v13ExperimentStatus')
        fields.addWidget(self.status)
        root.addWidget(intake)

        actions = QGroupBox('確認したCSVを既存画面へ引き継ぐ')
        row = QHBoxLayout(actions)
        for text, callback in (
            ('① 解析画面へ', self.to_sensor),
            ('② 実験記録票へ', self.to_journal),
            ('③ ログ比較画面へ', self.to_compare),
        ):
            b = QPushButton(text)
            b.clicked.connect(callback)
            row.addWidget(b)
        root.addWidget(actions)
        warning = QLabel('引き継ぐのはCSVのパスだけです。実験の成功判定、結果保存、単位の一致確認、'
                         '比較実行はそれぞれの画面で行ってください。')
        warning.setWordWrap(True)
        warning.setStyleSheet('color: #5A6980; font-size: 12px;')
        root.addWidget(warning)

        saved = QGroupBox('作業の再開・引き継ぎ（CSV自体は含めません）')
        saved_layout = QVBoxLayout(saved)
        self.memo = QPlainTextEdit()
        self.memo.setPlaceholderText('次の作業や配線変更のメモ。コードや個人情報を無断で共有しないでください。')
        self.memo.setMaximumHeight(72)
        saved_layout.addWidget(self.memo)
        saves = QHBoxLayout()
        for label, callback in [('作業情報をJSON保存', self.export_session),
                                ('作業情報をJSON読込', self.import_session)]:
            b = QPushButton(label); b.clicked.connect(callback); saves.addWidget(b)
        saves.addStretch(1)
        saved_layout.addLayout(saves)
        tip = QLabel('JSONはファイルパスとSHA256のみです。別PCでは元CSVが必要です。'
                     '再読込後は必ず「CSVを確認」で内容とハッシュを照合します。')
        tip.setWordWrap(True)
        saved_layout.addWidget(tip)
        root.addWidget(saved)
        root.addStretch(1)

    def open_label(self, label: str) -> bool:
        tabs = self.host.tabs
        for i in range(tabs.count()):
            if tabs.tabText(i) == label:
                self.host.navigation.open_tab(i)
                return True
        QMessageBox.warning(self, '機能が見つかりません', f'対象機能がありません：{label}')
        return False

    def pick_csv(self, is_reference=False):
        choice, _ = QFileDialog.getOpenFileName(self, 'CSVを選択', '', 'CSV (*.csv)')
        if choice:
            self.set_path(choice, is_reference=is_reference)

    def set_path(self, path, *, is_reference=False):
        # Reset validation state even when a different CSV with same name is chosen.
        edit = self.reference_path if is_reference else self.measured_path
        edit.setText(str(path))
        if is_reference:
            self.reference_info = None
        else:
            self.measured_info = None
        self.imported = None
        self.status.setText('CSVを選択しました。「CSVを確認」で内容をチェックしてください。')

    def use_demo(self):
        path = ROOT / 'v15_samples' / 'imu_bno055_sample.csv'
        self.set_path(path)
        self.reference_path.clear()
        self.reference_info = None
        self.kind.setCurrentText('サンプル')
        self.status.setText('架空のBNO055サンプルを選択しました。CSV確認後、解析・記録へ送れます。')

    def verify_csvs(self):
        try:
            if not self.measured_path.text().strip():
                raise ValueError('実験・測定CSVを選択してください。')
            m = inspect_csv(self.measured_path.text())
            r = inspect_csv(self.reference_path.text()) if self.reference_path.text().strip() else None
            if self.imported:
                for key, found in (('measured', m), ('reference', r)):
                    previous = self.imported.get(key)
                    if previous and (not found or previous['sha256'] != found.sha256):
                        raise ValueError(f'{key} のCSVが保存時と異なります。手動で選び直してください。')
            self.measured_info, self.reference_info = m, r
            self.status.setText(f'CSV確認済み（実機合否ではありません）：{m.name} / '
                                f'{m.rows}行・{m.signals}信号 / SHA256 {m.sha256[:14]}…'
                                + (f'　参考：{r.rows}行・{r.signals}信号' if r else ''))
            self.imported = None
            return True
        except (ValueError, OSError, UnicodeError, TypeError) as exc:
            self.measured_info = self.reference_info = None
            self.status.setText('CSV確認失敗：' + str(exc))
            QMessageBox.warning(self, 'CSV確認失敗', str(exc))
            return False

    def _ensure_fresh(self) -> bool:
        if self.measured_info is None:
            return self.verify_csvs()
        try:
            self.measured_info = verify_session_file({
                'path': self.measured_info.path, 'sha256': self.measured_info.sha256})
            if self.reference_info is not None:
                self.reference_info = verify_session_file({
                    'path': self.reference_info.path, 'sha256': self.reference_info.sha256})
            return True
        except (OSError, ValueError, UnicodeError) as exc:
            self.measured_info = self.reference_info = None
            self.status.setText('ファイル変更を検出：' + str(exc))
            QMessageBox.warning(self, 'CSV再確認が必要', str(exc))
            return False

    def to_sensor(self):
        if not self._ensure_fresh(): return
        tab = self.host.v15_sensor_tab
        tab.open_file(Path(self.measured_info.path))
        self.open_label('センサー実験・ログ解析')

    def to_journal(self):
        if not self._ensure_fresh(): return
        tab = self.host.v16_journal_tab
        tab.csv_path.setText(self.measured_info.path)
        if not tab.name.text().strip():
            tab.name.setText(f'CSV実験：{Path(self.measured_info.path).stem}')
        tab.status.setCurrentText('未判定')
        self.open_label('実験記録・コード版管理（v16）')
        tab.message.setText('v20からCSVパスを引き継ぎました。実験内容を確認してから手動保存してください。')

    def to_compare(self):
        if not self._ensure_fresh(): return
        tab = self.host.v19_compare_tab
        tab.measured_path.setText(self.measured_info.path)
        tab.reference_path.setText(self.reference_info.path if self.reference_info else '')
        tab.measured_log = None
        tab.reference_log = None
        tab.unit_check.setChecked(False)
        tab.invalidate()
        tab.status.setText('v20からCSVパスを引き継ぎました。比較画面で参考CSVを選び、'
                           '「CSVを読み込む」→単位確認→比較してください。')
        self.open_label('実験管理・仮想ログ比較（v19）')

    def export_session(self):
        if not self._ensure_fresh(): return
        dest, _ = QFileDialog.getSaveFileName(self, '作業情報を保存',
                                              'cansat_v20_workflow.json', 'JSON (*.json)')
        if not dest: return
        try:
            item = make_session(self.measured_info, self.reference_info,
                                kind=self.kind.currentText(), memo=self.memo.toPlainText())
            save_session(item, dest)
            self.status.setText('作業情報を保存しました（CSV本体は含みません）。')
        except (ValueError, OSError, TypeError) as exc:
            QMessageBox.warning(self, '作業情報の保存失敗', str(exc))

    def import_session(self):
        source, _ = QFileDialog.getOpenFileName(self, '作業情報を選択', '', 'JSON (*.json)')
        if not source: return
        try:
            item = load_session(source)
        except (ValueError, OSError, UnicodeError, TypeError) as exc:
            QMessageBox.warning(self, '作業情報の読込失敗', str(exc)); return
        self.imported = item
        self.measured_info = self.reference_info = None
        self.measured_path.setText(item['measured']['path'] if item['measured'] else '')
        self.reference_path.setText(item['reference']['path'] if item['reference'] else '')
        self.kind.setCurrentText(item['classification'])
        self.memo.setPlainText(item['memo'])
        self.status.setText('JSONを読み込みました。元CSVを確認してから「CSVを確認」を押してください。'
                            'JSON読み込みではCSVを自動実行・解析しません。')
