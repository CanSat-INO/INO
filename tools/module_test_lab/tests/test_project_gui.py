"""Qt integration tests. Uses a temporary HOME, no hardware or network.

Run in the existing GUI venv. These tests are skipped when QtTest is unavailable.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton, QFileDialog
    from PySide6.QtTest import QTest
except ImportError as exc:
    raise unittest.SkipTest('Run with the existing GUI venv: PySide6.QtTest required') from exc


class ProjectGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='cansat-project-gui-')
        cls.home = Path(cls.temp.name)
        cls.env = patch.dict(os.environ, {'HOME':str(cls.home), 'USERPROFILE':str(cls.home),
                            'XDG_CONFIG_HOME':str(cls.home/'config'), 'XDG_CACHE_HOME':str(cls.home/'cache')})
        cls.env.start()
        import project_store
        cls.store = project_store
        cls.original_id = os.environ.pop(project_store.PROJECT_ENV, None)
        cls.project = project_store.create_project('GUI project A', 'Test team', 'No real data')
        cls.other = project_store.create_project('GUI project B')
        os.environ[project_store.PROJECT_ENV] = cls.project.id
        # This file is intended to run in its own unittest process.
        import records
        import importlib
        importlib.reload(records)
        cls.records = records
        cls.app = QApplication.instance() or QApplication([])
        from app import TestLab
        from project_shell import install_project_shell
        cls.Window = TestLab
        cls.install = staticmethod(install_project_shell)

    @classmethod
    def tearDownClass(cls):
        os.environ.pop(cls.store.PROJECT_ENV, None)
        if cls.original_id is not None:
            os.environ[cls.store.PROJECT_ENV] = cls.original_id
        cls.env.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.records.save_records([])
        self.window = self.Window()
        self.install(self.window)
        self.window.resize(1120,850)
        self.window.show()
        QTest.qWait(50)

    def tearDown(self):
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.window.close()
        self.app.processEvents()

    def click(self, name):
        button=self.window.findChild(QPushButton,name)
        self.assertIsNotNone(button)
        QTest.mouseClick(button,Qt.LeftButton)
        self.app.processEvents()

    def test_file_dialog_views_keep_readable_background_and_text(self):
        from PySide6.QtGui import QPalette
        from PySide6.QtWidgets import QAbstractItemView
        # Real Qt file views created after theming: previous tests mocked the
        # file picker and therefore missed its white viewport/light text.
        def luminance(color):
            values=[v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4
                    for v in (color.redF(),color.greenF(),color.blueF())]
            return sum(v*w for v,w in zip(values,(0.2126,0.7152,0.0722)))
        for mode in (QFileDialog.AcceptSave,QFileDialog.AcceptOpen):
            dialog=QFileDialog(self.window.v20_workflow_tab)
            dialog.setOption(QFileDialog.DontUseNativeDialog,True)
            dialog.setAcceptMode(mode);dialog.setDirectory(str(Path(self.temp.name)))
            try:
                dialog.resize(680,480);dialog.show();QTest.qWait(30)
                for layout in (QFileDialog.Detail,QFileDialog.List):
                    dialog.setViewMode(layout);QTest.qWait(20)
                    views=[v for v in dialog.findChildren(QAbstractItemView) if v.isVisible()]
                    self.assertTrue(views)
                    for view in views:
                        viewport=view.viewport();image=viewport.grab().toImage()
                        # Sample unused space away from filenames and icons.
                        background=image.pixelColor(max(0,image.width()-4),max(0,image.height()-4))
                        self.assertLess(luminance(background),0.08,view.objectName())
                        for group in (QPalette.Active,QPalette.Inactive):
                            foreground=view.palette().color(group,QPalette.Text)
                            ratio=(luminance(foreground)+0.05)/(luminance(background)+0.05)
                            self.assertGreaterEqual(ratio,4.5,(mode,layout,view.objectName(),group))
            finally:
                dialog.reject();dialog.deleteLater();self.app.processEvents()

    def test_project_dashboard_and_four_routes(self):
        nav=self.window.navigation
        self.assertIs(nav.stack.currentWidget(),nav.project_home)
        self.assertIn('CanSat Simulation',self.window.windowTitle())
        targets=('センサー実験・ログ解析','実験記録・コード版管理（v16）',
                 'フェーズ別ミッション・仮想試験','実験管理・仮想ログ比較（v19）')
        for number,target in enumerate(targets,1):
            nav.show_home()
            self.click(f'projectQuick{number}')
            self.assertEqual(nav.tabs.tabText(nav.tabs.currentIndex()),target)
        nav.show_home()
        self.click('projectStartExperiment')
        self.assertIs(nav.tabs.currentWidget(),self.window.v20_workflow_tab)
        self.assertLessEqual(self.window.height(),900)

    def test_installed_shell_scrolls_only_workspace_body_at_three_window_sizes(self):
        nav=self.window.navigation;workflow=self.window.v20_workflow_tab
        nav._open_workflow()
        for width,height in ((1020,720),(1120,800),(1920,1080)):
            self.window.resize(width,height);QTest.qWait(30)
            self.assertLessEqual(self.window.width(),width,'window minimum width forced expansion')
            self.assertLessEqual(self.window.height(),height,'window minimum height forced expansion')
            self.assertEqual(nav.tabs_page.horizontalScrollBar().maximum(),0,(width,height,'outer horizontal'))
            self.assertEqual(nav.tabs_page.verticalScrollBar().maximum(),0,(width,height,'outer vertical'))
            self.assertEqual(workflow.scroll.horizontalScrollBar().maximum(),0,(width,height,'body horizontal'))
            self.assertLessEqual(nav.tabs.width(),nav.tabs_page.viewport().width())
            self.assertLessEqual(nav.tabs.height(),nav.tabs_page.viewport().height())
            for bottom in (False,True):
                workflow.scroll.verticalScrollBar().setValue(workflow.scroll.verticalScrollBar().maximum() if bottom else 0)
                self.app.processEvents()
                fixed=[workflow.progress,workflow.result_status,workflow.save_status,workflow.recommend_button]
                fixed += [b for b in workflow.findChildren(QPushButton) if b.text() in
                    ('CSV解析へ','実験記録票へ','ログ比較へ','下書きを保存…','下書きを開く…')]
                self.assertEqual(len(fixed),9)
                for widget in fixed:
                    visible=widget.visibleRegion().boundingRect()
                    name=widget.objectName() or widget.text()
                    self.assertGreaterEqual(visible.width(),widget.width()-2,(width,height,name))
                    self.assertGreaterEqual(visible.height(),widget.height()-2,(width,height,name))
            output=os.environ.get('CANSAT_GUI_OUTPUT_DIR')
            if output:
                folder=Path(output);folder.mkdir(parents=True,exist_ok=True)
                self.assertTrue(self.window.grab().save(str(folder/f'workspace-fit-{width}x{height}.png')))

    def test_large_legacy_form_does_not_resize_or_offset_workspace_after_return(self):
        nav=self.window.navigation;journal=self.window.v16_journal_tab
        self.window.resize(1020,720)
        nav.open_named_tab('実験記録・コード版管理（v16）');QTest.qWait(30)
        journal.observed.setText('画面を切り替えても残す観測結果')
        nav.tabs_page.verticalScrollBar().setValue(nav.tabs_page.verticalScrollBar().maximum())
        nav._open_workflow();QTest.qWait(30)
        self.assertEqual(nav.tabs_page.verticalScrollBar().maximum(),0)
        self.assertEqual(nav.tabs_page.horizontalScrollBar().maximum(),0)
        self.assertEqual(nav.tabs_page.verticalScrollBar().value(),0)
        self.assertEqual(journal.observed.text(),'画面を切り替えても残す観測結果')
        self.assertEqual(self.records.load_records(),[])

    def test_real_csv_handoff_save_and_quality_check(self):
        workflow=self.window.v20_workflow_tab
        for key,value in dict(name='Project-scoped experiment',tester='Tester',hardware='BNO055',code_version='test').items():
            workflow.context_fields[key].setText(value)
        workflow.use_demo()
        self.assertTrue(workflow.verify_csvs())
        workflow.to_sensor()
        self.assertIsNotNone(self.window.v15_sensor_tab.log)
        workflow.to_journal()
        self.window.v16_journal_tab.save()
        saved=self.records.load_records()
        self.assertEqual(len(saved),1)
        self.assertEqual(saved[0]['project_id'],self.project.id)
        self.assertEqual(workflow.record_id,saved[0]['id'])
        self.assertTrue((self.project.directory/'attachments'/saved[0]['id']).is_dir())
        self.assertEqual(self.store.read_project(self.other.id).directory,self.other.directory)

    def test_session_tag_and_cross_project_refusal(self):
        from v20_workflow_core import load_session,save_session
        workflow=self.window.v20_workflow_tab
        workflow.context_fields['name'].setText('Draft A')
        destination=self.store.export_path('test-session.json',session=True)
        with patch.object(QFileDialog,'getSaveFileName',return_value=(destination,'')):
            workflow.export_session()
        doc=load_session(destination)
        self.assertEqual(doc['project_id'],self.project.id)
        doc['project_id']=self.other.id
        foreign=self.home/'foreign.json';save_session(doc,foreign)
        with patch.object(QFileDialog,'getOpenFileName',return_value=(str(foreign),'')), patch.object(QMessageBox,'warning') as warn:
            workflow.import_session()
        warn.assert_called_once()
        self.assertEqual(workflow.context_fields['name'].text(),'Draft A')

    def test_switch_cancel_preserves_window(self):
        with patch.object(QMessageBox,'question',return_value=QMessageBox.No):
            self.click('projectSwitch')
        self.assertTrue(self.window.isVisible())

    def test_hub_create_and_reopen(self):
        from project_hub import ProjectHub
        hub=ProjectHub(Path(__file__).resolve().parents[1]/'app.py')
        try:
            hub.show();self.app.processEvents()
            QTest.mouseClick(hub.create_toggle,Qt.LeftButton)
            with patch.object(hub,'launch') as launch:
                hub.name.setText('New GUI project')
                hub.owner.setText('Team C')
                QTest.mouseClick(hub.create_button,Qt.LeftButton)
                launch.assert_called_once()
                created=self.store.read_project(launch.call_args.args[0])
                self.assertEqual(created.name,'New GUI project')
                self.assertEqual(created.owner,'Team C')
            self.assertGreaterEqual(hub.projects.count(),3)
        finally:
            # Do not quit the shared test QApplication via the hub close event.
            hub.hide();hub.deleteLater();self.app.processEvents()

    def test_render_screens_when_requested(self):
        output=os.environ.get('CANSAT_GUI_OUTPUT_DIR')
        if not output:
            self.skipTest('Set CANSAT_GUI_OUTPUT_DIR to save review screenshots')
        out=Path(output);out.mkdir(parents=True,exist_ok=True)
        self.window.navigation.show_home();self.app.processEvents()
        self.assertTrue(self.window.grab().save(str(out/'project-overview.png')))
        self.window.navigation._open_workflow();self.app.processEvents()
        self.assertTrue(self.window.grab().save(str(out/'experiment-workspace.png')))

    def test_hub_dark_background_empty_state_and_compact_header(self):
        from project_hub import ProjectHub, OrbitArtwork
        hub=ProjectHub(Path(__file__).resolve().parents[1]/'app.py')
        try:
            hub.show();QTest.qWait(50)
            with patch.object(self.store,'list_projects',return_value=([],0)):
                hub.reload()
            self.app.processEvents()
            self.assertTrue(hub.empty_state.isVisible())
            self.assertFalse(hub.projects.isVisible())
            self.assertFalse(hub.open_button.isEnabled())
            self.assertFalse(hub.share_button.isEnabled())
            self.assertLessEqual(hub.findChild(OrbitArtwork).height(),96)
            image=hub.grab().toImage()
            color=image.pixelColor(5,5)
            self.assertLess(max(color.red(),color.green(),color.blue()),90)
            output=os.environ.get('CANSAT_GUI_OUTPUT_DIR')
            if output:
                out=Path(output);out.mkdir(parents=True,exist_ok=True)
                self.assertTrue(hub.grab().save(str(out/'project-hub-empty.png')))
            hub.reload();self.app.processEvents()
            self.assertFalse(hub.empty_state.isVisible())
            self.assertTrue(hub.projects.isVisible())
            for width in (820,1020):
                hub.resize(width,720);self.app.processEvents()
                self.assertEqual(hub.centralWidget().horizontalScrollBar().maximum(),0)
            if output:
                self.assertTrue(hub.grab().save(str(out/'project-hub-projects.png')))
        finally:
            hub.hide();hub.deleteLater();self.app.processEvents()

    def test_project_share_dashboard_export_and_second_pc_hub_import(self):
        from project_hub import ProjectHub
        import project_share, project_share_dialogs
        output=self.home/'team-project.cansat-project.json'
        with patch.object(QFileDialog,'getSaveFileName',return_value=(str(output),'')), patch.object(project_share_dialogs,'message',return_value=QMessageBox.Ok):
            self.window.navigation.show_home()
            self.click('projectShareCurrent')
        document=project_share.read_share(output)
        self.assertEqual(document['project']['id'],self.project.id)
        member_root=self.home/'second-pc'/'cansat_module_lab_data'
        with patch.object(self.store,'base_dir',return_value=member_root):
            hub=ProjectHub(Path(__file__).resolve().parents[1]/'app.py')
            try:
                hub.show();self.app.processEvents()
                self.assertFalse(hub.share_button.isEnabled())
                QTest.mouseClick(hub.join_button,Qt.LeftButton)
                with patch.object(QFileDialog,'getOpenFileName',return_value=(str(output),'')),patch.object(project_share_dialogs,'message',return_value=QMessageBox.Yes),patch.object(hub,'launch') as launch:
                    QTest.mouseClick(hub.import_button,Qt.LeftButton)
                    self.app.processEvents()
                    launch.assert_not_called()
                self.assertEqual(hub.projects.count(),1)
                self.assertEqual(hub.projects.currentItem().data(Qt.UserRole),self.project.id)
                self.assertTrue(hub.share_button.isEnabled())
                self.assertTrue(hub.open_button.isEnabled())
                # Re-import selects the existing project and keeps the ledger.
                ledger=self.store.read_project(self.project.id).directory/'records.json'
                before=ledger.read_bytes()
                with patch.object(QFileDialog,'getOpenFileName',return_value=(str(output),'')),patch.object(project_share_dialogs,'message',return_value=QMessageBox.Yes):
                    QTest.mouseClick(hub.import_button,Qt.LeftButton)
                self.assertEqual(hub.projects.count(),1)
                self.assertEqual(ledger.read_bytes(),before)
                destination=os.environ.get('CANSAT_GUI_OUTPUT_DIR')
                if destination:
                    self.assertTrue(hub.grab().save(str(Path(destination)/'project-sharing-hub.png')))
            finally:
                hub.hide();hub.deleteLater();self.app.processEvents()

    def test_project_share_import_cancel_preserves_draft_and_storage(self):
        from project_hub import ProjectHub
        import project_share,project_share_dialogs
        output=self.home/'cancel-project.cansat-project.json'
        project_share.export_share(self.project.id,output)
        member_root=self.home/'cancelled-second-pc'/'cansat_module_lab_data'
        with patch.object(self.store,'base_dir',return_value=member_root):
            hub=ProjectHub(Path(__file__).resolve().parents[1]/'app.py')
            try:
                hub.show();hub.name.setText('入力中のプロジェクト');self.app.processEvents()
                QTest.mouseClick(hub.join_button,Qt.LeftButton)
                with patch.object(QFileDialog,'getOpenFileName',return_value=(str(output),'')),patch.object(project_share_dialogs,'message',return_value=QMessageBox.No):
                    QTest.mouseClick(hub.import_button,Qt.LeftButton)
                self.assertFalse(member_root.exists())
                self.assertEqual(hub.name.text(),'入力中のプロジェクト')
                self.assertEqual(hub.projects.count(),0)
            finally:
                hub.hide();hub.deleteLater();self.app.processEvents()

    def test_project_share_export_cancel_and_hub_selected_id(self):
        from project_hub import ProjectHub
        import project_share,project_share_dialogs
        hub=ProjectHub(Path(__file__).resolve().parents[1]/'app.py')
        try:
            hub.show();self.app.processEvents()
            QTest.mouseClick(hub.more_toggle,Qt.LeftButton)
            for index in range(hub.projects.count()):
                if hub.projects.item(index).data(Qt.UserRole)==self.other.id:
                    hub.projects.setCurrentRow(index);break
            with patch.object(QFileDialog,'getSaveFileName',return_value=('','')),patch.object(project_share_dialogs,'message') as message:
                QTest.mouseClick(hub.share_button,Qt.LeftButton)
                message.assert_not_called()
            output=self.home/'selected-project.cansat-project.json'
            with patch.object(QFileDialog,'getSaveFileName',return_value=(str(output),'')),patch.object(project_share_dialogs,'message',return_value=QMessageBox.Ok):
                QTest.mouseClick(hub.share_button,Qt.LeftButton)
            self.assertEqual(project_share.read_share(output)['project']['id'],self.other.id)
        finally:
            hub.hide();hub.deleteLater();self.app.processEvents()


if __name__=='__main__':
    unittest.main()
