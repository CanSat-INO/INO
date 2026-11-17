"""Move existing tab widgets into separate windows without cloning them."""

from PySide6.QtCore import QObject
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QPushButton
)


class DetachedTabWindow(QMainWindow):
    """A separate window that returns its widget when closed."""

    def __init__(self, manager, page, title):
        super().__init__()
        self.manager = manager
        self.page = page

        self.setWindowTitle(f"{title} | CanSat Simulation")
        self.resize(950, 680)
        self.setCentralWidget(page)

    def closeEvent(self, event):
        try:
            self.manager.restore(self.page)
        except Exception:
            import traceback
            traceback.print_exc()
            event.ignore()
            return

        event.accept()


class DetachedTabManager(QObject):
    """Keep tab positions and original widget instances intact."""

    def __init__(self, tabs):
        super().__init__(tabs)
        self.tabs = tabs
        self._windows = {}

    def count(self):
        return len(self._windows)

    def detach(self, index):
        if not 0 <= index < self.tabs.count():
            raise IndexError("タブ番号が不正です")

        selected_index = self.tabs.currentIndex()
        page = self.tabs.widget(index)

        # Already detached: bring its existing window forward.
        for entry in self._windows.values():
            if entry["placeholder"] is page:
                window = entry["window"]
                window.showNormal()
                window.raise_()
                window.activateWindow()
                return window

        title = self.tabs.tabText(index)
        icon = self.tabs.tabIcon(index)
        enabled = self.tabs.isTabEnabled(index)

        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)

        message = QLabel(
            "この機能は別ウィンドウで開いています。\n"
            "別ウィンドウを閉じると元の画面に戻ります。"
        )
        message.setWordWrap(True)

        focus_button = QPushButton("別ウィンドウを表示")

        layout.addStretch()
        layout.addWidget(message)
        layout.addWidget(focus_button)
        layout.addStretch()

        # Keep the tab slot instead of changing other tab indices.
        self.tabs.removeTab(index)
        self.tabs.insertTab(index, placeholder, icon, title)
        self.tabs.setTabEnabled(index, enabled)
        self.tabs.setCurrentIndex(selected_index)

        window = DetachedTabWindow(self, page, title)

        # Keep the original application's visual theme.
        window.setStyleSheet(self.tabs.window().styleSheet())

        self._windows[id(page)] = {
            "page": page,
            "placeholder": placeholder,
            "window": window,
            "title": title,
            "icon": icon,
            "enabled": enabled,
        }

        focus_button.clicked.connect(
            lambda checked=False, p=page: self.focus(p)
        )

        window.show()

        # QTabWidget may leave a removed page explicitly hidden.
        page.show()

        return window

    def focus(self, page):
        entry = self._windows.get(id(page))
        if entry is None:
            return

        window = entry["window"]
        window.showNormal()
        window.raise_()
        window.activateWindow()

    def restore(self, page):
        entry = self._windows.get(id(page))
        if entry is None:
            return

        index = self.tabs.indexOf(entry["placeholder"])
        if index < 0:
            raise RuntimeError("元のタブ位置が見つかりません")

        window = entry["window"]
        restored = window.takeCentralWidget()

        if restored is not page:
            raise RuntimeError("元のウィジェットを回収できません")

        self.tabs.removeTab(index)
        self.tabs.insertTab(
            index,
            page,
            entry["icon"],
            entry["title"],
        )
        self.tabs.setTabEnabled(index, entry["enabled"])

        entry["placeholder"].deleteLater()
        del self._windows[id(page)]

    def close_all(self):
        for entry in list(self._windows.values()):
            entry["window"].close()

        return not self._windows
