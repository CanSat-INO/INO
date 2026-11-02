"""Source-only regression checks; no GUI, GitHub access or user data required."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SyncUIWiringTests(unittest.TestCase):
    def test_v16_ui_uses_existing_host_sync_worker(self):
        tree = ast.parse((ROOT / 'v16_experiment_tab.py').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ExperimentJournalV16Tab')
        names = {n.name for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        self.assertTrue({'github_action', 'set_sync_busy', 'set_sync_status'}.issubset(names))
        source = (ROOT / 'v16_experiment_tab.py').read_text(encoding='utf-8')
        self.assertIn("self.host.start_github_sync('upload', record_ids=", source)
        self.assertIn("self.host.start_github_sync(action)", source)
        self.assertNotIn('subprocess.run(', source)

    def test_app_keeps_old_ledger_and_refreshes_journal(self):
        source = (ROOT / 'app.py').read_text(encoding='utf-8')
        self.assertIn('def start_github_sync(self, action, record_ids=None):', source)
        self.assertIn('self.v16_journal_tab.reload()', source)
        self.assertIn('self.v16_journal_tab.set_sync_busy(True)', source)
        self.assertIn('self.v16_journal_tab.set_sync_busy(False)', source)
        self.assertIn('self.build_ledger_tab()', source)
        self.assertIn('self.build_v16_journal_tab()', source)


if __name__ == '__main__':
    unittest.main()
