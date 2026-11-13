"""Beginner entry flows: reveal, search, consent, layout and data preservation."""
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
    from PySide6.QtWidgets import QApplication,QWidget,QPushButton,QMessageBox
    from PySide6.QtTest import QTest
except ImportError as exc:raise unittest.SkipTest('Existing GUI venv with QtTest required') from exc


class BeginnerHubTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='cansat-beginner-');self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)
        self.env=patch.dict(os.environ,HOME=str(self.home),USERPROFILE=str(self.home),XDG_CONFIG_HOME=str(self.home/'config'),XDG_CACHE_HOME=str(self.home/'cache'))
        self.env.start();self.addCleanup(self.env.stop)
        self.previous_id=os.environ.pop('CANSAT_LAB_PROJECT_ID',None)
        self.addCleanup(self.restore_id)
        import project_store,project_auto_gui,project_settings
        from project_hub import ProjectHub
        self.store=project_store;self.gui=project_auto_gui;self.settings=project_settings
        self.hub=ProjectHub(Path(__file__).resolve().parents[1]/'app.py')
        self.hub.show();QTest.qWait(25)
    def restore_id(self):
        if self.previous_id is not None:os.environ['CANSAT_LAB_PROJECT_ID']=self.previous_id
    def tearDown(self):
        background=self.hub.catalog.background;background.timer.stop()
        if background.worker:
            background.worker.requestInterruption();background.worker.wait(3000)
        self.app.processEvents();self.hub.hide();self.hub.deleteLater();self.app.processEvents()
    def click(self,button):QTest.mouseClick(button,Qt.LeftButton);self.app.processEvents()
    def wait_done(self):
        until=time.monotonic()+3
        while self.hub.catalog.background.worker is not None and time.monotonic()<until:
            self.app.processEvents();QTest.qWait(10)
        self.assertIsNone(self.hub.catalog.background.worker)
    def test_first_view_has_no_setup_forms_and_creates_no_data(self):
        self.assertTrue(self.hub.empty_state.isVisible());self.assertFalse(self.hub.open_button.isVisible())
        self.assertTrue(self.hub.join_button.isVisible());self.assertTrue(self.hub.create_toggle.isVisible())
        self.assertFalse(self.hub.create_form.isVisible());self.assertFalse(self.hub.join_area.isVisible());self.assertFalse(self.hub.more_area.isVisible())
        self.assertFalse(self.store.base_dir().exists())
    def test_switching_create_and_join_preserves_draft_without_creating_project(self):
        self.click(self.hub.create_toggle);self.assertTrue(self.hub.name.isVisible())
        self.hub.name.setText('Draft project');self.hub.team.setText('INO')
        self.click(self.hub.join_button)
        self.assertTrue(self.hub.catalog.repository.isVisible());self.assertFalse(self.hub.create_form.isVisible())
        self.click(self.hub.create_toggle)
        self.assertEqual(self.hub.name.text(),'Draft project');self.assertEqual(self.hub.team.text(),'INO')
        self.assertFalse(self.store.base_dir().exists())
    def test_single_project_is_selected_and_open_does_not_change_ledger(self):
        project=self.store.create_project('INO',year=2026,team='INO')
        ledger=project.directory/'records.json';before=ledger.read_bytes();self.hub.reload();self.app.processEvents()
        self.assertEqual(self.hub.projects.currentItem().data(Qt.UserRole),project.id)
        self.assertTrue(self.hub.open_button.isEnabled())
        with patch.object(self.hub,'launch') as launch:self.click(self.hub.open_button);launch.assert_called_once_with(project.id)
        self.assertEqual(ledger.read_bytes(),before)
    def test_link_search_uses_default_branch_and_does_not_enable_experiment_sharing(self):
        project=self.store.Project('a'*32,'Remote INO','Team','',self.home/'unused',2026,'INO')
        doc=self.gui.core.document(project);calls=[]
        class API:
            def __init__(inner,repository,branch,**kwargs):calls.append((repository,branch))
            def catalog(inner,cache):return {'projects':[doc],'cache':{}}
        self.click(self.hub.join_button);panel=self.hub.catalog
        self.assertFalse(panel.details_area.isVisible())
        panel.repository.setText('https://github.com/club/ino')
        with patch.object(self.gui.core,'ProjectAPI',API),patch.object(self.gui.core,'set_enabled') as enable:
            self.click(panel.search_button);self.wait_done()
            self.assertEqual(calls,[('club/ino','main')]);self.assertEqual(panel.items.count(),1)
            self.assertEqual(self.store.list_projects(),([],0));enable.assert_not_called()
            panel.items.setCurrentRow(0)
            with patch.object(self.gui,'message',return_value=QMessageBox.No),patch.object(self.hub,'launch') as launch:
                self.click(panel.join);launch.assert_not_called()
            self.assertEqual(self.store.list_projects(),([],0));enable.assert_not_called()
    def test_invalid_link_never_starts_network_and_empty_result_explains_next_step(self):
        self.click(self.hub.join_button);panel=self.hub.catalog;panel.repository.setText('not a repository link')
        with patch.object(self.gui,'message'),patch.object(self.gui.core,'ProjectAPI') as api:
            self.click(panel.search_button);api.assert_not_called()
        self.assertFalse(self.settings.catalog()['enabled'])
        panel.checkbox.blockSignals(True);panel.checkbox.setChecked(True);panel.checkbox.blockSignals(False)
        panel.joined_catalog({'projects':[],'cache':{}})
        self.assertIn('作成した人',panel.status.text());self.assertFalse(panel.join.isEnabled())
        panel.checkbox.blockSignals(True);panel.checkbox.setChecked(False);panel.checkbox.blockSignals(False)
    def test_narrow_and_wide_windows_keep_content_centered_without_horizontal_scroll(self):
        content=self.hub.findChild(QWidget,'projectHubContent')
        for width in (820,1020,1920):
            self.hub.resize(width,900);self.app.processEvents()
            self.assertEqual(self.hub.centralWidget().horizontalScrollBar().maximum(),0)
            self.assertLessEqual(content.width(),1080)
            if width<1080:self.assertGreater(content.width(),width-100)
        output=os.environ.get('CANSAT_GUI_OUTPUT_DIR')
        if output:
            folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
            self.assertTrue(self.hub.grab().save(str(folder/'beginner-hub.png')))
            self.click(self.hub.join_button)
            self.assertTrue(self.hub.grab().save(str(folder/'beginner-join.png')))
            self.click(self.hub.create_toggle)
            self.assertTrue(self.hub.grab().save(str(folder/'beginner-create.png')))


if __name__=='__main__':unittest.main()
