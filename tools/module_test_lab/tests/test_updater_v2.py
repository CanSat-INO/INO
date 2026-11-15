"""Offline regression tests for the v2 updater; never touch the real HOME."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

DIST = Path(__file__).resolve().parents[1] / 'distribution'
sys.path.insert(0, str(DIST))
import cansat_bootstrap as boot
import cansat_update as updater
import install_client
import publish_release


class UpdaterV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cansat-v2-tests-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'member'
        self.home.mkdir()
        self.root = self.home / '.local/share/cansat-lab'
        self.root.mkdir(parents=True)
        (self.root / 'cansat_bootstrap.py').write_bytes((DIST / 'cansat_bootstrap.py').read_bytes())
        self.raw = (DIST / 'cansat_update.py').read_bytes()

    def test_stage_activate_and_select_versioned_client(self):
        a = updater.stage_client(self.root, self.raw)
        self.assertTrue(updater.activate_client(self.root, a))
        self.assertFalse(updater.activate_client(self.root, a))
        self.assertEqual(boot.choose(self.root), boot.version_path(self.root, a))
        b = updater.stage_client(self.root, self.raw + b'\n# upgrade\n')
        self.assertTrue(updater.activate_client(self.root, b))
        info = boot.read_state(self.root)
        self.assertEqual((info['current'], info['previous']), (b, a))
        self.assertEqual(boot.choose(self.root), boot.version_path(self.root, b))
        boot.rollback(self.root)
        self.assertEqual(boot.read_state(self.root)['current'], a)
        self.assertTrue((self.root / 'paused').exists())
        self.assertEqual(boot.choose(self.root), boot.version_path(self.root, a))

    def test_corruption_falls_back_without_executing(self):
        a = updater.stage_client(self.root, self.raw)
        updater.activate_client(self.root, a)
        b = updater.stage_client(self.root, self.raw + b'\n# upgrade\n')
        updater.activate_client(self.root, b)
        boot.version_path(self.root, b).write_bytes(b'corrupted')
        self.assertEqual(boot.choose(self.root), boot.version_path(self.root, a))
        with self.assertRaises(ValueError):
            updater.stage_client(self.root, self.raw + b'\n# upgrade\n')

    def test_reject_incompatible_updater_and_traversal(self):
        for raw in (b'UPDATER_PROTOCOL = 1\n', b'print("no contract")\n',
                    b'UPDATER_PROTOCOL = 2\ninvalid ???\n'):
            with self.assertRaises(ValueError):
                updater.stage_client(self.root, raw)
        with self.assertRaises(ValueError):
            boot.version_path(self.root, '../bad')
        boot.save_state(self.root, {'schema': 1, 'current': '../bad'})
        with self.assertRaises(ValueError):
            boot.read_state(self.root)

    def test_legacy_fallback(self):
        (self.root / 'cansat_update.py').write_bytes(self.raw)
        self.assertEqual(boot.choose(self.root), self.root / 'cansat_update.py')

    def test_release_client_update_preserves_legacy_format(self):
        folder = Path(self.temp.name) / 'release'
        app = folder / updater.APP
        app.mkdir(parents=True)
        for name in ('app.py', 'launch_v13_4.sh', 'project_store.py', 'project_hub.py'):
            (app / name).write_text('# test\n', encoding='utf-8')
        dest = app / 'distribution'
        dest.mkdir()
        (dest / 'cansat_update.py').write_bytes(self.raw)
        manifest = {'format': updater.FORMAT, 'data_format': 1, 'client_protocol': 1,
                    'files': updater.file_list(folder)}
        (folder / 'release.json').write_text(json.dumps(manifest), encoding='utf-8')
        self.assertEqual(updater.validate(folder)['client_protocol'], 1)
        self.assertTrue(updater.update_client_from_release(self.root, folder))
        self.assertFalse(updater.update_client_from_release(self.root, folder))
        (dest / 'cansat_update.py').write_text('UPDATER_PROTOCOL = 1\n')
        manifest['files'] = updater.file_list(folder)
        manifest['files'].pop('release.json', None)
        (folder / 'release.json').write_text(json.dumps(manifest))
        self.assertFalse(updater.update_client_from_release(self.root, folder))

    def test_install_uses_home_independent_launcher_and_backups(self):
        bin_dir = self.home / '.local/bin'
        bin_dir.mkdir(parents=True)
        launcher = bin_dir / 'cansat-lab'
        launcher.write_text('old launcher\n')
        def which(name):
            return None if name == 'cansat-lab' else '/usr/bin/' + name
        with patch.object(install_client.shutil, 'which', side_effect=which), \
             patch.object(install_client.subprocess, 'run'), \
             patch.object(updater, 'fetch', return_value='a' * 40):
            install_client.install(self.home, sys.executable, apply=False)
            self.assertEqual(launcher.read_text(), 'old launcher\n')
            install_client.install(self.home, sys.executable, apply=True)
        text = launcher.read_text()
        self.assertIn('$HOME/.local/share/cansat-lab/cansat_bootstrap.py', text)
        self.assertNotIn(str(self.home), text)
        self.assertTrue((self.root / 'client_state.json').exists())
        self.assertTrue((self.root / 'cansat_bootstrap.py').exists())
        self.assertTrue(list((self.root / 'client_backups').glob('*/cansat-lab')))

    def test_snapshot_keeps_protocol_one(self):
        source = Path(self.temp.name) / 'source'
        source.mkdir()
        for name in ('app.py', 'launch_v13_4.sh', 'project_store.py', 'project_hub.py'):
            (source / name).write_text('# test\n')
        root = Path(self.temp.name) / 'published'
        manifest = publish_release.snapshot(source, root)
        self.assertEqual(manifest['client_protocol'], 1)
        self.assertIn(updater.APP + '/distribution/cansat_bootstrap.py', manifest['files'])
        self.assertEqual(updater.validate(root)['client_protocol'], 1)


if __name__ == '__main__':
    unittest.main()
