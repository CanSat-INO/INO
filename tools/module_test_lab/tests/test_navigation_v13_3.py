"""v13.3 independent GUI layout and IME regression tests."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

class NavigationV133SourceTests(unittest.TestCase):
    def test_qframe_card_and_minimum_rows(self):
        s = (ROOT / 'module_navigation.py').read_text(encoding='utf-8')
        self.assertIn('class NavigationTile(QFrame)', s)
        self.assertIn('self.setFixedHeight(self.HEIGHT)', s)
        self.assertIn('grid.setRowMinimumHeight(row, NavigationTile.HEIGHT)', s)
        self.assertIn('self.title_label = QLabel(self._title)', s)
        self.assertNotIn('def paintEvent(self, event):', s)
        self.assertNotIn('QHBoxLayout(button)', s)

    def test_ime_launcher_is_present_and_safe(self):
        s = (ROOT / 'launch_v13_3.sh').read_text(encoding='utf-8')
        self.assertIn('QT_IM_MODULE=fcitx', s)
        self.assertIn('--diagnose', s)
        self.assertNotIn('sudo apt', s)

try:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QInputMethodEvent
    from PySide6.QtWidgets import QApplication, QFrame, QWidget
    from PySide6.QtTest import QTest
    from module_navigation import ModuleNavigation, NavigationTile
except ImportError:
    QApplication = None

@unittest.skipUnless(QApplication is not None, 'PySide6なし: GUIの実測テスト省略')
class NavigationV133QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.nav = ModuleNavigation()
        for title in ['着地検知シミュレーション', '3モジュール・仮想CAN',
                      'v12 実験管理・一括比較', '使い方・Arduinoとの接続']:
            self.nav.tabs.addTab(QWidget(), title)
        self.nav._initialize()
        self.nav.resize(1030, 750)
        self.nav.show()
        self.app.processEvents()

    def tearDown(self):
        self.nav.close()
        self.app.processEvents()

    def test_card_geometry_and_children(self):
        cards = self.nav.scroll.widget().findChildren(NavigationTile)
        self.assertEqual(4, len(cards))
        for card in cards:
            self.assertIsInstance(card, QFrame)
            self.assertEqual(NavigationTile.HEIGHT, card.height())
            self.assertGreater(card.title_label.height(), 0)
            self.assertEqual(card.maximumHeight(), card.minimumHeight())

    def test_navigation_click(self):
        self.nav.scroll.widget().findChildren(NavigationTile)[1].clicked.emit()
        self.assertEqual(1, self.nav.tabs.currentIndex())

    def test_search_input_composition_does_not_rebuild(self):
        before = self.nav.scroll.widget()
        self.nav.search.inputMethodEvent(QInputMethodEvent('ちゃくち', []))
        self.nav._apply_search()
        self.assertIs(before, self.nav.scroll.widget())
        self.nav._search_timer.stop()

    def test_search_filter(self):
        self.nav.search.setText('着地')
        self.nav.rebuild_home()
        self.assertEqual(1, len(self.nav.scroll.widget().findChildren(NavigationTile)))

if __name__ == '__main__':
    unittest.main()
