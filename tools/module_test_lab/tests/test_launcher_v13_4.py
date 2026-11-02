"""Standalone tests for v13.4 WSLg IME launcher (no Qt/X server required)."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class TestV134Launcher(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'
        self.home.mkdir()
        self.lab = self.root / 'tools' / 'module_test_lab'
        self.lab.mkdir(parents=True)
        source = Path(__file__).resolve().parents[1] / 'launch_v13_4.sh'
        shutil.copy2(source, self.lab / source.name)
        (self.lab / 'app.py').write_text('# dummy\n')
        self.fakebin = self.root / 'fakebin'
        self.fakebin.mkdir()
        self.output = self.root / 'observed.txt'
        self.ready = self.root / 'fcitx-ready'
        self.fcitx_log = self.root / 'fcitx.log'
        self.fake_python = self.root / 'fake-python'
        self.fake_python.write_text('#!/bin/sh\n'
                                    'printf "%s\\n" "$IBUS_USE_PORTAL" "$QT_QPA_PLATFORM" "$QT_IM_MODULE" "$QT_IM_MODULES" "$XMODIFIERS" "$@" > "$TEST_OUTPUT"\n')
        self.fake_python.chmod(0o755)
        fcitx = self.fakebin / 'fcitx5'
        fcitx.write_text('#!/bin/sh\n'
                         'printf "%s\\n" "$*" >> "$FCITX_LOG"\n'
                         'touch "$FCITX_READY"\n')
        fcitx.chmod(0o755)
        remote = self.fakebin / 'fcitx5-remote'
        remote.write_text('#!/bin/sh\n'
                          'if [ "$1" = "--check" ]; then\n'
                          '  test -f "$FCITX_READY"\n'
                          'else\n'
                          '  echo mozc\n'
                          'fi\n')
        remote.chmod(0o755)
        self.env = dict(os.environ,
                        HOME=str(self.home),
                        DISPLAY=':0',
                        DBUS_SESSION_BUS_ADDRESS='unix:path=/test/bus',
                        CANSAT_GUI_PYTHON=str(self.fake_python),
                        PATH=str(self.fakebin) + ':' + os.environ['PATH'],
                        FCITX_LOG=str(self.fcitx_log),
                        FCITX_READY=str(self.ready),
                        TEST_OUTPUT=str(self.output))

    def run_launcher(self, *args):
        return subprocess.run(['bash', str(self.lab / 'launch_v13_4.sh'), *args],
                              env=self.env, text=True, capture_output=True, timeout=15)

    def test_starts_fcitx_when_needed_with_correct_environment(self):
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.fcitx_log.read_text().strip(), '-d --disable=wayland,waylandim')
        values = self.output.read_text().splitlines()
        self.assertEqual(values[:5], ['1', 'xcb', 'ibus', 'ibus', '@im=fcitx'])
        self.assertIn(str(self.lab / 'app.py'), values)

    def test_does_not_restart_running_fcitx(self):
        self.ready.touch()
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.fcitx_log.exists())

    def test_diagnose_does_not_start_gui_or_fcitx(self):
        result = self.run_launcher('--diagnose')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('IBUS_USE_PORTAL=1', result.stdout)
        self.assertIn('QT_IM_MODULE=ibus', result.stdout)
        self.assertNotIn(str(self.lab / "app.py"), self.output.read_text())
        self.assertFalse(self.fcitx_log.exists())

    def test_missing_python_fails_without_starting_ime(self):
        self.env['CANSAT_GUI_PYTHON'] = str(self.root / 'missing-python')
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Python', result.stderr)
        self.assertFalse(self.fcitx_log.exists())


if __name__ == '__main__':
    unittest.main()
