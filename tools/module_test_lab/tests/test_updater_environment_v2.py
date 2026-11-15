"""Environment provisioning tests that never install packages or touch HOME."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

DIST = Path(__file__).resolve().parents[1] / 'distribution'
sys.path.insert(0, str(DIST))
import cansat_update as updater


class EnvironmentV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cansat-venv-v2-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'client'
        self.root.mkdir()
        self.release = Path(self.temp.name) / 'release'
        self.app = self.release / updater.APP
        self.app.mkdir(parents=True)
        for file in ('app.py', 'launch_v13_4.sh', 'project_store.py', 'project_hub.py'):
            (self.app / file).write_text('# fixture\n', encoding='utf-8')

    def build(self, requirements=None):
        file = self.app / 'requirements-runtime.txt'
        if requirements is None:
            file.unlink(missing_ok=True)
        else:
            file.write_text(requirements, encoding='utf-8')
        (self.release / 'release.json').unlink(missing_ok=True)
        manifest = {'format': updater.FORMAT, 'data_format': 1, 'client_protocol': 1,
                    'files': updater.file_list(self.release)}
        (self.release / 'release.json').write_text(json.dumps(manifest))
        return updater.validate(self.release)

    def test_old_releases_keep_previous_interpreter(self):
        self.build()
        self.assertIsNone(updater.runtime_requirements(self.release))
        with patch.object(updater, '_environment_command') as call:
            result = updater.prepare_runtime_python(self.root, self.release, sys.executable)
            self.assertEqual(result, sys.executable)
            call.assert_not_called()

    def test_requirements_have_exact_versions_without_pip_options(self):
        for value in (
            'PySide6>=6.12\n', 'PySide6==6.12.0\n-r other.txt\n',
            'PySide6==6.12.0\n--extra-index-url=https://example.test\n',
            'PySide6 @ https://example.test/a.whl\n',
            'PySide6==6.12.0\nnumpy==2.0; python_version > "3"\n',
            'PySide6==6.12.0\npyside6==6.12.0\n',
            'numpy==2.0\n',
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.build(value)
        self.build('PySide6==6.12.0\n# a comment\nnumpy==2.3.0\n')
        raw, packages = updater.runtime_requirements(self.release)
        self.assertEqual(packages['pyside6'], ('PySide6', '6.12.0'))
        self.assertEqual(packages['numpy'], ('numpy', '2.3.0'))

    def test_new_environment_created_once_and_reused(self):
        self.build('PySide6==6.12.0\n')
        calls = []
        def fake_run(command, timeout=90):
            calls.append(command)
            if len(command) > 1 and command[1] == '-c':
                return SimpleNamespace(stdout=b'3.14:cpython-314:x86_64')
            if command[1:3] == ['-m', 'venv']:
                path = Path(command[3])
                (path / 'bin').mkdir(parents=True)
                (path / 'bin/python').write_text('fake-python')
        with patch.object(updater, '_environment_command', side_effect=fake_run), \
             patch.object(updater, '_verify_runtime_python') as verify:
            first = updater.prepare_runtime_python(self.root, self.release, sys.executable)
            second = updater.prepare_runtime_python(self.root, self.release, sys.executable)
        self.assertEqual(first, second)
        self.assertTrue(Path(first).is_file())
        self.assertEqual(sum(cmd[1:3] == ['-m', 'venv'] for cmd in calls), 1)
        self.assertEqual(sum('install' in cmd for cmd in calls), 1)
        self.assertEqual(verify.call_count, 2)  # initial verification + cached
        self.assertTrue(list((self.root / 'environments').glob('*/ready.json')))
        self.assertEqual(len(list((self.root / 'environments').glob('*/ready.json'))), 1)

    def test_install_failure_does_not_mark_as_ready(self):
        self.build('PySide6==6.12.0\n')
        def fail(command, timeout=90):
            if len(command) > 1 and command[1] == '-c':
                return SimpleNamespace(stdout=b'3.14:cpython-314:x86_64')
            if command[1:3] == ['-m', 'venv']:
                path = Path(command[3]); (path / 'bin').mkdir(parents=True)
                (path / 'bin/python').write_text('fake-python')
            elif 'install' in command:
                raise ValueError('offline')
        with patch.object(updater, '_environment_command', side_effect=fail), \
             patch.object(updater, '_verify_runtime_python'):
            with self.assertRaisesRegex(ValueError, 'offline'):
                updater.prepare_runtime_python(self.root, self.release, sys.executable)
            self.assertFalse(list((self.root / 'environments').glob('*/ready.json')))
            self.assertFalse(list((self.root / 'environments').iterdir()))
            # A transient network failure does not permanently block retries.
            with self.assertRaisesRegex(ValueError, 'offline'):
                updater.prepare_runtime_python(self.root, self.release, sys.executable)

    def test_incomplete_directory_from_crash_is_never_reused(self):
        self.build('PySide6==6.12.0\n')
        digest, _, _ = updater._python_environment(self.root, self.release, sys.executable)
        path = self.root / 'environments' / digest
        path.mkdir(parents=True)
        (path / 'notice.txt').write_text('crashed mid-install')
        with self.assertRaisesRegex(ValueError, '作成途中'):
            updater.prepare_runtime_python(self.root, self.release, sys.executable)
        self.assertTrue((path / 'notice.txt').is_file())

    def test_invalid_ready_marker_is_rejected(self):
        self.build('PySide6==6.12.0\n')
        digest, packages, base = updater._python_environment(self.root, self.release, sys.executable)
        path = self.root / 'environments' / digest
        (path / 'bin').mkdir(parents=True)
        (path / 'bin/python').write_text('fake-python')
        (path / 'ready.json').write_text(json.dumps({'schema': 1, 'id': 'wrong'}))
        with self.assertRaisesRegex(ValueError, '一致しません'):
            updater.prepare_runtime_python(self.root, self.release, sys.executable)

    def test_failed_new_environment_does_not_switch_gui_revision(self):
        import shutil
        # Existing GUI has no extra dependencies and has already been installed.
        self.build(None)
        old_revision, new_revision = 'a'*40, 'b'*40
        releases = self.root / 'releases'
        releases.mkdir()
        shutil.copytree(self.release, releases / old_revision)
        updater.save_state(self.root, {'current': old_revision, 'previous': None})
        # The future version adds a dependency, which fails to provision.
        self.build('PySide6==6.12.0\n')
        shutil.copytree(self.release, releases / new_revision)
        def provision(root, release, python):
            if release.name == new_revision:
                raise ValueError('dependency unavailable')
            return str(python)
        with patch.object(updater, 'fetch', return_value=new_revision), \
             patch.object(updater, 'prepare_runtime_python', side_effect=provision), \
             patch.object(updater, 'update_client_from_release') as activation:
            revision, path = updater.select(self.root, base_python=sys.executable)
        self.assertEqual(revision, old_revision)
        self.assertEqual(updater.state(self.root)['current'], old_revision)
        activation.assert_not_called()

    def test_environment_cache_changes_with_requirements(self):
        self.build('PySide6==6.12.0\n')
        first = updater._python_environment(self.root, self.release, sys.executable)[0]
        self.build('PySide6==6.12.0\nnumpy==2.3.0\n')
        second = updater._python_environment(self.root, self.release, sys.executable)[0]
        self.assertNotEqual(first, second)

    def test_release_without_requirements_not_changed_in_updater(self):
        self.build(None)
        with patch.object(updater, 'fetch', return_value='a'*40), \
             patch.object(updater, 'update_client_from_release', return_value=False), \
             patch.object(updater, 'prepare_runtime_python', return_value=sys.executable) as prepared:
            # 'fetch' is mocked; create matching path for validation.
            actual = self.root / 'releases' / ('a'*40)
            import shutil
            shutil.copytree(self.release, actual)
            result = updater.select(self.root, base_python=sys.executable)
            self.assertEqual(result[0], 'a'*40)
            self.assertEqual(updater.state(self.root)['current'], 'a'*40)
            self.assertEqual(prepared.call_count, 2)


if __name__ == '__main__':
    unittest.main()
