"""Project selector. Starts one isolated Test Lab process at a time."""
from __future__ import annotations
from pathlib import Path
import os
import sys
from datetime import datetime

from PySide6.QtCore import Qt, QProcess, QProcessEnvironment, QSize
from PySide6.QtGui import QColor, QPainter, QPen, QRadialGradient, QBrush
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QScrollArea, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGroupBox, QLabel, QLineEdit, QPushButton, QListWidget,
    QListWidgetItem, QMessageBox, QSizePolicy, QSpinBox,
)
import project_store as store
from project_theme import apply_space_theme


class OrbitArtwork(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(140, 88)
        self.setMaximumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName('装飾用の惑星と軌道')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        painter.translate(cx, cy)
        scale = min((self.width() - 12) / 190, (self.height() - 8) / 140)
        painter.scale(scale, scale)
        cx = cy = 0
        painter.setPen(QColor('#335872'))
        painter.drawLine(int(cx-85), int(cy), int(cx+85), int(cy))
        painter.drawLine(int(cx), int(cy-60), int(cx), int(cy+60))
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(-25)
        painter.drawEllipse(-86, -40, 172, 80)
        painter.rotate(65)
        painter.drawEllipse(-70, -52, 140, 104)
        painter.restore()
        gradient = QRadialGradient(cx-17, cy-19, 68)
        gradient.setColorAt(0, QColor('#9BD9E9'))
        gradient.setColorAt(.3, QColor('#377A9F'))
        gradient.setColorAt(.7, QColor('#14354F'))
        gradient.setColorAt(1, QColor('#07101D'))
        painter.setPen(QPen(QColor('#68A9C4'), 1))
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(int(cx-42), int(cy-42), 84, 84)
        painter.end()


class ProjectHub(QMainWindow):
    def __init__(self, app_file: Path, parent=None):
        super().__init__(parent)
        self.app_file = Path(app_file).resolve()
        self.worker = None
        self.output = ''
        self.setObjectName('projectHub')
        self.setWindowTitle('CanSat Simulation')
        self.resize(1020, 720)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)
        surface = QWidget()
        surface.setObjectName('projectHubBody')
        scroll.setWidget(surface)
        center = QHBoxLayout(surface)
        center.setContentsMargins(0, 0, 0, 0)
        body = QWidget()
        body.setObjectName('projectHubContent')
        body.setMaximumWidth(1080)
        center.addStretch(1); center.addWidget(body, 1000); center.addStretch(1)
        root = QVBoxLayout(body)
        root.setContentsMargins(22, 14, 22, 18)
        root.setSpacing(12)
        hero = QHBoxLayout()
        title_column = QVBoxLayout()
        tag = QLabel('CanSat / INO'); tag.setObjectName('projectEyebrow')
        title = QLabel('CanSat Simulation'); title.setObjectName('projectHeading')
        title_column.addWidget(tag); title_column.addWidget(title)
        title_column.addStretch(1)
        hero.addLayout(title_column, 3)
        hero.addWidget(OrbitArtwork(), 1)
        root.addLayout(hero)
        existing = QGroupBox('このPCのプロジェクト')
        existing_layout = QVBoxLayout(existing)
        self.projects = QListWidget()
        self.projects.setMinimumHeight(96)
        self.projects.setMaximumHeight(230)
        self.projects.setWordWrap(True)
        self.projects.itemDoubleClicked.connect(lambda item: self.open_selected())
        self.projects.currentItemChanged.connect(self.selection_changed)
        existing_layout.addWidget(self.projects)
        self.empty_state = QLabel('まだ参加中のプロジェクトはありません。\n班のプロジェクトに参加するか、新しく作成してください。')
        self.empty_state.setObjectName('projectEmpty')
        self.empty_state.setAlignment(Qt.AlignCenter)
        self.empty_state.setWordWrap(True)
        self.empty_state.setMinimumHeight(56)
        existing_layout.addWidget(self.empty_state)
        self.open_button = QPushButton('選択したプロジェクトを開く →')
        self.open_button.setObjectName('projectOpen')
        self.open_button.clicked.connect(self.open_selected)
        self.open_button.setEnabled(False)
        existing_layout.addWidget(self.open_button)
        root.addWidget(existing)
        join_row = QHBoxLayout()
        self.join_button = QPushButton('班のプロジェクトに参加')
        self.join_button.setObjectName('projectShowJoin')
        self.join_button.setProperty('v13Role', 'primary')
        self.join_button.setCheckable(True)
        join_row.addWidget(self.join_button)
        self.create_toggle = QPushButton('＋ 新しいプロジェクトを作る')
        self.create_toggle.setObjectName('projectShowCreate')
        self.create_toggle.setCheckable(True)
        join_row.addWidget(self.create_toggle)
        root.addLayout(join_row)
        self.join_area = QWidget()
        join_layout = QVBoxLayout(self.join_area)
        join_layout.setContentsMargins(0, 0, 0, 0)
        from project_auto_gui import CatalogPanel
        self.catalog = CatalogPanel(self)
        join_layout.addWidget(self.catalog)
        self.import_button = QPushButton('受け取ったプロジェクト共有ファイルから参加…')
        self.import_button.setObjectName('projectImportShare')
        self.import_button.clicked.connect(self.import_shared_project)
        join_layout.addWidget(self.import_button)
        share_hint = QLabel('班からリンクを案内された場合は上の欄へ。共有ファイルを受け取った場合は下のボタンから登録できます。')
        share_hint.setWordWrap(True); share_hint.setObjectName('projectHint')
        join_layout.addWidget(share_hint)
        root.addWidget(self.join_area)
        self.join_area.hide()
        create = QGroupBox('新しいプロジェクト')
        self.create_form = create
        form = QFormLayout(create)
        hint = QLabel('新しい年度や班のプロジェクトを立ち上げるときに使います。既存の班に入る場合は「班のプロジェクトに参加」を選んでください。')
        hint.setWordWrap(True); form.addRow(hint)
        self.name = QLineEdit(); self.name.setMaxLength(120)
        self.name.setPlaceholderText('例：INO 2026 / CanSat A班 2027')
        self.owner = QLineEdit(); self.owner.setMaxLength(80)
        self.owner.setPlaceholderText('任意：担当者名')
        self.purpose = QLineEdit(); self.purpose.setMaxLength(500)
        self.purpose.setPlaceholderText('目的・概要（任意）')
        form.addRow('プロジェクト名', self.name)
        self.year=QSpinBox();self.year.setRange(2000,2200);self.year.setValue(datetime.now().year)
        self.year.setObjectName('projectYear')
        self.team=QLineEdit();self.team.setMaxLength(80);self.team.setPlaceholderText('例：INO / 次年度CanSat班')
        self.team.setObjectName('projectTeam')
        group_row=QHBoxLayout();group_row.addWidget(self.year);group_row.addWidget(self.team,1)
        form.addRow('年度・班',group_row)
        form.addRow('担当者（任意）', self.owner)
        form.addRow('目的・概要（任意）', self.purpose)
        self.create_button = QPushButton('作成して開く →')
        self.create_button.setObjectName('projectCreate')
        self.create_button.setEnabled(False)
        self.name.textChanged.connect(lambda value: self.create_button.setEnabled(bool(value.strip())))
        self.create_button.clicked.connect(self.create_project)
        form.addRow(self.create_button)
        root.addWidget(create)
        create.hide()
        self.join_button.toggled.connect(self.show_join)
        self.create_toggle.toggled.connect(self.show_create)
        self.more_toggle = QPushButton('共有・従来のデータを開く…')
        self.more_toggle.setObjectName('projectShowMore')
        self.more_toggle.setCheckable(True)
        root.addWidget(self.more_toggle)
        self.more_area = QWidget()
        more_layout = QVBoxLayout(self.more_area)
        more_layout.setContentsMargins(0, 0, 0, 0)
        self.share_button = QPushButton('選択したプロジェクトの共有ファイルを作る…')
        self.share_button.setObjectName('projectExportShare')
        self.share_button.setEnabled(False)
        self.share_button.clicked.connect(self.export_shared_project)
        more_layout.addWidget(self.share_button)
        legacy = QPushButton('従来の実験を開く（未分類）')
        legacy.clicked.connect(lambda: self.launch(None))
        more_layout.addWidget(legacy)
        root.addWidget(self.more_area)
        self.more_area.hide()
        self.more_toggle.toggled.connect(self.more_area.setVisible)
        bottom = QHBoxLayout()
        refresh = QPushButton('一覧を更新'); refresh.clicked.connect(self.reload)
        bottom.addWidget(refresh); bottom.addStretch(1)
        root.addLayout(bottom)
        self.note = QLabel(); self.note.setObjectName('projectHint'); self.note.setWordWrap(True)
        self.note.setTextFormat(Qt.PlainText)
        root.addWidget(self.note)
        root.addStretch(1)
        apply_space_theme(self)
        self.reload()

    def show_join(self, visible):
        self.join_area.setVisible(visible)
        if visible:
            self.create_toggle.setChecked(False)
            self.catalog.repository.setFocus()

    def show_create(self, visible):
        self.create_form.setVisible(visible)
        if visible:
            self.join_button.setChecked(False)
            self.name.setFocus()

    def reload(self):
        selected = self.projects.currentItem()
        selected_id = selected.data(Qt.UserRole) if selected else None
        self.projects.clear()
        try:
            projects, invalid = store.list_projects()
        except (OSError, ValueError, UnicodeError) as exc:
            self.projects.hide()
            self.empty_state.setText('プロジェクト一覧を読み込めません。')
            self.empty_state.show()
            self.note.setText('一覧を読み込めません：' + str(exc)); return
        self.projects.setVisible(bool(projects))
        self.open_button.setVisible(bool(projects))
        self.empty_state.setText('まだ参加中のプロジェクトはありません。\n班のプロジェクトに参加するか、新しく作成してください。')
        self.empty_state.setVisible(not projects)
        for project in projects:
            item = QListWidgetItem(project.name + '\n' + (f'{project.year or "年度未設定"} ｜ {project.team} ｜ ') + (project.owner or '担当者未入力') + ' ｜ ID: ' + project.id[:8])
            item.setData(Qt.UserRole, project.id)
            item.setToolTip((project.purpose or project.name) + '\nID: ' + project.id)
            item.setSizeHint(QSize(300, 66))
            self.projects.addItem(item)
            if project.id == selected_id:
                self.projects.setCurrentItem(item)
        if selected_id is None and len(projects) == 1:
            self.projects.setCurrentRow(0)
        self.note.setText((f'{len(projects)}プロジェクト。選択して開けます。' if projects else '班のメンバーは「班のプロジェクトに参加」から始められます。')
                          + (f' 読み取れないプロジェクト：{invalid}件（元データは変更していません）。' if invalid else ''))
        if os.environ.get('CANSAT_LAB_PREVIEW') == '1':
            self.note.setText('確認用プレビュー・一時データです。終了すると作成したプロジェクトは消えます。')

    def create_project(self):
        try:
            project = store.create_project(self.name.text(), self.owner.text(), self.purpose.text(),year=self.year.value(),team=self.team.text())
        except (ValueError, OSError, UnicodeError) as exc:
            QMessageBox.warning(self, '作成できません', str(exc)); return
        self.name.clear(); self.owner.clear(); self.purpose.clear(); self.team.clear()
        self.create_toggle.setChecked(False)
        self.reload()
        self.launch(project.id)

    def open_selected(self):
        item = self.projects.currentItem()
        if item:
            self.launch(item.data(Qt.UserRole))

    def selection_changed(self, current, previous):
        self.open_button.setEnabled(current is not None)
        self.share_button.setEnabled(current is not None)

    def import_shared_project(self):
        from project_share_dialogs import import_project
        result = import_project(self)
        if result is not None:
            self.reload()
            for index in range(self.projects.count()):
                item = self.projects.item(index)
                if item.data(Qt.UserRole) == result.project.id:
                    self.projects.setCurrentItem(item)
                    break

    def export_shared_project(self):
        item = self.projects.currentItem()
        if item is not None:
            from project_share_dialogs import export_project
            export_project(self, item.data(Qt.UserRole))

    def launch(self, project_id):
        if self.worker is not None:
            return
        try:
            if project_id:
                store.read_project(project_id)
            process = QProcess(self)
            process.setProgram(sys.executable)
            process.setArguments([str(self.app_file), '--project', project_id] if project_id else [str(self.app_file), '--legacy'])
            process.setWorkingDirectory(str(self.app_file.parent))
            environment = QProcessEnvironment.systemEnvironment()
            environment.remove(store.PROJECT_ENV)
            process.setProcessEnvironment(environment)
            process.setProcessChannelMode(QProcess.MergedChannels)
            self.output = ''
            process.readyReadStandardOutput.connect(self._read_output)
            process.finished.connect(self._finished)
            self.worker = process
            process.start()
            if not process.waitForStarted(5000):
                self.worker = None
                raise OSError(process.errorString())
            self.join_button.setChecked(False)
            self.create_toggle.setChecked(False)
            self.more_toggle.setChecked(False)
            for index in range(self.projects.count()):
                item = self.projects.item(index)
                if item.data(Qt.UserRole) == project_id:
                    self.projects.setCurrentItem(item)
                    break
            self.hide()
        except (ValueError, OSError, TypeError) as exc:
            QMessageBox.warning(self, '起動できません', str(exc))

    def _read_output(self):
        if self.worker:
            self.output = (self.output + bytes(self.worker.readAllStandardOutput()).decode('utf-8', errors='replace'))[-8000:]

    def _finished(self, code, status):
        process = self.worker
        self._read_output()
        self.worker = None
        if process:
            process.deleteLater()
        self.reload(); self.show(); self.raise_()
        if code != 0:
            QMessageBox.warning(self, '作業画面が終了しました', '終了コード：' + str(code) + '\n' + self.output[-3000:])

    def closeEvent(self, event):
        if self.worker is not None:
            event.ignore(); return
        if self.catalog.background.before_close():
            event.ignore(); return
        event.accept()
        QApplication.instance().quit()
