"""Regression guard for visible delete/restore controls on small screens.

Structural test avoids Qt and never reads or mutates experiment data.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class VisibleDeleteButtonsTests(unittest.TestCase):
    def test_ledger_places_delete_above_table(self):
        text = (ROOT / 'app.py').read_text(encoding='utf-8')
        body = text.split('    def build_ledger_tab(self):', 1)[1].split('    def build_v14_1_modules_tab(', 1)[0]
        self.assertIn('選択記録を削除（退避）', body)
        self.assertIn('退避ZIPから復元', body)
        self.assertLess(body.index('lay.addLayout(cleanup_row)'), body.index('self.table = QTableWidget()'))
        self.assertLess(body.index('self.github_status = QLabel('), body.index('lay.addLayout(cleanup_row)'))
        self.assertEqual(body.count('lay.addLayout(cleanup_row)'), 1)

    def test_journal_places_delete_above_splitter(self):
        text = (ROOT / 'v16_experiment_tab.py').read_text(encoding='utf-8')
        body = text.split('class ExperimentJournalV16Tab(QWidget):', 1)[1].split('    def github_action(', 1)[0]
        self.assertIn('選択記録を削除（退避）', body)
        self.assertIn('退避ZIPから復元', body)
        self.assertLess(body.index('root.addLayout(cleanup_row)'), body.index('splitter = QSplitter(Qt.Vertical)'))
        self.assertLess(body.index('root.addWidget(self.github_message)'), body.index('root.addLayout(cleanup_row)'))
        self.assertEqual(body.count('root.addLayout(cleanup_row)'), 1)

if __name__ == '__main__':
    unittest.main()
