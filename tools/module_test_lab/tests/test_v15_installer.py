"""v15 installer tests run only in source packaging context with install_v15.py."""
from pathlib import Path
import importlib.util
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / 'install_v15.py'
BASELINE = ROOT / '_base_v14_1'


class InstallerSafetyTests(unittest.TestCase):
    def setUp(self):
        if not INSTALLER.is_file() or not BASELINE.is_dir():
            self.skipTest('Only exercised during release packaging')
        spec = importlib.util.spec_from_file_location('install_v15_testing', INSTALLER)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / 'repo'
        self.target = self.repo / 'tools' / 'module_test_lab'
        self.target.mkdir(parents=True)
        for name in self.module.PREREQUISITES:
            source = BASELINE / name
            self.assertTrue(source.is_file(), name)
            shutil.copy2(source, self.target / name)
        self.backups = Path(self.tmp.name) / 'backups'

    def test_dryrun_apply_idempotent_and_restore_copy(self):
        before = (self.target / 'app.py').read_bytes()
        self.assertIsNone(self.module.install(self.repo, True, backup_root=self.backups))
        self.assertEqual((self.target / 'app.py').read_bytes(), before)
        self.assertFalse((self.target / 'v15_sensor_core.py').exists())
        path = self.module.install(self.repo, False, backup_root=self.backups)
        self.assertIsNotNone(path)
        self.assertNotEqual((self.target / 'app.py').read_bytes(), before)
        self.assertTrue((self.target / 'v15_sensor_core.py').exists())
        self.assertEqual(len(list(self.backups.iterdir())), 1)
        self.assertIsNone(self.module.install(self.repo, False, backup_root=self.backups))
        self.assertEqual(len(list(self.backups.iterdir())), 1)
        self.assertTrue(any(p.read_bytes() == before for p in path.glob('old_*.bak')))

    def test_protect_customized_existing_file(self):
        (self.target / 'app.py').write_text('# user modifications', encoding='utf8')
        with self.assertRaisesRegex(RuntimeError, '独自変更'):
            self.module.install(self.repo, False, backup_root=self.backups)
        self.assertFalse((self.target / 'v15_sensor_core.py').exists())
        self.assertFalse(self.backups.exists())

    def test_preserve_ime_and_existing_content(self):
        (self.target / 'launcher_note.txt').write_text('keep')
        self.module.install(self.repo, False, backup_root=self.backups)
        self.assertEqual((self.target / 'launcher_note.txt').read_text(), 'keep')
        self.assertEqual((self.target / 'launch_v13_4.sh').read_bytes(), (BASELINE / 'launch_v13_4.sh').read_bytes())
