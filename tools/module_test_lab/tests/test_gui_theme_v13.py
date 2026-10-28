"""V13 non-GUI checks; run without installing Qt on the test host."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gui_theme_v13 import CATEGORIES, MAIN_STYLESHEET, category_for, button_role


class ThemeV13Tests(unittest.TestCase):
    def test_all_categories_have_valid_tokens(self):
        for name, (label, accent, pale, hint) in CATEGORIES.items():
            with self.subTest(name=name):
                self.assertTrue(label)
                self.assertRegex(accent, r'^#[0-9A-Fa-f]{6}$')
                self.assertRegex(pale, r'^#[0-9A-Fa-f]{6}$')
                self.assertTrue(hint)

    def test_main_controls_are_blue(self):
        self.assertEqual(category_for('Main・CAM・Drive C++個別試験'), 'control')

    def test_network_is_blue(self):
        self.assertEqual(category_for('3モジュール・仮想CAN'), 'control')

    def test_camera_is_purple(self):
        self.assertEqual(category_for('カメラ解析'), 'camera')

    def test_drive_is_green(self):
        self.assertEqual(category_for('Drive 単体試験'), 'drive')

    def test_error_is_amber(self):
        self.assertEqual(category_for('異常分析'), 'fault')

    def test_results_category(self):
        self.assertEqual(category_for('v12 実験管理・一括比較'), 'results')

    def test_common_category(self):
        self.assertEqual(category_for('シミュレーション共通基盤'), 'simulation')

    def test_guide_category(self):
        self.assertEqual(category_for('使い方・Arduinoとの接続'), 'guide')

    def test_landing_category(self):
        self.assertEqual(category_for('着地検知シミュレーション'), 'landing')

    def test_run_primary(self):
        self.assertEqual(button_role('▶ 一括実行・履歴保存'), 'primary')

    def test_save_success(self):
        self.assertEqual(button_role('比較CSV出力'), 'success')

    def test_clear_danger(self):
        self.assertEqual(button_role('条件を全消去'), 'danger')

    def test_navigation_neutral(self):
        self.assertEqual(button_role('共通設定を開く'), 'neutral')

    def test_style_contains_selection_contrast(self):
        self.assertIn('selection-background-color: #C8E1FF', MAIN_STYLESHEET)
        self.assertIn('selection-color: #12294A', MAIN_STYLESHEET)

    def test_disabled_button_color(self):
        self.assertIn('QPushButton[v13Role="primary"]:disabled', MAIN_STYLESHEET)
        self.assertIn('QPushButton[v13Role="success"]:disabled', MAIN_STYLESHEET)

    def test_no_color_only_decisions(self):
        self.assertEqual(button_role('削除'), 'danger')
        self.assertEqual(button_role('実行'), 'primary')


if __name__ == '__main__':
    unittest.main()
