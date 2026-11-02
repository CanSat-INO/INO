"""Safe patch checks without touching the user's actual repository."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import sys

MODULE_DIR = Path(__file__).resolve().parents[1]
INSTALL_DIR = MODULE_DIR.parents[1].parent
if (INSTALL_DIR / 'install_v17.py').is_file():
    sys.path.insert(0, str(INSTALL_DIR))
    from install_v17 import install, files_to_install
else:
    install = files_to_install = None


@unittest.skipIf(install is None, 'インストーラーは配布ZIP展開フォルダ側にあります')
class InstallerTests(unittest.TestCase):
    def make_repo(self, root):
        target = Path(root) / 'tools' / 'module_test_lab'
        target.mkdir(parents=True)
        # Fill prerequisite files. Real v16 app content for baseline SHA.
        for name in ('records.py', 'module_navigation.py', 'v14_1_logic_tab.py',
                     'v15_sensor_core.py', 'v15_sensor_tab.py',
                     'navigation_search_v13_5.py', 'launch_v13_4.sh',
                     'v16_experiment_core.py', 'v16_experiment_tab.py'):
            (target / name).write_text('# baseline\n')
        return target

    def test_dry_run_does_not_touch_files(self):
        with tempfile.TemporaryDirectory() as temp:
            target = self.make_repo(Path(temp) / 'repo')
            (target / 'app.py').write_text('# custom\n')
            with self.assertRaises(RuntimeError):
                install(Path(temp) / 'repo', dry_run=True)
            self.assertFalse((target / 'v17_phase_core.py').exists())

    def test_new_payload_files_exist(self):
        names = [p.name for p in files_to_install()]
        for name in ('app.py', 'v17_phase_core.py', 'v17_phase_tab.py',
                     'README_V17_PHASE_SIM_JA.md', 'test_v17_phase_core.py'):
            self.assertIn(name, names)

    def test_cannot_install_without_v16(self):
        with tempfile.TemporaryDirectory() as temp:
            target = self.make_repo(Path(temp) / 'repo')
            (target / 'app.py').write_text('# not baseline\n')
            (target / 'v16_experiment_tab.py').unlink()
            with self.assertRaises(RuntimeError):
                install(Path(temp) / 'repo', dry_run=True)

    def test_install_repeat_and_backup(self):
        # v16 app bytes are saved in the packaged historic v16 patch.
        from zipfile import ZipFile
        history = Path('/mnt/data/cansat_module_test_lab_v16_experiment_journal_installer.zip')
        if not history.is_file():
            self.skipTest('historic v16 source zip not available (works after deployment)')
        with tempfile.TemporaryDirectory() as temp:
            target = self.make_repo(Path(temp) / 'repo')
            with ZipFile(history) as z:
                baseline = z.read('payload/tools/module_test_lab/app.py')
            (target / 'app.py').write_bytes(baseline)
            backup = install(Path(temp) / 'repo', backup_root=Path(temp) / 'backup')
            self.assertTrue(backup.is_dir())
            self.assertTrue((target / 'v17_phase_tab.py').is_file())
            self.assertIn('build_v17_phase_tab', (target / 'app.py').read_text())
            self.assertIsNone(install(Path(temp) / 'repo', backup_root=Path(temp) / 'backup'))
            self.assertIn('manifest', '\n'.join(p.name for p in backup.iterdir()))


if __name__ == '__main__':
    unittest.main()
