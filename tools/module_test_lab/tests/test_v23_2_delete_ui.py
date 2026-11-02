"""Static GUI integration checks, no Qt system/display required."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class DeleteUiTests(unittest.TestCase):
    def test_existing_app_keeps_navigation_and_sync(self):
        text = (ROOT / 'app.py').read_text(encoding='utf-8')
        for fragment in ['ModuleNavigation(self)', 'build_v16_journal_tab()',
                         'start_github_sync', 'self.refresh_ledger()',
                         'def delete_local_selected(', 'def restore_local_archive(',
                         '選択記録を削除（退避）', '退避ZIPから復元']:
            self.assertIn(fragment, text)
    def test_journal_uses_host_and_keeps_existing_records(self):
        text = (ROOT / 'v16_experiment_tab.py').read_text(encoding='utf-8')
        for fragment in ['experiment_records(', 'def github_action(',
                         'def delete_selected_local(', 'def restore_local(',
                         'host.delete_local_selected(', 'host.restore_local_archive()']:
            self.assertIn(fragment, text)
    def test_sync_skips_local_deleted_ids(self):
        text = (ROOT / 'github_sync.py').read_text(encoding='utf-8')
        for fragment in ['from record_trash import deleted_ids',
                         'if rid in local_deleted and rid not in local:',
                         'skipped_deleted += 1']:
            self.assertIn(fragment, text)

if __name__ == '__main__': unittest.main()
