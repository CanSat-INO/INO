"""Regression coverage for the merge of upstream exit confirmation and camera cleanup."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
try:
    from PySide6.QtWidgets import QMessageBox
    from app import TestLab
    HAVE_QT=True
except ImportError:HAVE_QT=False


@unittest.skipUnless(HAVE_QT,'PySide6 unavailable')
class CameraMergeExitTests(unittest.TestCase):
    def host(self):
        camera=Mock();camera.active.return_value=True
        return SimpleNamespace(_sync_worker=None,camera_sim_tab=camera,close=Mock())

    def test_cancel_does_not_stop_camera(self):
        host=self.host();event=Mock()
        with patch('app.QMessageBox.question',return_value=QMessageBox.No):
            TestLab.closeEvent(host,event)
        event.ignore.assert_called_once();host.camera_sim_tab.stop.assert_not_called()
        self.assertFalse(getattr(host,'_exit_confirmed',False))

    def test_async_camera_stop_prompts_only_once(self):
        host=self.host();event=Mock()
        with patch('app.QMessageBox.question',return_value=QMessageBox.Yes) as question,patch('PySide6.QtCore.QTimer.singleShot') as retry:
            TestLab.closeEvent(host,event);TestLab.closeEvent(host,event)
        question.assert_called_once();self.assertTrue(host._exit_confirmed)
        self.assertEqual(retry.call_count,2);host.camera_sim_tab.stop.assert_called()

    def test_github_sync_still_blocks_exit_before_camera_stop(self):
        host=self.host();host._sync_worker=Mock();host._sync_worker.isRunning.return_value=True
        with patch('app.QMessageBox.question') as question,patch('app.QMessageBox.information'):
            TestLab.closeEvent(host,Mock())
        question.assert_not_called();host.camera_sim_tab.stop.assert_not_called()

if __name__=='__main__':unittest.main()
