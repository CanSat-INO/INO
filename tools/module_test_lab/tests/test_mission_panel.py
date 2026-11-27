import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QProcess
from mission_sim_tab import MissionSimTab
from app import TestLab as LabWindow

class MissionPanelTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
 def test_stop_never_targets_process_group_zero(self):
  tab=MissionSimTab();proc=Mock();proc.state.return_value=QProcess.Starting;proc.processId.return_value=0;tab.process=proc
  with patch('mission_sim_tab.os.killpg') as kill,patch('mission_sim_tab.QTimer.singleShot'):
   tab.stop();kill.assert_not_called()
  tab.process=None;tab.timer.stop();tab.deleteLater();self.app.processEvents()
 def test_exit_stops_camera_and_mission_without_dropping_confirmation(self):
  camera=Mock();mission=Mock();camera.active.return_value=True;mission.active.return_value=True
  host=SimpleNamespace(_sync_worker=None,camera_sim_tab=camera,mission_sim_tab=mission,close=Mock())
  with patch('app.QMessageBox.question',return_value=QMessageBox.Yes),patch('PySide6.QtCore.QTimer.singleShot'):
   LabWindow.closeEvent(host,Mock())
  camera.stop.assert_called_once();mission.stop.assert_called_once();self.assertTrue(host._exit_confirmed)

if __name__=='__main__':unittest.main()
