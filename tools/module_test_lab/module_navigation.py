"""IME-aware search and readable v13.5 module navigation.

The existing tab widgets remain unchanged. A short search debounce keeps a
Japanese input-method preedit from triggering a full menu rebuild every stroke.
"""
from __future__ import annotations
import re

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMenu, QPushButton, QScrollArea, QStackedWidget, QTabWidget, QSizePolicy,
    QVBoxLayout, QWidget,
)
from gui_theme_v13 import CATEGORIES, category_for
from navigation_search_v13_5 import matches_search


# Accessible icons use text glyphs as decoration only; their names remain visible.
ITEM_ICONS = {
    '着地検知シミュレーション': '◎',
    '実験記録・チーム共有': '▣',
    '結果ダッシュボード': '▥',
    'Arduino/CSVログ解析': '▦',
    'C++着地判定': '</>',
    '着地一括テスト': '◇',
    '着地コード比較': '▤',
    '着地パラメータ探索': '⚙',
    'センサー実験・ログ解析': '▤',
    '3モジュール・仮想CAN': '▣',
    'C++モジュール連携': '⌁',
    '異常分析': '!',
    '統合実験結果': '▥',
    'Main・CAM・Drive C++個別試験': '◈',
    'シミュレーション共通基盤': '⬡',
    'v12 実験管理・一括比較': '▤',
    '使い方・Arduinoとの接続': '▧',
}


