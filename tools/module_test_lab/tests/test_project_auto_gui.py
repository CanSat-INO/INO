"""Qt opt-in, async receive, catalog join, cancellation and offline status."""
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
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication,QCheckBox,QLabel,QMessageBox
    from PySide6.QtTest import QTest
except ImportError as exc:
    raise unittest.SkipTest('Use the existing GUI venv with QtTest') from exc


class AutoGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='cansat-auto-gui-')
        cls.home=Path(cls.temp.name)
        cls.environment=patch.dict(os.environ,HOME=str(cls.home),USERPROFILE=str(cls.home),
            XDG_CONFIG_HOME=str(cls.home/'config'),XDG_CACHE_HOME=str(cls.home/'cache'))
        cls.environment.start()
        import project_store,importlib
        cls.store=project_store
        cls.project=project_store.create_project('Auto GUI','INO Team','Test only')
        os.environ[project_store.PROJECT_ENV]=cls.project.id
        import records
        importlib.reload(records)
        cls.records=records
        import project_auto_core,project_auto_gui
        cls.core=project_auto_core;cls.gui=project_auto_gui
        cls.app=QApplication.instance() or QApplication([])
        from app import TestLab
        from project_shell import install_project_shell
        cls.Window=TestLab;cls.install=staticmethod(install_project_shell)
    @classmethod
    def tearDownClass(cls):
        os.environ.pop(cls.store.PROJECT_ENV,None)
        cls.environment.stop();cls.temp.cleanup()
    def setUp(self):
        import project_settings
        project_settings.save(self.project.id,'club/data','main')
        self.core.set_enabled(self.project.id,False)
        self.core.set_catalog_enabled(False)
        self.records.save_records([])
        self.window=self.Window();self.install(self.window);self.window.show()
        self.controller=self.window.project_auto
        self.checkbox=self.window.findChild(QCheckBox,'projectAutoEnabled')
        self.status=self.window.findChild(QLabel,'projectAutoStatus')
        QTest.qWait(20)
    def tearDown(self):
        self.controller.checkbox.setChecked(False)
        if self.controller.worker:
            self.controller.worker.requestInterruption();self.controller.worker.wait(2000)
        self.app.processEvents()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):self.window.close()
        self.app.processEvents()
    def wait_done(self,controller):
        until=time.monotonic()+3
        while controller.worker is not None and time.monotonic()<until:
            self.app.processEvents();QTest.qWait(10)
        self.assertIsNone(controller.worker)
    def test_default_off_and_cancel_never_contacts_github(self):
        self.assertFalse(self.checkbox.isChecked())
        with patch.object(self.gui,'message',return_value=QMessageBox.No),patch.object(self.gui.core,'ProjectAPI') as api:
            self.checkbox.setChecked(True);self.app.processEvents()
            api.assert_not_called()
        self.assertFalse(self.checkbox.isChecked())
        self.assertFalse(self.core.enabled(self.project.id))
    def test_opt_in_receives_on_gui_thread_without_overwriting_inputs(self):
        incoming=self.records.new_record(scenario='Incoming saved run')
        class API:
            def __init__(self,**kwargs):pass
            def cycle(inner,*args):
                return {'cache':{},'confirmed':{},'sent':0,'conflicts':[], 'blocked':{},
                        'received':[(incoming,{})],'metadata_differs':False}
        workflow=self.window.v20_workflow_tab
        workflow.context_fields['name'].setText('未保存の入力を保持')
        with patch.object(self.gui,'message',return_value=QMessageBox.Yes),patch.object(self.gui.core,'ProjectAPI',API):
            self.checkbox.setChecked(True);self.wait_done(self.controller)
        self.assertEqual(self.records.load_records()[0]['id'],incoming['id'])
        self.assertEqual(workflow.context_fields['name'].text(),'未保存の入力を保持')
        self.assertIn('受信 1件',self.status.text())
        self.assertFalse(self.controller.manual_allowed())
    def test_network_failure_keeps_record_and_defers_retry(self):
        original=self.records.add_record(self.records.new_record(scenario='Local pending'))
        class API:
            def __init__(self,**kwargs):pass
            def cycle(inner,*args):raise self.core.SyncError('offline test')
        with patch.object(self.gui,'message',return_value=QMessageBox.Yes),patch.object(self.gui.core,'ProjectAPI',API):
            self.checkbox.setChecked(True);self.wait_done(self.controller)
        self.assertEqual(self.records.load_records(),[original])
        self.assertIn('同期保留',self.status.text())
        self.assertGreater(self.controller.next_allowed,time.monotonic())
    def test_close_waits_for_worker_and_cancelled_close_keeps_window(self):
        class API:
            def __init__(inner,cancelled,**kwargs):inner.cancelled=cancelled
            def cycle(inner,*args):
                while not inner.cancelled():QThread.msleep(10)
                raise self.core.Cancelled('stopped')
        from PySide6.QtCore import QThread
        with patch.object(self.gui,'message',return_value=QMessageBox.Yes),patch.object(self.gui.core,'ProjectAPI',API),patch.object(QMessageBox,'question',return_value=QMessageBox.No):
            self.checkbox.setChecked(True)
            self.assertIsNotNone(self.controller.worker)
            self.window.close();self.wait_done(self.controller)
            self.assertTrue(self.window.isVisible())
            self.assertFalse(self.controller.closing)
    def test_catalog_join_registers_same_id_and_enables_auto_sharing(self):
        from project_hub import ProjectHub
        foreign=self.store.create_project('Remote project','Members')
        doc=self.core.document(foreign)
        # Use a separate PC for registration, not the project already on disk.
        member_root=self.home/'member-catalog'/'cansat_module_lab_data'
        with patch.object(self.store,'base_dir',return_value=member_root):
            hub=ProjectHub(Path(__file__).resolve().parents[1]/'app.py')
            try:
                hub.show();self.app.processEvents()
                hub.catalog.source={'repository':'club/data','branch':'main','enabled':False}
                # Feed an authenticated network response without real network.
                hub.catalog.checkbox.blockSignals(True);hub.catalog.checkbox.setChecked(True);hub.catalog.checkbox.blockSignals(False)
                hub.catalog.joined_catalog({'projects':[doc],'cache':{}})
                hub.catalog.items.setCurrentRow(0)
                with patch.object(self.gui,'message',return_value=QMessageBox.Yes),patch.object(hub,'launch') as launch:
                    hub.catalog.join_project()
                    launch.assert_called_once_with(foreign.id)
                self.assertEqual(self.store.read_project(foreign.id).name,'Remote project')
                self.assertTrue(self.core.enabled(foreign.id))
            finally:
                hub.catalog.checkbox.blockSignals(True);hub.catalog.checkbox.setChecked(False);hub.catalog.checkbox.blockSignals(False)
                hub.catalog.background.timer.stop();hub.hide();hub.deleteLater();self.app.processEvents()
    def test_cancel_catalog_join_does_not_register_or_enable(self):
        from project_hub import ProjectHub
        doc=self.core.document(self.project)
        member_root=self.home/'cancel-catalog'/'cansat_module_lab_data'
        with patch.object(self.store,'base_dir',return_value=member_root):
            hub=ProjectHub(Path(__file__).resolve().parents[1]/'app.py')
            try:
                hub.catalog.checkbox.blockSignals(True);hub.catalog.checkbox.setChecked(True);hub.catalog.checkbox.blockSignals(False)
                hub.catalog.joined_catalog({'projects':[doc],'cache':{}});hub.catalog.items.setCurrentRow(0)
                with patch.object(self.gui,'message',return_value=QMessageBox.No),patch.object(hub,'launch') as launch:
                    hub.catalog.join_project();launch.assert_not_called()
                self.assertFalse(member_root.exists())
            finally:
                hub.catalog.background.timer.stop();hub.hide();hub.deleteLater();self.app.processEvents()


if __name__=='__main__':unittest.main()
