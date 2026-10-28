"""Regression tests for current fixed-height QFrame navigation cards."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TileV132SourceChecks(unittest.TestCase):
    def test_tile_uses_qframe_with_explicit_layout(self):
        source = (ROOT / 'module_navigation.py').read_text(encoding='utf-8')
        self.assertIn('class NavigationTile(QFrame)', source)
        self.assertIn('line = QHBoxLayout(self)', source)
        self.assertIn('self.setFixedHeight(self.HEIGHT)', source)
        self.assertNotIn('line = QHBoxLayout(button)', source)
        self.assertNotIn('QGraphicsDropShadowEffect(button)', source)

    def test_scroll_content_has_explicit_minimum_height(self):
        source = (ROOT / 'module_navigation.py').read_text(encoding='utf-8')
        self.assertIn('container.setMinimumHeight(max(80, minimum))', source)


try:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QInputMethodEvent
    from PySide6.QtWidgets import QApplication, QPushButton, QWidget
    from PySide6.QtTest import QTest
    from module_navigation import ModuleNavigation, NavigationTile
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication is not None, 'PySide6未導入：実画面の動作テストはWSLで実施')
class TileV132QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.nav = ModuleNavigation()
        self.names = [
            '着地検知シミュレーション', '3モジュール・仮想CAN',
            'v12 実験管理・一括比較', '使い方・Arduinoとの接続',
        ]
        for title in self.names:
            self.nav.tabs.addTab(QWidget(), title)
        self.nav._initialize()
        self.nav.resize(1000, 750)
        self.nav.show()
        self.app.processEvents()

    def tearDown(self):
        self.nav.close()
        self.app.processEvents()

    def test_fixed_card_height(self):
        cards = self.nav.scroll.widget().findChildren(NavigationTile)
        self.assertEqual(len(cards), 4)
        for card in cards:
            self.assertEqual(card.height(), NavigationTile.HEIGHT)
            self.assertEqual(card.minimumHeight(), card.maximumHeight())
            self.assertTrue(card.findChildren(QWidget), 'QFrameカード内のラベルが存在すること')

    def test_click_navigates_legacy_tab(self):
        card = self.nav.scroll.widget().findChildren(
            NavigationTile, 'moduleNavigationTile1')[0]
        QTest.mouseClick(card, Qt.LeftButton)
        self.assertEqual(self.nav.tabs.currentIndex(), 1)
        self.assertIs(self.nav.stack.currentWidget(), self.nav.tabs)

    def test_ime_preedit_does_not_replace_scroll_widget(self):
        old = self.nav.scroll.widget()
        self.nav.search.inputMethodEvent(QInputMethodEvent('ちゃくち', []))
        self.assertTrue(self.nav.search.composing)
        self.nav._apply_search()
        self.assertIs(self.nav.scroll.widget(), old)
        self.nav._search_timer.stop()

    def test_category_filter_and_height(self):
        self.nav.search.setText('着地')
        self.nav.rebuild_home()
        self.assertEqual(len(self.nav.scroll.widget().findChildren(NavigationTile)), 1)
        self.assertGreaterEqual(self.nav.scroll.widget().minimumHeight(), 80)


if __name__ == '__main__':
    unittest.main()
