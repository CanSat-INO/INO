"""Menu integration for safely detaching existing Test Lab tabs."""

from PySide6.QtWidgets import QMessageBox, QPushButton

from detached_tab_manager import DetachedTabManager


def install_detached_tab_ui(host):
    """Add window controls without changing existing feature widgets."""
    if hasattr(host, "detached_tab_manager"):
        raise RuntimeError("複数ウィンドウ機能は既に登録されています")

    manager = DetachedTabManager(host.tabs)
    host.detached_tab_manager = manager

    menu = host.menuBar().addMenu("ウィンドウ")

    open_action = menu.addAction(
        "現在の機能を別ウィンドウで開く"
    )
    restore_action = menu.addAction(
        "すべての別ウィンドウを元に戻す"
    )

    def is_feature_visible():
        navigation = host.navigation
        tabs_page = getattr(
            navigation, "tabs_page", host.tabs
        )
        return (
            navigation.stack.currentWidget() is tabs_page
            and host.tabs.currentIndex() >= 0
        )

    def open_current():
        if not is_feature_visible():
            QMessageBox.information(
                host,
                "別ウィンドウ",
                "先に機能一覧から開きたい機能を選択してください。"
            )
            return

        index = host.tabs.currentIndex()

        try:
            manager.detach(index)
        except Exception as exc:
            QMessageBox.warning(
                host,
                "別ウィンドウを開けません",
                str(exc)
            )

    def refresh_menu():
        open_action.setEnabled(is_feature_visible())
        restore_action.setEnabled(manager.count() > 0)

    open_action.triggered.connect(open_current)
    restore_action.triggered.connect(
        lambda checked=False: manager.close_all()
    )
    menu.aboutToShow.connect(refresh_menu)

    # Add an accessible button to the existing navigation header.
    header = getattr(host.navigation, "header_frame", None)
    if header is None or header.layout() is None:
        raise RuntimeError("ナビゲーションヘッダーが見つかりません")

    button = QPushButton("別窓で開く", header)
    button.setObjectName("detachedOpenCurrentFeature")
    button.setToolTip("現在の機能を別ウィンドウで開きます")
    button.clicked.connect(open_current)

    # Project switch is subsequently inserted at position 2.
    header.layout().insertWidget(2, button)
    host.detached_open_button = button

    def update_button(*_):
        button.setEnabled(is_feature_visible())

    host.navigation.stack.currentChanged.connect(update_button)
    host.tabs.currentChanged.connect(update_button)
    update_button()

    return manager
