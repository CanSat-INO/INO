"""Offline deletion/restore tests; temporary records only. Never touches user data."""
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import records
import record_trash
import github_sync


class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data = self.root / 'data'
        self.archives = self.root / 'trash'
        self.patches = [patch.object(records, 'DATA_DIR', self.data),
                        patch.object(records, 'RECORDS_FILE', self.data / 'records.json'),
                        patch.object(records, 'ATTACHMENTS_DIR', self.data / 'attachments')]
        for p in self.patches: p.start()
    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.temp.cleanup()
    def create(self, label, files=True):
        rec = records.new_record(scenario=label)
        if files:
            original = self.root / (label + '.csv')
            original.write_text('time,imu\n0,9.8\n', encoding='utf-8')
            records.add_record(rec, [original])
        else: records.add_record(rec)
        return rec
    def test_selected_delete_preserves_other_and_archives_all_files(self):
        first = self.create('first')
        second = self.create('second')
        orphan = records.ATTACHMENTS_DIR / first['id'] / 'extra.bin'
        orphan.write_bytes(b'extra')
        outcome = record_trash.delete_selected([first['id']], self.archives)
        self.assertEqual(outcome['deleted'], 1)
        self.assertEqual([r['id'] for r in records.load_records()], [second['id']])
        self.assertFalse((records.ATTACHMENTS_DIR / first['id']).exists())
        self.assertTrue((records.ATTACHMENTS_DIR / second['id']).exists())
        with zipfile.ZipFile(outcome['archive']) as z:
            self.assertIn('attachments/' + first['id'] + '/extra.bin', z.namelist())
        self.assertEqual(record_trash.deleted_ids(), {first['id']})
        restored = record_trash.restore_archive(Path(outcome['archive']))
        self.assertEqual(restored['restored'], 1)
        self.assertEqual({r['id'] for r in records.load_records()}, {first['id'], second['id']})
        self.assertEqual(orphan.read_bytes(), b'extra')
        self.assertEqual(record_trash.deleted_ids(), set())

    def test_deleted_remote_id_is_ignored_on_download(self):
        from test_github_sync import FakeGitHub
        sync = FakeGitHub()
        rec = self.create('shared')
        sync.upload([rec['id']])
        record_trash.delete_selected([rec['id']], self.archives)
        pulled = sync.download()
        self.assertEqual(pulled['remote'], 1)
        self.assertEqual(pulled['skipped_deleted'], 1)
        self.assertEqual(pulled['added'], 0)
        self.assertEqual(records.load_records(), [])

    def test_none_selected_and_invalid_id_change_nothing(self):
        r = self.create('keep')
        for ids in [[], ['../../etc/passwd'], [r['id'], 'bad']]:
            with self.assertRaises(record_trash.TrashError):
                record_trash.delete_selected(ids, self.archives)
            self.assertEqual(records.load_records()[0]['id'], r['id'])
        self.assertFalse(self.archives.exists())

    def test_archive_failure_does_not_delete(self):
        r = self.create('keep')
        (self.data / 'attachments' / r['id'] / 'danger').symlink_to(self.root / 'outside')
        with self.assertRaisesRegex(record_trash.TrashError, 'シンボリック'):
            record_trash.delete_selected([r['id']], self.archives)
        self.assertEqual(len(records.load_records()), 1)
        self.assertFalse(self.archives.exists())

    def test_restore_refuses_existing_record_without_overwrite(self):
        r = self.create('keep')
        result = record_trash.delete_selected([r['id']], self.archives)
        record_trash.restore_archive(Path(result['archive']))
        with self.assertRaisesRegex(record_trash.TrashError, '既にあります'):
            record_trash.restore_archive(Path(result['archive']))
        self.assertEqual(len(records.load_records()), 1)

    def test_restore_refuses_orphan_directory(self):
        r = self.create('keep')
        result = record_trash.delete_selected([r['id']], self.archives)
        orphan = records.ATTACHMENTS_DIR / r['id']
        orphan.mkdir(parents=True)
        (orphan / 'sentinel.txt').write_text('do not touch')
        with self.assertRaisesRegex(record_trash.TrashError, '同名の添付'):
            record_trash.restore_archive(Path(result['archive']))
        self.assertEqual((orphan / 'sentinel.txt').read_text(), 'do not touch')
        self.assertEqual(records.load_records(), [])

    def test_backup_zip_tamper_is_detected(self):
        r = self.create('keep')
        result = record_trash.delete_selected([r['id']], self.archives)
        archive = Path(result['archive'])
        archive.write_bytes(b'not a zip')
        with self.assertRaises(zipfile.BadZipFile):
            record_trash.restore_archive(archive)
        self.assertEqual(records.load_records(), [])


if __name__ == '__main__': unittest.main()
