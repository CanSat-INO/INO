"""v13.5: UI-independent keyword search and safe installer regression tests."""
from __future__ import annotations

import importlib.util
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = ROOT.parents[2]  # build root when in installer payload
sys.path.insert(0, str(ROOT))
from navigation_search_v13_5 import ALIASES, matches_search

TABS = (
    '着地検知シミュレーション', '実験記録・チーム共有', '結果ダッシュボード',
    'Arduino/CSVログ解析', 'C++着地判定', '着地一括テスト', '着地コード比較',
    '着地パラメータ探索', '3モジュール・仮想CAN', 'C++モジュール連携',
    '異常分析', '統合実験結果', 'Main・CAM・Drive C++個別試験',
    'シミュレーション共通基盤', 'v12 実験管理・一括比較', '使い方・Arduinoとの接続',
)


def search(query):
    return [title for title in TABS if matches_search(title, '着地・解析' if '着地' in title else 'その他', query)]


class KeywordSearchTests(unittest.TestCase):
    def test_aliases_only_known_pages(self):
        self.assertEqual(set(TABS), set(ALIASES))

    def test_blank_query_matches_all(self):
        self.assertEqual(list(TABS), search(' 　'))

    def test_global_cansat_japanese_and_english(self):
        for query in ('CanSat', 'ＣａｎＳａｔ', 'cansat', 'キャンサット', 'カンサット'):
            with self.subTest(query=query):
                self.assertEqual(list(TABS), search(query))

    def test_gps_maps_only_recording_tab(self):
        self.assertEqual(['実験記録・チーム共有'], search('GPS'))
        self.assertEqual(search('GPS'), search('gnss'))
        self.assertEqual(search('GPS'), search('衛星測位'))

    def test_imu_and_sensor(self):
        self.assertIn('着地検知シミュレーション', search('IMU'))
        self.assertIn('Arduino/CSVログ解析', search('IMU'))
        self.assertIn('着地検知シミュレーション', search('センサー'))
        self.assertNotIn('3モジュール・仮想CAN', search('センサー'))
        self.assertIn('着地検知シミュレーション', search('BNO055'))

    def test_legacy_words_preserved(self):
        for term, tab in [('着地', '着地検知シミュレーション'),
                          ('can', '3モジュール・仮想CAN'),
                          ('c++', 'C++着地判定'),
                          ('異常', '異常分析')]:
            self.assertIn(tab, search(term))

    def test_japanese_english_combined(self):
        self.assertIn('着地検知シミュレーション', search('着地CanSat'))
        self.assertIn('着地検知シミュレーション', search('着地 cansat'))
        self.assertEqual(['実験記録・チーム共有'], search('gps cansat'))
        self.assertEqual([], search('gps imu'))

    def test_category_name_without_alias(self):
        self.assertTrue(matches_search('Foo', '制御・通信', '制御'))
        self.assertFalse(matches_search('Foo', '制御・通信', '着地'))
        self.assertTrue(matches_search('Foo', '制御・通信', 'cansat'))

    def test_no_accidental_nonsense_results(self):
        self.assertEqual([], search('somethingunrelated'))
        self.assertEqual([], search('マイナス123XYZ'))

    def test_ime_and_gui_code_kept(self):
        src = (ROOT / 'module_navigation.py').read_text(encoding='utf-8')
        self.assertIn('compositionFinished.connect(self._queue_search)', src)
        self.assertIn('if self.search.composing:', src)
        self.assertIn('class NavigationTile(QFrame)', src)
        self.assertIn('self.setFixedHeight(self.HEIGHT)', src)
        self.assertIn('matches_search(name,', src)
        self.assertNotIn('QT_IM_MODULE=', src)


class InstallerTests(unittest.TestCase):
    """Creates disposable home/repo tree without touching the actual user repo."""
    def test_safe_install_dryrun_idempotence_and_backup(self):
        # During installed runs the installer isn't beside this test; get the
        # source installer from the ZIP build test context only.
        installer = ROOT.parents[2] / 'install_v13_5.py'
        if not installer.is_file():
            self.skipTest('インストーラー本体は単体ZIPで配布')
        original = ROOT.parents[2] / '_original_navigation_v13_3.py'
        if not original.is_file():
            self.skipTest('元版ファイルはビルド専用')
        spec = importlib.util.spec_from_file_location('install_v13_5', installer)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as d:
            home = pathlib.Path(d) / 'home'
            home.mkdir()
            repo = pathlib.Path(d) / 'repo'
            target = repo / 'tools' / 'module_test_lab'
            target.mkdir(parents=True)
            (target / 'app.py').write_text('original app')
            (target / 'launch_v13_4.sh').write_text('original launcher')
            shutil.copy2(original, target / 'module_navigation.py')
            oldapp = (target / 'app.py').read_bytes()
            oldlaunch = (target / 'launch_v13_4.sh').read_bytes()
            oldnav = (target / 'module_navigation.py').read_bytes()
            from unittest.mock import patch
            with patch.object(module.Path, 'home', return_value=home):
                module.install(repo, True)
                self.assertEqual(oldnav, (target / 'module_navigation.py').read_bytes())
                module.install(repo, False)
                self.assertNotEqual(oldnav, (target / 'module_navigation.py').read_bytes())
                self.assertTrue((target / 'navigation_search_v13_5.py').exists())
                self.assertEqual(oldapp, (target / 'app.py').read_bytes())
                self.assertEqual(oldlaunch, (target / 'launch_v13_4.sh').read_bytes())
                module.install(repo, False)
                backups = list((home / 'cansat_v13_5_backups').glob('*/manifest.json'))
                self.assertEqual(1, len(backups))
                self.assertIn(b'module_navigation.py', backups[0].read_bytes())

    def test_refuse_unknown_modified_navigation(self):
        installer = ROOT.parents[2] / 'install_v13_5.py'
        if not installer.is_file():
            self.skipTest('インストーラー本体は単体ZIPで配布')
        spec = importlib.util.spec_from_file_location('install_v13_5_test', installer)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as d:
            repo = pathlib.Path(d) / 'repo'
            target = repo / 'tools' / 'module_test_lab'
            target.mkdir(parents=True)
            for name in ['app.py', 'launch_v13_4.sh', 'module_navigation.py']:
                (target / name).write_text('user custom')
            with self.assertRaisesRegex(RuntimeError, '保護するため停止'):
                module.install(repo, False)
            self.assertEqual('user custom', (target / 'module_navigation.py').read_text())


if __name__ == '__main__':
    unittest.main()
