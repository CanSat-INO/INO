"""Installer regression tests; no writes to actual user folders."""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

MODULE_DIR = Path(__file__).resolve().parents[1]
INSTALL_DIR = MODULE_DIR.parents[1].parent
if (INSTALL_DIR / 'install_v18.py').is_file():
    sys.path.insert(0, str(INSTALL_DIR))
    from install_v18 import install, files_to_install
else:
    install = files_to_install = None


@unittest.skipIf(install is None, '配布ZIP内でのみインストーラーテストを実施')
class InstallerTests(unittest.TestCase):
    def create_fake_previous_repo(self, base):
        module = base / 'tools' / 'module_test_lab'
        module.mkdir(parents=True)
        for name in ('records.py', 'module_navigation.py', 'v14_1_logic_tab.py',
                     'v15_sensor_core.py', 'v15_sensor_tab.py',
                     'navigation_search_v13_5.py', 'v16_experiment_core.py',
                     'v16_experiment_tab.py', 'launch_v13_4.sh',
                     'v17_phase_core.py', 'v17_phase_tab.py'):
            (module / name).write_text('# previous installed\n')
        (module / 'app.py').write_bytes(
            (INSTALL_DIR / 'v17_app_fixture.py').read_bytes()
            if (INSTALL_DIR / 'v17_app_fixture.py').is_file()
            else (MODULE_DIR / 'app.py').read_bytes())
        return module

    def test_payload_coverage(self):
        names = {p.name for p in files_to_install()}
        for required in ('app.py', 'v18_bus_core.py', 'v18_bus_tab.py',
                         'README_V18_VIRTUAL_BUS_JA.md', 'test_v18_bus_core.py'):
            self.assertIn(required, names)

    def test_missing_previous_version(self):
        with tempfile.TemporaryDirectory() as td:
            module = self.create_fake_previous_repo(Path(td) / 'repo')
            (module / 'v17_phase_core.py').unlink()
            with self.assertRaises(RuntimeError):
                install(Path(td) / 'repo', dry_run=True)

    def test_custom_source_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            module = self.create_fake_previous_repo(Path(td) / 'repo')
            (module / 'app.py').write_text('# local edits\n')
            with self.assertRaises(RuntimeError):
                install(Path(td) / 'repo', dry_run=True)
            self.assertEqual((module / 'app.py').read_text(), '# local edits\n')

    def test_dry_run_install_and_repeat(self):
        if not (INSTALL_DIR / 'v17_app_fixture.py').is_file():
            self.skipTest('v17基準ソースは配布ZIPには含めません')
        with tempfile.TemporaryDirectory() as td:
            module = self.create_fake_previous_repo(Path(td) / 'repo')
            self.assertIsNone(install(Path(td) / 'repo', dry_run=True))
            self.assertFalse((module / 'v18_bus_core.py').exists())
            backup = install(Path(td) / 'repo', backup_root=Path(td) / 'backups')
            self.assertTrue(backup.is_dir())
            self.assertTrue((module / 'v18_bus_tab.py').exists())
            self.assertIn('build_v18_bus_tab', (module / 'app.py').read_text())
            self.assertTrue((backup / 'manifest.json').exists())
            self.assertIsNone(install(Path(td) / 'repo', backup_root=Path(td) / 'backups'))


if __name__ == '__main__':
    unittest.main()
