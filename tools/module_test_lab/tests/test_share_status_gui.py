"""Read-only probes, cancellation and cross-screen share indicators in real Qt."""
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
    from PySide6.QtCore import QThread
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PySide6.QtTest import QTest
except ImportError as exc:raise unittest.SkipTest('Use existing GUI venv with QtTest') from exc


class ShareStatusGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='cansat-share-status-');cls.home=Path(cls.temp.name)
        cls.env=patch.dict(os.environ,HOME=str(cls.home),USERPROFILE=str(cls.home),XDG_CONFIG_HOME=str(cls.home/'config'),XDG_CACHE_HOME=str(cls.home/'cache'))
        cls.env.start()
        import project_store,importlib
        cls.store=project_store;cls.project=project_store.create_project('Status GUI')
        os.environ[project_store.PROJECT_ENV]=cls.project.id
        import records
        importlib.reload(records);cls.records=records
        import project_auto_core,project_settings,project_storage_gui
        cls.core=project_auto_core;cls.settings=project_settings;cls.gui=project_storage_gui
        cls.app=QApplication.instance() or QApplication([])
        from app import TestLab
        from project_shell import install_project_shell
        cls.Window=TestLab;cls.install=staticmethod(install_project_shell)
    @classmethod
    def tearDownClass(cls):
        os.environ.pop(cls.store.PROJECT_ENV,None);cls.env.stop();cls.temp.cleanup()
    def setUp(self):
        self.settings.save(self.project.id,'club/data','main')
        self.records.save_records([]);self.dialogs=[]
        self.window=self.Window();self.install(self.window);self.window.show();QTest.qWait(20)
        self.auto=self.window.project_auto;self.strip=self.window.project_status_strip
    def tearDown(self):
        self.window.project_connection_dialog=None
        for dialog in self.dialogs:
            if dialog.worker:dialog.reject();self.wait_done(dialog)
            dialog.reject();dialog.deleteLater()
        if self.strip.dialog is not None:self.strip.dialog.reject()
        self.auto.checkbox.setChecked(False)
        if self.auto.worker:self.auto.worker.requestInterruption();self.auto.worker.wait(3000)
        self.app.processEvents()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Yes):self.window.close()
        self.app.processEvents()
    def dialog(self):
        dialog=self.gui.ShareSettingsDialog(self.window);self.dialogs.append(dialog);dialog.show();self.app.processEvents();return dialog
    def wait_done(self,owner):
        until=time.monotonic()+4
        while owner.worker is not None and time.monotonic()<until:self.app.processEvents();QTest.qWait(10)
        self.assertIsNone(owner.worker)
    def enabled_without_network(self):
        self.auto.timer.stop();self.auto.checkbox.blockSignals(True);self.auto.checkbox.setChecked(True);self.auto.checkbox.blockSignals(False)
    def result(self,confirmed=None,blocked=None):
        return {'cache':{},'confirmed':confirmed or {},'sent':0,'conflicts':[],'blocked':blocked or {},'received':[],'metadata_differs':False}
    def test_footer_is_available_across_tabs_without_discarding_input(self):
        workflow=self.window.v20_workflow_tab;workflow.context_fields['name'].setText('Keep this draft')
        for target in ('センサー実験・ログ解析','実験記録・コード版管理（v16）','実験管理・仮想ログ比較（v19）'):
            self.window.navigation.open_named_tab(target);self.app.processEvents()
            self.assertTrue(self.strip.button.isVisible());self.assertIn('PC保存 0件',self.window.statusBar().currentMessage())
        self.assertEqual(workflow.context_fields['name'].text(),'Keep this draft')
        self.assertEqual(self.records.load_records(),[])
    def test_confirmed_count_requires_matching_current_record_and_invalidates_on_edit(self):
        rec=self.records.add_record(self.records.new_record(scenario='run'));self.window.refresh_ledger()
        self.assertEqual(self.strip.summary['shared'],0)
        self.enabled_without_network();self.auto.success(self.result({rec['id']:self.core.digest(rec)}))
        self.assertEqual(self.strip.summary['state'],'shared')
        rec['notes']='changed after confirmation';self.records.save_records([rec]);self.window.refresh_ledger()
        self.assertEqual(self.strip.summary['shared'],0);self.assertEqual(self.strip.summary['pending'],1)
    def test_failure_and_missing_folder_explain_pending_without_changing_records(self):
        rec=self.records.add_record(self.records.new_record());self.window.refresh_ledger();before=self.records.RECORDS_FILE.read_bytes()
        self.enabled_without_network();self.auto.success(self.result(blocked={rec['id']:'共有フォルダーが未設定です'}))
        self.assertEqual(self.strip.summary['needs'],1);self.assertIn('ZIP保存先',self.strip.detail)
        error=self.core.SyncError('offline');error.reason='network';self.auto.failed(error)
        self.assertEqual(self.strip.summary['state'],'problem');self.assertIn('ネットワーク',self.strip.detail)
        self.assertEqual(self.records.RECORDS_FILE.read_bytes(),before)
    def test_read_only_probe_does_not_save_settings_or_send_records(self):
        calls=[]
        class API:
            def __init__(inner,repository,branch,**kwargs):inner.repo=repository;inner.branch=branch
            def _api(inner,method,path,**kwargs):
                calls.append((method,path));return {'private':True,'permissions':{'push':False}} if path==f'repos/{inner.repo}' else {'name':inner.branch}
        dialog=self.dialog();dialog.repo.setText('https://github.com/club/other')
        before=self.settings.path(self.project.id).read_bytes();ledger=self.records.RECORDS_FILE.read_bytes()
        with patch.object(self.gui,'ProjectAPI',API):dialog.check_connection();self.wait_done(dialog)
        self.assertEqual([m for m,p in calls],['GET','GET']);self.assertIn('書込み権限はありません',dialog.result.text())
        self.assertEqual(self.settings.path(self.project.id).read_bytes(),before);self.assertEqual(self.records.RECORDS_FILE.read_bytes(),ledger)
    def test_invalid_link_and_auth_failure_show_actions_without_persisting(self):
        dialog=self.dialog();before=self.settings.path(self.project.id).read_bytes();dialog.repo.setText('invalid')
        with patch.object(self.gui,'ProjectAPI') as api:dialog.check_connection();api.assert_not_called()
        error=self.core.SyncError('auth test');error.reason='auth'
        dialog.repo.setText('club/other')
        with patch.object(self.gui,'ProjectAPI',side_effect=error):dialog.check_connection();self.wait_done(dialog)
        self.assertIn('gh auth',dialog.result.text());self.assertEqual(self.settings.path(self.project.id).read_bytes(),before)
    def test_cancel_probe_waits_for_thread_and_keeps_settings(self):
        class API:
            def __init__(inner,repository,branch,cancelled):inner.repo=repository;inner.branch=branch;inner.cancelled=cancelled
            def _api(inner,*args,**kwargs):
                while not inner.cancelled():QThread.msleep(5)
                raise self.core.Cancelled('cancelled')
        dialog=self.dialog();before=self.settings.path(self.project.id).read_bytes()
        with patch.object(self.gui,'ProjectAPI',API):
            dialog.check_connection();dialog.reject();self.wait_done(dialog)
        self.assertFalse(dialog.isVisible());self.assertEqual(self.settings.path(self.project.id).read_bytes(),before)
    def test_rate_limit_blocks_immediate_repeated_probe(self):
        dialog=self.dialog();error=self.core.SyncError('rate test');error.reason='rate';error.retry_after=120
        with patch.object(self.gui,'ProjectAPI',side_effect=error):dialog.check_connection();self.wait_done(dialog)
        with patch.object(self.gui,'ProjectAPI') as api:
            dialog.check_connection();api.assert_not_called()
        self.assertIn('待機中',dialog.result.text())
    def test_main_window_close_waits_for_probe_and_keeps_draft_when_cancelled(self):
        class API:
            def __init__(inner,repository,branch,cancelled):inner.repo=repository;inner.branch=branch;inner.cancelled=cancelled
            def _api(inner,*args,**kwargs):
                while not inner.cancelled():QThread.msleep(5)
                raise self.core.Cancelled('cancelled')
        workflow=self.window.v20_workflow_tab;workflow.context_fields['name'].setText('Keep unsaved draft')
        dialog=self.dialog();self.window.project_connection_dialog=dialog
        with patch.object(self.gui,'ProjectAPI',API),patch.object(QMessageBox,'question',return_value=QMessageBox.No):
            dialog.check_connection();self.window.close();self.wait_done(dialog);QTest.qWait(20)
        self.assertTrue(self.window.isVisible());self.assertEqual(workflow.context_fields['name'].text(),'Keep unsaved draft')
    def test_ledger_read_failure_does_not_restore_stale_success_while_typing(self):
        with patch.object(self.records,'load_records',side_effect=ValueError('invalid ledger')):
            self.strip.local_changed();self.window.v20_workflow_tab.context_fields['name'].setText('draft')
            self.assertTrue(self.strip.read_problem);self.assertIn('読取待ち',self.window.statusBar().currentMessage())
        self.strip.local_changed();self.assertFalse(self.strip.read_problem)
    def test_details_open_without_leaving_current_screen_or_changing_records(self):
        self.window.navigation._open_workflow();before=self.records.RECORDS_FILE.read_bytes();current=self.window.tabs.currentWidget()
        dialog=self.strip.show_details();self.app.processEvents()
        self.assertIs(self.window.tabs.currentWidget(),current);self.assertTrue(dialog.isVisible())
        self.assertIn('共有先',self.strip.detail);dialog.reject();self.app.processEvents()
        self.assertEqual(self.records.RECORDS_FILE.read_bytes(),before)


if __name__=='__main__':unittest.main()
