"""Qt integration for local settings, ZIP registration and safe closing."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
try:
    from PySide6.QtCore import QTimer,Qt,QThread
    from PySide6.QtWidgets import QApplication,QDialog,QDialogButtonBox,QLineEdit,QMessageBox
    from PySide6.QtTest import QTest
except ImportError as exc:raise unittest.SkipTest('Existing GUI venv and QtTest required') from exc


class StorageGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='cansat-storage-gui-');cls.home=Path(cls.temp.name)
        cls.env=patch.dict(os.environ,HOME=str(cls.home),USERPROFILE=str(cls.home),XDG_CONFIG_HOME=str(cls.home/'config'),XDG_CACHE_HOME=str(cls.home/'cache'))
        cls.env.start()
        import project_store,importlib
        cls.store=project_store;cls.project=project_store.create_project('Storage GUI',year=2026,team='INO')
        os.environ[project_store.PROJECT_ENV]=cls.project.id
        import records
        importlib.reload(records);cls.records=records
        import project_storage_gui,project_settings
        cls.gui=project_storage_gui;cls.settings=project_settings
        cls.app=QApplication.instance() or QApplication([])
        from app import TestLab
        from project_shell import install_project_shell
        cls.Window=TestLab;cls.install=staticmethod(install_project_shell)
    @classmethod
    def tearDownClass(cls):
        os.environ.pop(cls.store.PROJECT_ENV,None);cls.env.stop();cls.temp.cleanup()
    def setUp(self):
        self.shared=self.home/'shared';self.shared.mkdir(exist_ok=True)
        self.settings.save(self.project.id,'club/data','main',str(self.shared))
        self.records.save_records([])
        self.window=self.Window();self.install(self.window);self.window.show();self.panel=self.window.project_packages
        self.messages=patch.object(self.gui,'message',return_value=QMessageBox.Yes);self.messages.start()
        QTest.qWait(20)
    def tearDown(self):
        if self.panel.worker:self.panel.worker.requestInterruption();self.panel.worker.wait(3000)
        self.app.processEvents()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):self.window.close()
        self.messages.stop();self.app.processEvents()
    def wait_done(self):
        until=time.monotonic()+5
        while self.panel.worker is not None and time.monotonic()<until:self.app.processEvents();QTest.qWait(10)
        self.assertIsNone(self.panel.worker)
    def register(self):
        file=self.home/'test-model.sdf';file.write_text('<sdf/>')
        with patch.object(self.gui.QFileDialog,'getOpenFileNames',return_value=([str(file)],'')),patch.object(self.gui.QInputDialog,'getText',return_value=('Model',True)):
            self.panel.register(False);self.wait_done()
        return file
    def test_register_saves_reference_and_preserves_source_and_four_routes(self):
        file=self.register();saved=self.records.load_records()
        self.assertEqual(len(saved),1);self.assertEqual(saved[0]['shared_files'][0]['file_count'],1)
        self.assertEqual(file.read_text(),'<sdf/>');self.assertEqual(self.panel.items.count(),1)
        for index in range(1,5):self.assertIsNotNone(self.window.findChild(self.gui.QPushButton,f'projectQuick{index}'))
    def test_missing_folder_does_not_create_record(self):
        self.settings.save(self.project.id,'club/data','main','')
        self.panel.register(False)
        self.assertEqual(self.records.load_records(),[]);self.assertIsNone(self.panel.worker)
    def test_corrupt_zip_does_not_open(self):
        self.register();record=self.records.load_records()[0];ref=record['shared_files'][0]
        (self.shared/ref['relative_path']).write_bytes(b'bad')
        self.panel.items.setCurrentRow(0)
        with patch.object(self.gui.QDesktopServices,'openUrl') as opened:
            self.panel.open_selected();self.wait_done();opened.assert_not_called()
        self.assertIn('SHA256',self.panel.status.text())
    def test_settings_save_changes_local_destination_without_record_changes(self):
        self.register();before=self.records.RECORDS_FILE.read_bytes();errors=[]
        def save_dialog():
            dialog=self.app.activeModalWidget()
            try:
                self.assertIsInstance(dialog,QDialog)
                dialog.findChild(QLineEdit,'projectStorageRepository').setText('club/next')
                buttons=dialog.findChild(QDialogButtonBox)
                buttons.button(QDialogButtonBox.Save).click()
            except Exception as exc:errors.append(exc);dialog.reject()
        QTimer.singleShot(20,save_dialog);self.gui.configure(self.window)
        self.assertEqual(errors,[]);self.assertEqual(self.settings.read(self.project.id)['repository'],'club/next')
        self.assertEqual(self.records.RECORDS_FILE.read_bytes(),before)
    def test_close_waits_for_zip_worker_and_cancel_close_resumes_window(self):
        def task(cancel):
            while not cancel():QThread.msleep(5)
            raise ValueError('cancelled')
        self.panel.run_job(task,lambda value:None)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.No):
            self.window.close();self.wait_done()
            self.assertTrue(self.window.isVisible());self.assertFalse(self.panel.closing)


if __name__=='__main__':unittest.main()
