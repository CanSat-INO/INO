"""Purpose-based project dashboard over the existing real Test Lab screens."""
from __future__ import annotations
import os
from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QBoxLayout, QGridLayout, QGroupBox, QLabel, QPushButton, QScrollArea
import project_store as store
import records
from project_theme import apply_space_theme


class ProjectDashboard(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        body = QWidget(); scroll.setWidget(body)
        root = QVBoxLayout(body); root.setSpacing(14)
        start = QGroupBox('実験ワークスペース')
        row = QBoxLayout(QBoxLayout.LeftToRight, start)
        self._workspace_actions = row
        label = QLabel('共通情報・CSV確認・解析・記録'); label.setWordWrap(True)
        row.addWidget(label, 1)
        button = QPushButton('＋ 新しい実験')
        button.setObjectName('projectStartExperiment')
        button.setProperty('v13Role', 'primary')
        button.clicked.connect(host.navigation._open_workflow)
        row.addWidget(button)
        root.addWidget(start)
        self._share_actions = None
        if store.active_id():
            share_row = QBoxLayout(QBoxLayout.LeftToRight)
            self._share_actions = share_row
            share_note = QLabel('メンバーへ同じプロジェクトを渡す')
            share_note.setWordWrap(True)
            share_row.addWidget(share_note, 1)
            share = QPushButton('プロジェクトを共有…')
            share.setObjectName('projectShareCurrent')
            share.clicked.connect(self.share_project)
            share_row.addWidget(share)
            root.addLayout(share_row)
            from project_auto_gui import AutoPanel
            auto_panel=AutoPanel(host)
            from project_storage_gui import PackagesPanel,configure
            host.project_packages=PackagesPanel(host)
            settings=QPushButton('共有設定（年度・班／GitHub／ZIPの場所）…')
            settings.setObjectName('projectStorageSettings');settings.clicked.connect(lambda:configure(host))
            root.addWidget(settings)
        groups = (
            ('センサー・解析', (('センサーCSV解析', 'センサー実験・ログ解析'),)),
            ('実験・記録', (('実験台帳', '実験記録・コード版管理（v16）'), ('結果ダッシュボード', '結果ダッシュボード'))),
            ('ミッション・制御', (('フェーズ別ミッション', 'フェーズ別ミッション・仮想試験'),
                             ('仮想通信', 'Main・CAM・Drive 仮想通信検証（v18）'),
                             ('C++ロジック検証', '着地・Drive・CAM・Main ロジック検証'))),
            ('比較・共有', (('時系列比較', '実験管理・仮想ログ比較（v19）'),
                          ('台帳・添付の品質点検', '共通基盤・全体品質チェック（v21）'))),
        )
        grid = QGridLayout()
        self._route_grid = grid
        self._route_cards = []
        self._route_columns = 2
        for index, (title, targets) in enumerate(groups):
            group = QGroupBox(title)
            column = QVBoxLayout(group)
            for position, (label, target) in enumerate(targets):
                button = QPushButton(label)
                if position == 0:
                    button.setObjectName(f'projectQuick{index + 1}')
                button.clicked.connect(lambda checked=False, name=target: host.navigation.open_named_tab(name))
                column.addWidget(button)
            column.addStretch(1)
            self._route_cards.append(group)
            grid.addWidget(group, index // 2, index % 2)
        grid.setColumnStretch(0, 1); grid.setColumnStretch(1, 1)
        root.addLayout(grid)
        self._route_viewport = scroll.viewport()
        self._route_viewport.installEventFilter(self)
        self.summary = QLabel(); self.summary.setWordWrap(True); self.summary.setTextFormat(Qt.PlainText)
        self.summary.setObjectName('v13ExperimentStatus')
        root.addWidget(self.summary)
        all_features = QPushButton('すべての機能・検索を開く')
        all_features.clicked.connect(host.navigation.show_all_features)
        root.addWidget(all_features)
        if store.active_id():
            root.addWidget(auto_panel)
            root.addWidget(host.project_packages)
        root.addStretch(1)
        self.refresh()
        self._reflow_route_cards()
        self._reflow_workspace_actions()

    @staticmethod
    def route_column_count(width):
        return 1 if width < 720 else 2

    def eventFilter(self, watched, event):
        if (
            watched is getattr(self, "_route_viewport", None)
            and event.type() == QEvent.Resize
        ):
            self._reflow_route_cards()
            self._reflow_workspace_actions()
        return super().eventFilter(watched, event)

    def _reflow_route_cards(self):
        columns = self.route_column_count(
            self._route_viewport.width()
        )
        if columns == self._route_columns:
            return

        self._route_columns = columns

        # ボタンとグループを再生成せず位置だけ変更
        for card in self._route_cards:
            self._route_grid.removeWidget(card)

        for index, card in enumerate(self._route_cards):
            self._route_grid.addWidget(
                card,
                index // columns,
                index % columns
            )

        self._route_grid.setColumnStretch(0, 1)
        self._route_grid.setColumnStretch(
            1, 1 if columns == 2 else 0
        )

    def _reflow_workspace_actions(self):
        width = self._route_viewport.width()
        direction = (
            QBoxLayout.TopToBottom
            if width < 720
            else QBoxLayout.LeftToRight
        )

        layouts = (
            self._workspace_actions,
            self._share_actions,
        )

        for layout in layouts:
            if layout is not None and layout.direction() != direction:
                layout.setDirection(direction)

    def share_project(self):
        from project_share_dialogs import export_project
        project_id = store.active_id()
        if project_id:
            export_project(self, project_id)

    def refresh(self):
        try:
            items = records.load_records()
            success = sum(item.get('status') == '成功' for item in items)
            failure = sum(item.get('status') == '失敗' for item in items)
            self.summary.setText(f'このプロジェクトの記録：{len(items)}件 ｜ 成功 {success} ｜ 失敗 {failure} ｜ 未判定 {len(items)-success-failure}')
        except (ValueError, OSError, TypeError, KeyError) as exc:
            self.summary.setText('台帳を確認してください：' + str(exc))


def install_project_shell(window):
    nav = window.navigation
    title = store.project_title()
    window.setWindowTitle('CanSat Simulation | ' + title)
    heading = window.findChild(QLabel, 'moduleLabTitle')
    heading.setText('CanSat Simulation')
    info = window.findChild(QLabel, 'moduleLabSubtitle')
    info.setTextFormat(Qt.PlainText)
    info.setText('プロジェクト：' + title + ' ｜ OFFLINE LAB・実機接続なし'
                 + (' ｜ 確認用・一時データ' if os.environ.get('CANSAT_LAB_PREVIEW') == '1' else ''))
    info.setWordWrap(True)
    switch = QPushButton('プロジェクト切替')
    switch.setObjectName('projectSwitch')
    switch.clicked.connect(window.close)  # Existing close confirmation protects unsaved input.
    nav.header_frame.layout().insertWidget(2, switch)
    window.project_dashboard = ProjectDashboard(window)
    nav.project_home = window.project_dashboard
    nav.stack.addWidget(nav.project_home)
    # Keep large legacy forms scrollable instead of forcing the whole window taller.
    nav.stack.removeWidget(nav.tabs)
    tabs_page = QScrollArea()
    tabs_page.setWidgetResizable(True)
    tabs_page.setWidget(nav.tabs)
    # Refresh scroll ranges immediately when the current page's size hint changes.
    nav.tabs.currentChanged.connect(lambda index: tabs_page.setWidgetResizable(True))
    nav.tabs_page = tabs_page
    nav.stack.addWidget(tabs_page)
    apply_space_theme(window)
    nav.show_home()
    window.statusBar().showMessage('保存先：' + str(records.DATA_DIR) + ' ｜ プロジェクト切替時は未保存入力を確認してください')

    if store.active_id():
        from project_status_gui import ProjectStatusStrip
        window.project_status_strip = ProjectStatusStrip(window)
