"""Test safety of the additive v16 installation."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from unittest.mock import patch

# The v16 installer is an independently distributed historical ZIP, not a
# runtime module in the current shared Test Lab source tree.
try:
    import install_v16
except ModuleNotFoundError as exc:
    if exc.name != 'install_v16':
        raise
    install_v16 = None

if install_v16 is not None:
    from install_v16 import BASELINE_SHA256, PREREQUISITES, install
else:
    BASELINE_SHA256, PREREQUISITES, install = {}, (), None


@unittest.skipUnless(install_v16 is not None, '旧v16インストーラーは別配布ZIPのため対象外')
class TestV16Installer(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'INO-module-lab'
        self.target = self.root / 'tools' / 'module_test_lab'
        self.target.mkdir(parents=True)
        # Isolated temporary fixture: never depends on the developer machine.
        source = b'baseline-v15-app.py test fixture\n'
        (self.target / 'app.py').write_bytes(source)
        self.mock_hash = patch.object(install_v16, 'BASELINE_SHA256', {'app.py': hashlib.sha256(source).hexdigest()})
        self.mock_hash.start()
        self.addCleanup(self.mock_hash.stop)
        for name in PREREQUISITES:
            if name != 'app.py': (self.target / name).write_text('stub', encoding='utf-8')
        self.backup = Path(self.temp.name) / 'backups'

    def test_dry_run_and_idempotent(self):
        self.assertIsNone(install(self.root, True, backup_root=self.backup))
        self.assertEqual(list(self.backup.glob('*')), [])
        before = (self.target / 'app.py').read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(), install_v16.BASELINE_SHA256['app.py'])
        dest = install(self.root, False, backup_root=self.backup)
        self.assertTrue((dest / 'manifest.json').is_file())
        self.assertTrue((self.target / 'v16_experiment_core.py').is_file())
        self.assertTrue((self.target / 'v16_experiment_tab.py').is_file())
        self.assertIsNone(install(self.root, False, backup_root=self.backup))
        self.assertEqual(len(list(self.backup.glob('*'))), 1)

    def test_protect_custom_source(self):
        (self.target / 'app.py').write_text('modified by user', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, '独自変更'):
            install(self.root, backup_root=self.backup)
        self.assertFalse((self.target / 'v16_experiment_core.py').exists())

    def test_protect_existing_new_file(self):
        (self.target / 'v16_experiment_tab.py').write_text('custom file', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, '同名'):
            install(self.root, backup_root=self.backup)


if __name__ == '__main__': unittest.main()
