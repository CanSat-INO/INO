"""Real Qt widget tests; all records/attachments stay in a temporary HOME.

Run with the existing GUI venv: python -m unittest discover -s tests -p test_v20_workspace_gui.py -v
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QTabWidget, QPushButton, QFileDialog, QMessageBox
except ImportError as exc:
    raise unittest.SkipTest('Use the existing GUI venv (PySide6.QtTest required)') from exc

import records
from v15_sensor_tab import SensorCsvV15Tab
from v16_experiment_tab import ExperimentJournalV16Tab
from v19_compare_tab import ExperimentCompareV19Tab
from v20_workflow_tab import WorkflowV20Tab, WORKSPACE_LABEL
from v20_workflow_core import make_session, save_session


class WorkspaceGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cansat-workspace-test-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'HOME': str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)
        data = self.home / 'cansat_module_lab_data'
        self.data_patch = patch.multiple(records, DATA_DIR=data, RECORDS_FILE=data/'records.json', ATTACHMENTS_DIR=data/'attachments')
        self.data_patch.start()
        self.addCleanup(self.data_patch.stop)
        self.tabs = QTabWidget()
        self.addCleanup(self.tabs.close)
        self.host = types.SimpleNamespace(tabs=self.tabs, navigation=types.SimpleNamespace(open_tab=self.tabs.setCurrentIndex))
        self.host.v15_sensor_tab = SensorCsvV15Tab()
        self.host.v16_journal_tab = ExperimentJournalV16Tab()
        self.host.v19_compare_tab = ExperimentCompareV19Tab()
        for tab, label in ((self.host.v15_sensor_tab, 'センサー実験・ログ解析'),
                           (self.host.v16_journal_tab, '実験記録・コード版管理（v16）'),
                           (self.host.v19_compare_tab, '実験管理・仮想ログ比較（v19）')):
            self.tabs.addTab(tab, label)
        self.workflow = WorkflowV20Tab(host=self.host)
        self.tabs.addTab(self.workflow, WORKSPACE_LABEL)
        self.tabs.setCurrentWidget(self.workflow)
        self.tabs.resize(1100, 900)
        self.tabs.show()
        self.context = dict(name='静止試験01', tester='担当A', hardware='ESP32-S3 / BNO055', code_version='test123')
        for key, value in self.context.items():
            self.workflow.context_fields[key].setText(value)
        self.workflow.use_demo()
        self.app.processEvents()

    def click(self, tab, text):
        matches = [b for b in tab.findChildren(QPushButton) if b.text() == text]
        self.assertEqual(len(matches), 1, text)
        QTest.mouseClick(matches[0], Qt.LeftButton)
        self.app.processEvents()

    def test_context_handoff_and_return_without_auto_save(self):
        w = self.workflow
        self.click(w, '① 解析画面へ')
        sensor = self.host.v15_sensor_tab
        self.assertIs(self.tabs.currentWidget(), sensor)
        self.assertIsNotNone(sensor.log)
        self.assertIn('静止試験01', w.context_panels[sensor].text())
        self.click(sensor, '実験ワークスペースへ戻る')
        self.assertIs(self.tabs.currentWidget(), w)
        self.click(w, '② 実験記録票へ')
        journal = self.host.v16_journal_tab
        for key, value in self.context.items():
            self.assertEqual(getattr(journal, key).text(), value)
        self.assertEqual(journal.status.currentText(), '未判定')
        self.assertEqual(records.load_records(), [])
        self.assertIsNone(w.record_id)
        self.click(journal, '実験記録を保存')
        saved = records.load_records()
        self.assertEqual(len(saved), 1)
        self.assertEqual(w.record_id, saved[0]['id'])
        self.assertTrue((records.ATTACHMENTS_DIR / saved[0]['id']).is_dir())
        self.assertIn('台帳：保存済み', w.progress.text())
        w.memo.setPlainText('次回のメモ')
        self.assertEqual(w.record_id, saved[0]['id'])
        w.context_fields['code_version'].setText('changed')
        self.assertIsNone(w.record_id)

    def test_conflicting_journal_cancel_then_accept(self):
        w, journal = self.workflow, self.host.v16_journal_tab
        journal.name.setText('先に入力した実験')
        journal.wiring.setText('保護する配線メモ')
        journal.code_path.setText('/test-only/keep.ino')
        journal.status.setCurrentText('成功')
        before = journal._form_data()
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.No):
            w.to_journal()
        self.assertEqual(journal._form_data(), before)
        with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            w.to_journal()
        self.assertEqual(journal.name.text(), self.context['name'])
        self.assertEqual(journal.status.currentText(), '未判定')
        self.assertEqual(journal.wiring.text(), before['wiring'])
        self.assertEqual(journal.code_path.text(), before['code_path'])
        self.assertEqual(records.load_records(), [])

    def test_compare_clears_old_settings_and_carries_context(self):
        w, compare = self.workflow, self.host.v19_compare_tab
        compare.use_demo()
        compare.unit_check.setChecked(True)
        compare.shift.setValue(12)
        compare.do_compare()
        self.assertIsNotNone(compare.result)
        w.set_path(w.measured_path.text(), is_reference=True)
        self.click(w, '③ ログ比較へ（任意）')
        self.assertEqual(compare.reference_path.text(), w.measured_path.text())
        self.assertIsNone(compare.result)
        self.assertIsNone(compare.measured_log)
        self.assertEqual(compare.measured_signal.count(), 0)
        self.assertEqual(compare.shift.value(), 0)
        self.assertFalse(compare.unit_check.isChecked())
        self.assertFalse(compare.export_json_button.isEnabled())
        self.assertIn('担当A', w.context_panels[compare].text())
        compare.load_files()
        compare.unit_check.setChecked(True)
        compare.do_compare()
        self.assertIsNotNone(compare.result)
        self.assertAlmostEqual(compare.result.mae, 0)

    def test_json_roundtrip_dirty_cancel_and_no_csv_read_on_import(self):
        w = self.workflow
        target = self.home / 'workspace.json'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
            self.click(w, '作業情報をJSON保存')
        self.assertIn('保存内容と一致', w.save_status.text())
        w.context_fields['name'].setText('未保存の変更')
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(target), '')), patch.object(QMessageBox, 'question', return_value=QMessageBox.No):
            self.click(w, '作業情報をJSON読込')
        self.assertEqual(w.context_fields['name'].text(), '未保存の変更')
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(target), '')), patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes), patch('v20_workflow_tab.inspect_csv', side_effect=AssertionError('automatic CSV read')):
            self.click(w, '作業情報をJSON読込')
        self.assertEqual(w.context(), self.context)
        self.assertIsNone(w.measured_info)
        self.assertIn('保存内容と一致', w.save_status.text())
        self.assertTrue(w.verify_csvs())
        self.assertIn('保存内容と一致', w.save_status.text())
        self.assertIsNone(w.record_id)
        self.assertEqual(records.load_records(), [])

    def test_draft_without_csv_and_save_failure_keep_dirty_state(self):
        w = self.workflow
        w.set_path('')
        target = self.home / 'draft.json'
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')):
            w.export_session()
        self.assertTrue(target.exists())
        w.memo.setPlainText('変更')
        snapshot = w.saved_snapshot
        with patch.object(QFileDialog, 'getSaveFileName', return_value=(str(target), '')), patch('v20_workflow_tab.save_session', side_effect=OSError('test disk error')), patch.object(QMessageBox, 'warning'):
            w.export_session()
        self.assertEqual(snapshot, w.saved_snapshot)
        self.assertIn('未保存の変更あり', w.save_status.text())

    def test_changed_reference_is_checked_before_handoff(self):
        w = self.workflow
        self.assertTrue(w.verify_csvs())
        reference = self.home / 'bad.csv'
        reference.write_text('not a sensor log', encoding='utf-8')
        w.set_path(reference, is_reference=True)
        with patch.object(QMessageBox, 'warning'):
            w.to_compare()
        self.assertNotIn('compare', w.sent)
        self.assertIsNone(w.measured_info)

    def test_hash_mismatch_and_save_failure_do_not_claim_saved(self):
        w, journal = self.workflow, self.host.v16_journal_tab
        source = self.home / 'measured.csv'
        source.write_text('time_s,accel_x_mps2\n0,1\n1,2\n', encoding='utf-8')
        w.set_path(source)
        w.to_journal()
        with patch('v16_experiment_tab.save_experiment', side_effect=OSError('test error')), patch.object(QMessageBox, 'warning'):
            journal.save()
        self.assertIsNone(w.record_id)
        source.write_text('time_s,accel_x_mps2\n0,3\n1,4\n', encoding='utf-8')
        with patch.object(QMessageBox, 'warning'):
            w.to_sensor()
        self.assertIsNone(w.measured_info)
        self.assertEqual(w.sent, set())

    def test_legacy_json_clears_context_without_reading_csv(self):
        target = self.home / 'legacy.json'
        save_session(make_session(None, None, memo='以前の作業'), target)
        with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(target), '')), patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
            self.workflow.import_session()
        self.assertTrue(all(not value for value in self.workflow.context().values()))
        self.assertEqual(self.workflow.memo.toPlainText(), '以前の作業')
        self.assertIsNone(self.workflow.measured_info)

    def test_other_journal_record_does_not_mark_workflow_saved(self):
        self.workflow.to_journal()
        journal = self.host.v16_journal_tab
        journal.name.setText('別の実験に変更')
        journal.save()
        self.assertEqual(len(records.load_records()), 1)
        self.assertIsNone(self.workflow.record_id)

    def test_full_app_home_entries_and_workspace_layout(self):
        from app import TestLab
        window = TestLab()
        try:
            window.setFixedSize(1120, 850)
            window.show()
            QTest.qWait(50)  # Let the existing initial home-page timer settle.
            targets = ('センサー実験・ログ解析', '実験記録・コード版管理（v16）',
                       'フェーズ別ミッション・仮想試験', '実験管理・仮想ログ比較（v19）')
            for i, target in enumerate(targets, 1):
                window.navigation.show_home()
                button = window.findChild(QPushButton, f'moduleNavigationV22Quick{i}')
                self.assertIsNotNone(button)
                QTest.mouseClick(button, Qt.LeftButton)
                self.assertEqual(window.tabs.tabText(window.tabs.currentIndex()), target)
            window.navigation.show_home()
            start = window.findChild(QPushButton, 'moduleNavigationWorkflowStart')
            QTest.mouseClick(start, Qt.LeftButton)
            w = window.v20_workflow_tab
            self.assertIs(window.tabs.currentWidget(), w)
            for key, value in self.context.items():
                w.context_fields[key].setText(value)
            w.use_demo()
            w.verify_csvs()
            self.app.processEvents()
            self.assertEqual(w.scroll.horizontalScrollBar().maximum(), 0)
            for text in ('① 解析画面へ', '② 実験記録票へ', '③ ログ比較へ（任意）'):
                button = next(b for b in w.findChildren(QPushButton) if b.text() == text)
                self.assertFalse(button.visibleRegion().isEmpty())
            if os.environ.get('CANSAT_GUI_OUTPUT_DIR'):
                out = Path(os.environ['CANSAT_GUI_OUTPUT_DIR'])
                out.mkdir(parents=True, exist_ok=True)
                window.grab().save(str(out / 'v20-workspace.png'))
                w.scroll.verticalScrollBar().setValue(w.scroll.verticalScrollBar().maximum())
                self.app.processEvents()
                window.grab().save(str(out / 'v20-workspace-save.png'))
                w.scroll.verticalScrollBar().setValue(0)
                w.to_sensor()
                self.app.processEvents()
                window.grab().save(str(out / 'v15-context.png'))
                window.setFixedSize(1120, 1250)
                w.to_journal()
                self.app.processEvents()
                window.grab().save(str(out / 'v16-context.png'))
                window.setFixedSize(1120, 850)
                w.to_compare()
                self.app.processEvents()
                window.grab().save(str(out / 'v19-context.png'))
        finally:
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.Yes):
                window.close()


if __name__ == '__main__':
    unittest.main()
