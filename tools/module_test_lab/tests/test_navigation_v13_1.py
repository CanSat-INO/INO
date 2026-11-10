"""Regression checks for v13.1 navigation, style, and Japanese input."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from gui_theme_v13 import CATEGORIES, category_for


class NavigationV131StaticTests(unittest.TestCase):
    def test_palette_is_high_contrast_on_white(self):
        # WCAG relative contrast against the white cards: >=4.5 for category text.
        def luminance(hexa):
            nums = [int(hexa[i:i+2], 16)/255 for i in (1,3,5)]
            r,g,b = (c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in nums)
            return .2126*r + .7152*g + .0722*b
        for category, (_, accent, _, _) in CATEGORIES.items():
            if category not in ('landing','control','fault','results','simulation','guide'):
                continue
            contrast = (1.05)/(luminance(accent)+.05)
            with self.subTest(category=category):
                self.assertGreaterEqual(contrast, 4.5)

    def test_category_mapping_preserved(self):
        self.assertEqual(category_for('3モジュール・仮想CAN'), 'control')
        self.assertEqual(category_for('v12 実験管理・一括比較'), 'results')


try:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication, QPushButton
    from module_navigation import JapaneseSearchEdit, ModuleNavigation, NavigationTile
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication, 'PySide6未導入のためGUIテストをスキップ')
class NavigationV131GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.nav = ModuleNavigation()
        for name in ('着地検知シミュレーション', '3モジュール・仮想CAN',
                     'v12 実験管理・一括比較'):
            from PySide6.QtWidgets import QWidget
            self.nav.tabs.addTab(QWidget(), name)
        self.nav._initialize()

    def tearDown(self):
        self.nav.close()

    def test_japanese_filter_and_restore(self):
        self.nav.search.setText('着地')
        self.nav.rebuild_home()
        self.assertEqual(len(self.nav.scroll.widget().findChildren(
            NavigationTile, 'moduleNavigationTile0')), 1)
        self.nav.search.setText('')
        self.nav.rebuild_home()
        self.assertEqual(len(self.nav.scroll.widget().findChildren(
            NavigationTile)), 3)

    def test_ime_preedit_does_not_rebuild(self):
        from PySide6.QtGui import QInputMethodEvent
        old = self.nav.scroll.widget()
        self.nav.search.inputMethodEvent(QInputMethodEvent('にほん', []))
        self.assertTrue(self.nav.search.composing)
        self.nav._apply_search()
        self.assertIs(self.nav.scroll.widget(), old)
        self.nav._search_timer.stop()

    def test_chip_filters_without_typing(self):
        self.nav._toggle_category('制御・通信')
        self.assertEqual(self.nav.search.text(), '制御・通信')
        self.assertEqual(len(self.nav.scroll.widget().findChildren(
            NavigationTile)), 1)
        self.nav._toggle_category('制御・通信')
        self.assertEqual(self.nav.search.text(), '')


if __name__ == '__main__':
    unittest.main()
