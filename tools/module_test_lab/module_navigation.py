"""Non-destructive navigation shell for the existing Module Test Lab QTabWidget."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTabWidget, QStackedWidget, QScrollArea, QGridLayout, QFrame,
    QLineEdit, QMenu,
)


class ModuleNavigation(QWidget):
    """Retain each original tab QWidget and expose it as a full-page view.

    The original self.tabs and addTab() API remain compatible with previous releases.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._last_page = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        bar = QHBoxLayout()
        self.menu_button = QPushButton('☰  機能一覧')
        self.menu_button.setObjectName('moduleNavigationMenuButton')
        self.menu_button.setToolTip('どの画面からでも機能を切り替えます')
        self.menu_button.clicked.connect(self.show_menu)
        self.home_button = QPushButton('⌂ ホーム')
        self.home_button.setObjectName('moduleNavigationHomeButton')
        self.home_button.clicked.connect(self.show_home)
        self.page_title = QLabel('ホーム')
        self.page_title.setStyleSheet('font-weight: bold; color: #17365e; font-size: 15px;')
        bar.addWidget(self.menu_button)
        bar.addWidget(self.home_button)
        bar.addWidget(self.page_title, 1)
        layout.addLayout(bar)

        self.stack = QStackedWidget(self)
        self.home = QWidget()
        home_layout = QVBoxLayout(self.home)
        heading = QLabel('試験・解析メニュー')
        heading.setStyleSheet('font-weight: bold; font-size: 22px; color: #17365e;')
        home_layout.addWidget(heading)
        self.search = QLineEdit()
        self.search.setPlaceholderText('機能名で検索（例：CAN、着地、C++）')
        self.search.textChanged.connect(self.rebuild_home)
        home_layout.addWidget(self.search)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        home_layout.addWidget(self.scroll, 1)
        self.stack.addWidget(self.home)

        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.stack.addWidget(self.tabs)
        layout.addWidget(self.stack, 1)
        self.stack.setCurrentWidget(self.home)
        QTimer.singleShot(0, self._initialize)

    def _initialize(self):
        self._ready = True
        self.rebuild_home()
        self.show_home()

    def _items(self):
        return [(i, self.tabs.tabText(i)) for i in range(self.tabs.count())]

    def rebuild_home(self, *_):
        if not self._ready:
            return
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(3, 8, 3, 8)
        grid.setSpacing(12)
        query = self.search.text().strip().casefold()
        matched = [(i, name) for i, name in self._items() if query in name.casefold()]
        for position, (tab_index, title) in enumerate(matched):
            button = QPushButton(title + '   ›')
            button.setObjectName(f'moduleNavigationTile{tab_index}')
            button.setMinimumHeight(75)
            button.setStyleSheet('''
                QPushButton { text-align: left; padding: 14px; background: white;
                    border: 1px solid #d7e1ee; border-radius: 10px;
                    font-size: 14px; font-weight: bold; color: #17365e; }
                QPushButton:hover { background: #eaf2ff; border-color: #7aa5df; }
            ''')
            button.clicked.connect(lambda checked=False, i=tab_index: self.open_tab(i))
            grid.addWidget(button, position // 2, position % 2)
        if not matched:
            grid.addWidget(QLabel('一致する機能がありません。'), 0, 0)
        grid.setRowStretch(len(matched)//2 + 1, 1)
        prior = self.scroll.takeWidget()
        self.scroll.setWidget(container)
        if prior is not None:
            prior.deleteLater()

    def open_tab(self, index):
        if not 0 <= index < self.tabs.count():
            return
        self.tabs.setCurrentIndex(index)
        self.stack.setCurrentWidget(self.tabs)
        self._last_page = index
        self.page_title.setText(self.tabs.tabText(index))

    def show_home(self):
        self.rebuild_home()
        self.stack.setCurrentWidget(self.home)
        self.page_title.setText('ホーム')

    def show_menu(self):
        menu = QMenu(self)
        action = menu.addAction('⌂  ホーム')
        action.triggered.connect(self.show_home)
        menu.addSeparator()
        for i, title in self._items():
            action = menu.addAction(title)
            action.triggered.connect(lambda checked=False, index=i: self.open_tab(index))
        menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))

    def _on_tab_changed(self, index):
        if self.stack.currentWidget() is self.tabs and index >= 0:
            self.page_title.setText(self.tabs.tabText(index))