class JapaneseSearchEdit(QLineEdit):
    compositionFinished = Signal()

    """Track IME preedit without consuming input-method events.

    All composition processing remains in Qt's native QLineEdit; we simply
    prevent menu rebuilding while it is active. This cannot repair a missing
    OS-side Japanese IME engine in WSL/X11.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._preedit_active = False
        self.setAttribute(Qt.WA_InputMethodEnabled, True)
        self.setInputMethodHints(Qt.ImhNone)

    def inputMethodEvent(self, event):
        was_composing = self._preedit_active
        self._preedit_active = bool(event.preeditString())
        super().inputMethodEvent(event)
        if not self._preedit_active and (was_composing or event.commitString()):
            self.compositionFinished.emit()

    @property
    def composing(self):
        return self._preedit_active


class NavigationTile(QFrame):
    """Real-label keyboard-accessible card without QPushButton painting."""

    clicked = Signal()
    HEIGHT = 88

    def __init__(self, title, category_title, accent, pale, glyph, parent=None):
        super().__init__(parent)
        self._title = str(title)
        self.setFixedHeight(self.HEIGHT)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAccessibleName(f'{category_title}：{title}')
        self.setToolTip(self._title)
        self.setStyleSheet(f'''
            QFrame {{ background: #FFFFFF; border: 1px solid #DCE6F1;
                      border-left: 5px solid {accent}; border-radius: 10px; }}
            QFrame:hover {{ background: #F5F9FF; border-color: #93B8ED;
                           border-left: 5px solid {accent}; }}
            QFrame:focus {{ background: #F2F7FF; border: 2px solid #2A72DC;
                           border-left: 5px solid {accent}; }}
        ''')

        line = QHBoxLayout(self)
        line.setContentsMargins(14, 10, 13, 10)
        line.setSpacing(12)

        glyph_label = QLabel(glyph)
        glyph_label.setAlignment(Qt.AlignCenter)
        glyph_label.setFixedSize(42, 42)
        glyph_label.setStyleSheet(
            f'QLabel {{ background: {pale}; color: {accent}; border: none;'
            ' border-radius: 9px; font-size: 19px; font-weight: 700; }'
        )
        glyph_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        line.addWidget(glyph_label)

        info = QVBoxLayout()
        info.setSpacing(5)
        info.setContentsMargins(0, 0, 0, 0)
        category_label = QLabel(category_title)
        category_label.setStyleSheet(
            f'QLabel {{ color: {accent}; font-size: 12px; font-weight: 700;'
            ' background: transparent; border: none; }'
        )
        category_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        info.addWidget(category_label)

        self.title_label = QLabel(self._title)
        self.title_label.setStyleSheet(
            'QLabel { color: #142F53; font-size: 15px; font-weight: 700;'
            ' background: transparent; border: none; }'
        )
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        info.addWidget(self.title_label)
        line.addLayout(info, 1)

        arrow = QLabel('›')
        arrow.setAlignment(Qt.AlignCenter)
        arrow.setFixedWidth(21)
        arrow.setStyleSheet(
            'QLabel { color: #46719C; font-size: 23px; font-weight: 600;'
            ' background: transparent; border: none; }'
        )
        arrow.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        line.addWidget(arrow)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        available = max(0, self.width() - 14 - 42 - 12 - 13 - 21 - 12 - 14)
        metrics = QFontMetrics(self.title_label.font())
        self.title_label.setText(metrics.elidedText(self._title, Qt.ElideRight, available))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ModuleNavigation(QWidget):
    """Keep the original QTabWidget/API, with a more legible home screen."""

    SEARCH_DELAY_MS = 350

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._last_page = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        self.menu_button = QPushButton('☰  機能一覧')
        self.menu_button.setObjectName('moduleNavigationMenuButton')
        self.menu_button.setToolTip('どの画面からでも機能を切り替えます')
        self.menu_button.clicked.connect(self.show_menu)
        self.menu_button.setStyleSheet('''
            QPushButton { background: #1765E8; border: 1px solid #1765E8;
                border-radius: 9px; color: #FFFFFF; padding: 10px 18px;
                font-weight: 750; }
            QPushButton:hover { background: #0F54C5; }
            QPushButton:focus { border: 2px solid #0B3F96; }
        ''')
        self.home_button = QPushButton('⌂  ホーム')
        self.home_button.setObjectName('moduleNavigationHomeButton')
        self.home_button.clicked.connect(self.show_home)
        self.home_button.setStyleSheet('''
            QPushButton { background: #FFFFFF; color: #1555B4;
                border: 1px solid #D2E1F7; border-radius: 9px;
                padding: 10px 16px; font-weight: 700; }
            QPushButton:hover { background: #F0F6FF; }
        ''')
        self.page_title = QLabel('ホーム')
        self.page_title.setStyleSheet('font-weight: 700; color: #142B50; font-size: 15px;')
        self.category_badge = QLabel('')
        self.category_badge.setVisible(False)
        bar.addWidget(self.menu_button)
        bar.addWidget(self.home_button)
        bar.addWidget(self.page_title, 1)
        bar.addWidget(self.category_badge)
        layout.addLayout(bar)

        self.stack = QStackedWidget(self)
        self.home = QWidget()
        home_layout = QVBoxLayout(self.home)
        home_layout.setContentsMargins(5, 12, 5, 0)
        home_layout.setSpacing(9)

        heading = QLabel('⚙  試験・解析メニュー')
        heading.setObjectName('moduleNavigationHeading')
        heading.setStyleSheet('font-size: 23px; color: #112A55; font-weight: 800;')
        home_layout.addWidget(heading)
        subtitle = QLabel('機能を目的別に整理しました。機能名・カテゴリ・関連語（GPS、IMU、センサー等）で検索できます。')
        subtitle.setStyleSheet('color: #4D6583; font-size: 12px;')
        home_layout.addWidget(subtitle)

        # v22: task-focused entry points; underlying screens stay untouched.
        guide_label = QLabel('まず何をしたいですか？ 目的を選ぶと対応する画面へ移動します。')
        guide_label.setObjectName('moduleNavigationV22Guide')
        guide_label.setStyleSheet('color: #254A75; font-size: 13px; font-weight: 700;')
        home_layout.addWidget(guide_label)
        quick_grid = QGridLayout()
        quick_grid.setHorizontalSpacing(10)
        quick_grid.setVerticalSpacing(8)
        quick_entries = [
            ('① センサーデータを確認', 'CSVのグラフ・欠損・平均値', 'センサー実験・ログ解析'),
            ('② 実験内容を記録', '配線・担当・コード版を保存', '実験記録・コード版管理（v16）'),
            ('③ 仮想ミッションを試す', 'フェーズ遷移と異常ケース', 'フェーズ別ミッション・仮想試験'),
            ('④ データを比較', '測定値と参考値の誤差を確認', '実験管理・仮想ログ比較（v19）'),
        ]
        for pos, (label, description, target) in enumerate(quick_entries):
            quick = QPushButton(f'{label}　｜　{description}')
            quick.setObjectName(f'moduleNavigationV22Quick{pos+1}')
            quick.setMinimumHeight(37)
            quick.setStyleSheet("""
                QPushButton { background: #FFFFFF; border: 1px solid #BED2EA;
                    border-radius: 8px; padding: 8px 11px; text-align: left;
                    color: #163A65; font-size: 12px; font-weight: 650; }
                QPushButton:hover { background: #EAF3FF; border-color: #3B83DB; }
                QPushButton:focus { border: 2px solid #1765E8; }
            """)
            quick.setToolTip(f'{label}：{description}')
            quick.clicked.connect(lambda checked=False, name=target: self.open_named_tab(name))
            quick_grid.addWidget(quick, pos // 2, pos % 2)
        home_layout.addLayout(quick_grid)

        # A single guided entry point; retain the complete legacy navigation below.
        start = QPushButton('▶  はじめての実験：ワークフローを開く')
        start.setObjectName('moduleNavigationWorkflowStart')
        start.setStyleSheet('''
            QPushButton { background: #ECF4FF; color: #174E9E;
                border: 1px solid #B8D1F4; border-radius: 8px;
                padding: 9px 15px; font-weight: 700; text-align: left; }
            QPushButton:hover { background: #DDEBFF; }
        ''')
        start.clicked.connect(self._open_workflow)
        home_layout.addWidget(start)

        all_label = QLabel('すべての機能を探す（カテゴリ・キーワード検索）')
        all_label.setStyleSheet('color: #284D79; font-size: 13px; font-weight: 700;')
        home_layout.addWidget(all_label)
        legend = QHBoxLayout()
        legend.setSpacing(7)
        for key in ('landing', 'control', 'fault', 'results', 'simulation', 'guide'):
            name, accent, pale, _ = CATEGORIES[key]
            chip = QPushButton('●  ' + name)
            chip.setObjectName('moduleNavigationCategory' + key.capitalize())
            chip.setToolTip(name + 'の機能を絞り込む（再度押すと解除）')
            chip.setStyleSheet(
                f'QPushButton {{ color: {accent}; background: {pale}; border: 1px solid {pale};'
                'border-radius: 13px; padding: 6px 12px; font-weight: 750; min-height: 17px; }'
                f'QPushButton:hover {{ border: 1px solid {accent}; }}'
            )
            chip.clicked.connect(lambda checked=False, label=name: self._toggle_category(label))
            legend.addWidget(chip)
        legend.addStretch(1)
        home_layout.addLayout(legend)

        self.search = JapaneseSearchEdit()
        self.search.setObjectName('moduleNavigationSearch')
        self.search.setPlaceholderText('⌕  機能や関連語で検索（例：CanSat、GPS、センサー、C++）')
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(38)
        self.search.setStyleSheet('''
            QLineEdit { background: #FFFFFF; border: 1px solid #CCDDF4;
                border-radius: 9px; padding: 8px 13px; color: #132C51;
                font-size: 13px; selection-background-color: #CDE3FF; }
            QLineEdit:focus { border: 2px solid #2474E5; }
        ''')
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(self.SEARCH_DELAY_MS)
        self._search_timer.timeout.connect(self._apply_search)
        self.search.textEdited.connect(self._queue_search)
        self.search.compositionFinished.connect(self._queue_search)
        home_layout.addWidget(self.search)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet('QScrollArea { background: transparent; border: none; }')
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

    def _toggle_category(self, label):
        # Category pills remain usable even without a functioning OS-side IME.
        self.search.setText('' if self.search.text() == label else label)
        self._search_timer.stop()
        self.rebuild_home()

    def _queue_search(self, *_):
        # Updating the complete menu during native IME conversion can interfere
        # with some Qt/X11 input methods. Never destroy/recreate tiles per key.
        self._search_timer.start()

    def _apply_search(self):
        if self.search.composing:
            self._search_timer.start()
            return
        self.rebuild_home()

    @staticmethod
    def _display_title(title):
        # Presentation only: original tab names remain untouched for navigation.
        title = re.sub(r"^\s*v12\s+", "", title, flags=re.I)
        return re.sub(r"[（(]\s*v(?:1[0-9]|2[0-9])(?:\.[0-9]+)?\s*[）)]", "", title, flags=re.I).strip()

    def _make_tile(self, tab_index, title):
        category = category_for(title)
        category_title, accent, pale, hint = CATEGORIES[category]
        # QFrame-based card: avoids QPushButton QSS clipping in WSL/X11.
        tile = NavigationTile(self._display_title(title), category_title, accent, pale,
                              ITEM_ICONS.get(title, '◈'))
        tile.setObjectName(f'moduleNavigationTile{tab_index}')
        tile.setToolTip(f'{self._display_title(title)}：{hint}')
        tile.clicked.connect(lambda checked=False, i=tab_index: self.open_tab(i))
        return tile

    def rebuild_home(self, *_):
        if not self._ready:
            return
        container = QWidget()
        grid = QGridLayout(container)
        grid.setContentsMargins(4, 10, 4, 14)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(11)
        query = self.search.text()
        matched = [
            (i, name) for i, name in self._items()
            if matches_search(name, CATEGORIES[category_for(name)][0], query)
        ]
        for position, (tab_index, title) in enumerate(matched):
            grid.addWidget(self._make_tile(tab_index, title), position // 2, position % 2)
        if not matched:
            empty = QLabel('一致する機能がありません。別のキーワードを入力してください。')
            empty.setStyleSheet('padding: 20px; color: #526780;')
            grid.addWidget(empty, 0, 0)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        row_count = (len(matched) + 1) // 2
        for row in range(row_count):
            grid.setRowMinimumHeight(row, NavigationTile.HEIGHT)
        # Reserve the entire card rows; overflow scrolls instead of shrinking.
        minimum = 10 + 14 + row_count * NavigationTile.HEIGHT + max(0, row_count - 1) * 11
        container.setMinimumHeight(max(80, minimum))
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
        grid.setRowStretch(row_count, 1)
        prior = self.scroll.takeWidget()
        self.scroll.setWidget(container)
        if prior is not None:
            prior.deleteLater()

    def open_named_tab(self, name):
        for index, title in self._items():
            if title == name:
                self.open_tab(index)
                return
        # Degrade gently on older/local installations where a screen is absent.
        self.search.setText(name)
        self.rebuild_home()
        self.show_home()

    def _open_workflow(self):
        for idx, name in self._items():
            if name == '共通基盤・実験ワークフロー（v20）':
                self.open_tab(idx)
                return

    def open_tab(self, index):
        if not 0 <= index < self.tabs.count():
            return
        self.tabs.setCurrentIndex(index)
        self.stack.setCurrentWidget(self.tabs)
        self._last_page = index
        self._update_header(index)

    def show_home(self):
        # Navigation and filtering must not disturb native IME composition.
        if not self.search.composing:
            self.rebuild_home()
        self.stack.setCurrentWidget(self.home)
        self.page_title.setText('ホーム')
        self.page_title.setStyleSheet('font-weight: 700; color: #142B50; font-size: 15px;')
        self.category_badge.setVisible(False)

    def show_menu(self):
        menu = QMenu(self)
        action = menu.addAction('⌂  ホーム')
        action.triggered.connect(self.show_home)
        menu.addSeparator()
        for i, title in self._items():
            action = menu.addAction(self._display_title(title))
            action.triggered.connect(lambda checked=False, index=i: self.open_tab(index))
        menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))

    def _on_tab_changed(self, index):
        if self.stack.currentWidget() is self.tabs and index >= 0:
            self._update_header(index)

    def _update_header(self, index):
        title = self.tabs.tabText(index)
        key = category_for(title)
        name, accent, pale, _ = CATEGORIES[key]
        self.page_title.setText(self._display_title(title))
        self.page_title.setStyleSheet(f'font-weight: 750; color: {accent}; font-size: 15px;')
        self.category_badge.setText(name)
        self.category_badge.setStyleSheet(
            f'color: {accent}; background: {pale}; border: 1px solid {pale};'
            'border-radius: 9px; font-weight: 750; padding: 5px 11px;'
        )
        self.category_badge.setVisible(True)
