"""IME-aware search and readable v13.5 module navigation.

The existing tab widgets remain unchanged. A short search debounce keeps a
Japanese input-method preedit from triggering a full menu rebuild every stroke.
"""
from __future__ import annotations
import re

from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QMenu, QPushButton, QScrollArea, QStackedWidget, QTabWidget, QSizePolicy,
    QVBoxLayout, QWidget,
)
from gui_theme_v13 import CATEGORIES, category_for
from navigation_feature_groups import (FEATURE_GROUPS, feature_group_for, feature_group_presentation)
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
            QFrame {{ background: #183149; border: 1px solid #DCE6F1;
                      border-left: 5px solid {accent}; border-radius: 10px; }}
            QFrame:hover {{ background: #24435F; border-color: #93B8ED;
                           border-left: 5px solid {accent}; }}
            QFrame:focus {{ background: #24435F; border: 2px solid #2A72DC;
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
            f'QLabel {{ color: #ADD8F0; font-size: 12px; font-weight: 700;'
            ' background: transparent; border: none; }'
        )
        category_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        info.addWidget(category_label)

        self.title_label = QLabel(self._title)
        self.title_label.setStyleSheet(
            'QLabel { color: #EDF6FF; font-size: 15px; font-weight: 700;'
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
            'QLabel { color: #A4C4E5; font-size: 23px; font-weight: 600;'
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


class CurrentPageTabs(QTabWidget):
    """Hidden-tab navigation sizes its frame from the visible page only.

    A stock QTabWidget takes the maximum hint of every page. With an outer
    scroll area, a large hidden legacy form can then push a self-scrolling
    workspace's header and actions offscreen.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.currentChanged.connect(lambda index: self.updateGeometry())

    def _page_hint(self, minimum):
        page = self.currentWidget()
        if page is None or not self.tabBar().isHidden():
            return super().minimumSizeHint() if minimum else super().sizeHint()
        hint = page.minimumSizeHint() if minimum else page.sizeHint()
        hint = hint.expandedTo(page.minimumSize())
        margins = self.contentsMargins()
        return QSize(hint.width() + margins.left() + margins.right() + 8,
                     hint.height() + margins.top() + margins.bottom() + 8)

    def minimumSizeHint(self):
        return self._page_hint(True)

    def sizeHint(self):
        return self._page_hint(False)


class ModuleNavigation(QWidget):
    """Keep the original QTabWidget/API, with a more legible home screen."""

    SEARCH_DELAY_MS = 350

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ready = False
        self._last_page = None
        self._active_feature_group = None
        self._card_columns = None
        self._card_reflow_pending = False
        self._home_render_signature = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.header_frame = QFrame(self)
        self.header_frame.setObjectName("moduleNavigationHeader")
        self.header_frame.setStyleSheet(
            "QFrame#moduleNavigationHeader {"
            " background-color: #101E30;"
            " border: 1px solid #37516B;"
            " border-radius: 10px;"
            "}"
        )
        bar = QHBoxLayout(self.header_frame)
        bar.setContentsMargins(10, 8, 10, 8)
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
            QPushButton { background: #162A40; color: #DFEAF5;
                border: 1px solid #37516B; border-radius: 9px;
                padding: 10px 16px; font-weight: 700; }
            QPushButton:hover { background: #223C59; }
        ''')
        self.page_title = QLabel('ホーム')
        self.page_title.setStyleSheet('font-weight: 700; color: #DCEBF7; font-size: 15px;')
        self.page_title.setMinimumWidth(0)
        self.page_title.setWordWrap(True)
        self.page_title.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Preferred
        )
        self.category_badge = QLabel('')
        self.category_badge.setVisible(False)
        bar.addWidget(self.menu_button)
        bar.addWidget(self.home_button)
        bar.addWidget(self.page_title, 1)
        bar.addWidget(self.category_badge)
        layout.addWidget(self.header_frame)

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
        subtitle.setWordWrap(True)
        home_layout.addWidget(subtitle)

        # v22: task-focused entry points; underlying screens stay untouched.
        guide_label = QLabel('まず何をしたいですか？ 目的を選ぶと対応する画面へ移動します。')
        guide_label.setObjectName('moduleNavigationV22Guide')
        guide_label.setStyleSheet('color: #254A75; font-size: 13px; font-weight: 700;')
        home_layout.addWidget(guide_label)
        quick_grid = QGridLayout()
        self._quick_grid = quick_grid
        self._quick_buttons = []
        self._quick_columns = None
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
            quick.setMinimumWidth(0)
            quick.setSizePolicy(
                QSizePolicy.Ignored,
                QSizePolicy.Preferred
            )
            quick.setStyleSheet("""
                QPushButton { background: #FFFFFF; border: 1px solid #BED2EA;
                    border-radius: 8px; padding: 8px 11px; text-align: left;
                    color: #163A65; font-size: 12px; font-weight: 650; }
                QPushButton:hover { background: #EAF3FF; border-color: #3B83DB; }
                QPushButton:focus { border: 2px solid #1765E8; }
            """)
            quick.setToolTip(f'{label}：{description}')
            quick.clicked.connect(lambda checked=False, name=target: self.open_named_tab(name))
            self._quick_buttons.append(quick)
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
        # 目的別の5カテゴリーと「すべて」
        category_grid = QGridLayout()
        category_grid.setHorizontalSpacing(8)
        category_grid.setVerticalSpacing(7)

        self._group_buttons = {}

        options = [("all", "すべて")]
        options.extend(
            (key, label)
            for key, label, _ in FEATURE_GROUPS
            if key not in ("other",)
        )

        for position, (key, label) in enumerate(options):
            chip = QPushButton(label)
            chip.setObjectName(
                "moduleNavigationFeatureGroup"
                + key.capitalize()
            )
            chip.setCheckable(True)
            chip.setMinimumHeight(34)
            chip.setStyleSheet("""
                QPushButton {
                    background: #142B42;
                    color: #DCEBF7;
                    border: 1px solid #45627D;
                    border-radius: 8px;
                    padding: 7px 10px;
                    font-weight: 650;
                }
                QPushButton:hover {
                    background: #20445F;
                    border-color: #7BDFF4;
                }
                QPushButton:checked {
                    background: #235875;
                    color: #FFFFFF;
                    border: 1px solid #7BDFF4;
                }
            """)
            chip.clicked.connect(
                lambda checked=False, group=key:
                self._select_feature_group(group)
            )
            self._group_buttons[key] = chip
            category_grid.addWidget(
                chip, position // 3, position % 3
            )

        self._refresh_feature_group_buttons()
        home_layout.addLayout(category_grid)

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
        self.scroll.setStyleSheet('QScrollArea { background: #0B1B2D; border: none; }')
        self.scroll.viewport().setStyleSheet('background: #0B1B2D;')
        self.scroll.viewport().installEventFilter(self)
        home_layout.addWidget(self.scroll, 1)
        self.stack.addWidget(self.home)

        self.tabs = CurrentPageTabs()
        self.tabs.tabBar().hide()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.stack.addWidget(self.tabs)
        layout.addWidget(self.stack, 1)
        self.stack.setCurrentWidget(self.home)
        QTimer.singleShot(0, self._initialize)

    @staticmethod
    def quick_column_count(width):
        if width >= 700:
            return 2
        return 1

    def _reflow_quick_actions(self):
        if not getattr(self, "_ready", False):
            return

        columns = self.quick_column_count(self.width())

        if columns == self._quick_columns:
            return

        self._quick_columns = columns

        # ボタン自体は作り直さず、位置だけ変更する
        for button in self._quick_buttons:
            self._quick_grid.removeWidget(button)

        for i, button in enumerate(self._quick_buttons):
            self._quick_grid.addWidget(
                button,
                i // columns,
                i % columns
            )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_ready", False):
            self._reflow_quick_actions()
            self._schedule_card_reflow()

    def eventFilter(self, watched, event):
        from PySide6.QtCore import QEvent

        if (
            getattr(self, "_ready", False)
            and hasattr(self, "scroll")
            and watched is self.scroll.viewport()
            and event.type() == QEvent.Resize
        ):
            self._schedule_card_reflow()

        return super().eventFilter(watched, event)

    def _initialize(self):
        self._ready = True
        self._reflow_quick_actions()
        self.rebuild_home()
        self.show_home()
        self._schedule_card_reflow()

    def _items(self):
        return [(i, self.tabs.tabText(i)) for i in range(self.tabs.count())]

    def _refresh_feature_group_buttons(self):
        active = self._active_feature_group or "all"
        for key, button in self._group_buttons.items():
            button.setChecked(key == active)

    def _select_feature_group(self, group):
        if group == "all" or group == self._active_feature_group:
            self._active_feature_group = None
        else:
            self._active_feature_group = group

        self._refresh_feature_group_buttons()
        self.rebuild_home()

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
        category_title, accent, pale, hint = feature_group_presentation(title)
        # QFrame-based card: avoids QPushButton QSS clipping in WSL/X11.
        tile = NavigationTile(self._display_title(title), category_title, accent, pale,
                              ITEM_ICONS.get(title, '◈'))
        tile.setObjectName(f'moduleNavigationTile{tab_index}')
        tile.setToolTip(f'{self._display_title(title)}：{hint}')
        tile.clicked.connect(lambda checked=False, i=tab_index: self.open_tab(i))
        return tile

    @staticmethod
    def feature_column_count(width):
        return 1 if width < 720 else 2

    def _schedule_card_reflow(self):
        if self._card_reflow_pending:
            return
        self._card_reflow_pending = True
        QTimer.singleShot(0, self._reflow_feature_cards)

    def _reflow_feature_cards(self):
        self._card_reflow_pending = False
        if not getattr(self, "_ready", False):
            return
        if self.search.composing:
            return
        columns = self.feature_column_count(
            self.scroll.viewport().width()
        )
        if columns != self._card_columns:
            self.rebuild_home()

    def rebuild_home(self, *_):
        if not self._ready:
            return

        columns = self.feature_column_count(
            self.scroll.viewport().width()
        )
        signature = (
            columns,
            tuple(self._items()),
            self.search.text(),
            self._active_feature_group,
        )

        if (signature == self._home_render_signature
                and self.scroll.widget() is not None):
            return

        self._card_columns = columns

        container = QWidget()
        container.setObjectName('moduleNavigationGridContainer')
        container.setStyleSheet(
            'QWidget#moduleNavigationGridContainer { background-color: #0B1B2D; }'
        )
        grid = QGridLayout(container)
        grid.setContentsMargins(4, 10, 4, 14)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(11)

        query = self.search.text()

        matched = [
            (i, name)
            for i, name in self._items()
            if matches_search(name, CATEGORIES[category_for(name)][0], query)
        ]

        if self._active_feature_group is not None:
            matched = [
                (i, name)
                for i, name in matched
                if feature_group_for(name)
                == self._active_feature_group
            ]

        grouped = {
            key: [] for key, _, _ in FEATURE_GROUPS
        }

        for tab_index, title in matched:
            key = feature_group_for(title)
            grouped[key].append((tab_index, title))

        row = 0
        header_count = 0
        tile_row_count = 0

        for key, label, hint in FEATURE_GROUPS:
            items = grouped[key]
            if not items:
                continue

            heading = QLabel(
                f"{label}（{len(items)}件）"
            )
            heading.setObjectName(
                "moduleNavigationGroup" + key.capitalize()
            )
            heading.setToolTip(hint)
            heading.setStyleSheet(
                "font-size: 15px; "
                "font-weight: 750; "
                "color: #E2EFFB; "
                "padding: 5px 3px;"
            )

            grid.addWidget(heading, row, 0, 1, columns)
            grid.setRowMinimumHeight(row, 34)

            row += 1
            header_count += 1

            for position, (tab_index, title) in enumerate(items):
                tile_row = row + position // columns
                tile_col = position % columns
                grid.addWidget(
                    self._make_tile(tab_index, title),
                    tile_row,
                    tile_col
                )

            rows_for_group = (len(items) + columns - 1) // columns

            grid.setRowMinimumHeight(row, NavigationTile.HEIGHT)
            for r in range(row + 1, row + rows_for_group):
                grid.setRowMinimumHeight(r, NavigationTile.HEIGHT)

            row += rows_for_group
            tile_row_count += rows_for_group

        if not matched:
            empty = QLabel(
                "一致する機能がありません。"
                "別のキーワードを入力してください。"
            )
            empty.setStyleSheet("padding: 20px;")
            grid.addWidget(empty, 0, 0, 1, columns)

        grid.setColumnStretch(0, 1)
        if columns == 2:
            grid.setColumnStretch(1, 1)

        minimum = (
            24
            + header_count * 34
            + tile_row_count * NavigationTile.HEIGHT
            + max(0, row - 1) * 11
        )

        container.setMinimumHeight(max(80, minimum))
        container.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.MinimumExpanding
        )
        grid.setRowStretch(row, 1)

        prior = self.scroll.takeWidget()
        self.scroll.setWidget(container)
        self._home_render_signature = signature

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
        self.stack.setCurrentWidget(getattr(self, "tabs_page", self.tabs))
        self._last_page = index
        self._update_header(index)

    def show_home(self):
        if hasattr(self, "project_home"):
            self.project_home.refresh()
            self.stack.setCurrentWidget(self.project_home)
            self.page_title.setText("プロジェクト概要")
            self.page_title.setStyleSheet("color: #DCEBF7; font-weight: 600;")
            self.category_badge.setVisible(False)
            return
        # Navigation and filtering must not disturb native IME composition.
        if not self.search.composing:
            self.rebuild_home()
        self.stack.setCurrentWidget(self.home)
        self.page_title.setText('ホーム')
        self.page_title.setStyleSheet('font-weight: 700; color: #DCEBF7; font-size: 15px;')
        self.category_badge.setVisible(False)

    def show_all_features(self):
        self.rebuild_home()
        self.stack.setCurrentWidget(self.home)
        self.page_title.setText("すべての機能")
        self.category_badge.setVisible(False)

    def show_menu(self):
        menu = QMenu(self)
        action = menu.addAction('⌂  ホーム')
        action.triggered.connect(self.show_home)
        action = menu.addAction("すべての機能・検索")
        action.triggered.connect(self.show_all_features)
        menu.addSeparator()
        for i, title in self._items():
            action = menu.addAction(self._display_title(title))
            action.triggered.connect(lambda checked=False, index=i: self.open_tab(index))
        menu.exec(self.menu_button.mapToGlobal(self.menu_button.rect().bottomLeft()))

    def _on_tab_changed(self, index):
        if self.stack.currentWidget() is getattr(self, "tabs_page", self.tabs) and index >= 0:
            self._update_header(index)

    def _update_header(self, index):
        title = self.tabs.tabText(index)
        name, accent, pale, _ = feature_group_presentation(title)
        if hasattr(self, "project_home"):
            accent, pale = "#7BDFF4", "#112A40"
        self.page_title.setText(self._display_title(title))
        self.page_title.setStyleSheet(f'font-weight: 750; color: {accent}; font-size: 15px;')
        self.category_badge.setText(name)
        self.category_badge.setStyleSheet(
            f'color: {accent}; background: {pale}; border: 1px solid {pale};'
            'border-radius: 9px; font-weight: 750; padding: 5px 11px;'
        )
        self.category_badge.setVisible(True)
