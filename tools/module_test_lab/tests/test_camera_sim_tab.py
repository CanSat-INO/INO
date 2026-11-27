import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import Mock,patch
try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QProcess
    from camera_sim_tab import CameraSimTab
    HAVE_QT=True
except ImportError:HAVE_QT=False


@unittest.skipUnless(HAVE_QT,'PySide6 unavailable')
class CameraPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):self.tab=CameraSimTab()
    def tearDown(self):
        self.tab.process=None;self.tab.timer.stop();self.tab.deleteLater();self.app.processEvents()

    def test_not_ready_until_config_is_loaded(self):
        self.assertFalse(self.tab.start_button.isEnabled())
        self.assertFalse(self.tab.test_button.isEnabled())
        self.assertFalse(self.tab.stop_button.isEnabled())

    def test_stop_never_signals_process_group_zero(self):
        proc=Mock();proc.state.return_value=QProcess.Starting;proc.processId.return_value=0
        self.tab.process=proc
        with patch('camera_sim_tab.os.killpg') as kill,patch('camera_sim_tab.QTimer.singleShot') as retry:
            self.tab.stop();kill.assert_not_called();retry.assert_called_once()
        self.assertTrue(self.tab.stopping)

    def test_stop_does_not_signal_an_unowned_process_group(self):
        proc=Mock();proc.state.return_value=QProcess.Running;proc.processId.return_value=123
        self.tab.process=proc
        with patch('camera_sim_tab.os.getpgid',return_value=999),patch('camera_sim_tab.os.killpg') as kill,patch('camera_sim_tab.QTimer.singleShot'):
            self.tab.stop();kill.assert_not_called()

    def test_stop_signals_own_group_only_once(self):
        proc=Mock();proc.state.return_value=QProcess.Running;proc.processId.return_value=123
        self.tab.process=proc
        with patch('camera_sim_tab.os.getpgid',return_value=123),patch('camera_sim_tab.os.killpg') as kill:
            self.tab.stop();self.tab.stop();self.assertEqual(kill.call_count,1);self.assertEqual(kill.call_args.args[0],123)

if __name__=='__main__':unittest.main()
