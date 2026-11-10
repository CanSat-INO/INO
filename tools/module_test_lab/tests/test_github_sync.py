"""Offline tests for GitHub sync: no GitHub network calls or credentials."""
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import github_sync
import records


class FakeGitHub(github_sync.GitHubSync):
    def __init__(self):
        super().__init__()
        self.files = {}

    def _api(self, method, endpoint, data=None, *, allow_404=False):
        if endpoint == f"repos/{self.repo}":
            return {"full_name": self.repo, "default_branch": "main", "private": True}
        if endpoint.startswith(f"repos/{self.repo}/branches/"):
            return {"name": self.branch}
        prefix = f"repos/{self.repo}/contents/"
        assert endpoint.startswith(prefix), endpoint
        path = "/".join(unquote(x) for x in endpoint[len(prefix):].split("?", 1)[0].split("/"))
        if method == "PUT":
            assert path not in self.files
            self.files[path] = base64.b64decode(data["content"])
            return {"content": {"path": path}}
        if path in self.files:
            return {"type": "file", "content": base64.b64encode(self.files[path]).decode("ascii"),
                    "encoding": "base64"}
        if path in (github_sync.REMOTE_RECORDS, github_sync.LEGACY_REMOTE_RECORDS):
            names = sorted({p[len(path)+1:] for p in self.files if p.startswith(path + "/")})
            return [{"name": name, "type": "file"} for name in names]
        return None


class GitHubSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp.name)
        self.data = self.tmp / "database"
        self.patches = [
            patch.object(records, "DATA_DIR", self.data),
            patch.object(records, "RECORDS_FILE", self.data / "records.json"),
            patch.object(records, "ATTACHMENTS_DIR", self.data / "attachments"),
        ]
        for patcher in self.patches:
            patcher.start()
        self.sync = FakeGitHub()

    def tearDown(self):
        for patcher in reversed(self.patches):
            patcher.stop()
        self.temp.cleanup()

    def create_record(self):
        rec = records.new_record(module="着地検知", tester="研究班A", status="成功")
        sample_log = self.tmp / "run.csv"
        sample_log.write_text("t,imu\n1,9.8\n", encoding="utf-8")
        records.add_record(rec, [sample_log])
        return rec

    def test_push_then_pull_with_attachment_and_dedup(self):
        rec = self.create_record()
        first = self.sync.upload([rec["id"]])
        self.assertEqual(first, {"uploaded": 1, "skipped": 0})
        self.assertEqual(self.sync.upload([rec["id"]])["skipped"], 1)
        self.assertIn(f"{github_sync.REMOTE_RECORDS}/{rec['id']}.json", self.sync.files)
        self.assertIn(f"{github_sync.REMOTE_ATTACHMENTS}/{rec['id']}/run.csv", self.sync.files)
        records.save_records([])
        (self.data / "attachments" / rec["id"] / "run.csv").unlink()
        result = self.sync.download()
        self.assertEqual(result["added"], 1)
        self.assertEqual(len(records.load_records()), 1)
        self.assertTrue((self.data / "attachments" / rec["id"] / "run.csv").exists())
        self.assertEqual(self.sync.download()["skipped"], 1)

    def test_conflicting_id_not_overwritten(self):
        rec = self.create_record()
        self.sync.upload([rec["id"]])
        rec2 = records.load_records()[0]
        rec2["observed"] = "updated later"
        records.save_records([rec2])
        before = dict(self.sync.files)
        with self.assertRaises(github_sync.SyncError):
            self.sync.upload([rec["id"]])
        self.assertEqual(before, self.sync.files)
        result = self.sync.download()
        self.assertEqual(result["conflicts"], 1)
        self.assertEqual(records.load_records()[0]["observed"], "updated later")

    def test_bad_remote_checksum_no_import(self):
        rec = self.create_record()
        self.sync.upload([rec["id"]])
        self.sync.files[f"{github_sync.REMOTE_ATTACHMENTS}/{rec['id']}/run.csv"] = b"tampered"
        records.save_records([])
        with self.assertRaises(github_sync.SyncError):
            self.sync.download()
        self.assertEqual(len(records.load_records()), 0)

    def test_invalid_repo_and_empty_push(self):
        with self.assertRaises(github_sync.SyncError):
            github_sync.GitHubSync("not a repo")
        with self.assertRaises(github_sync.SyncError):
            self.sync.upload([])

    def test_no_remote_records(self):
        self.assertEqual(self.sync.download()["remote"], 0)
        self.assertFalse((self.tmp / "database_backups").exists())

    def test_download_keeps_backup_and_existing_data(self):
        original = self.create_record()
        self.sync.upload([original['id']])
        # A second local record should survive a download.
        other = records.new_record(scenario='existing-only')
        records.add_record(other)
        # Simulate another member's new record arriving remotely.
        incoming = records.new_record(scenario='remote-only')
        self.sync.files[f"{github_sync.REMOTE_RECORDS}/{incoming['id']}.json"] = self.sync._record_payload(incoming)
        result = self.sync.download()
        self.assertEqual(result['added'], 1)
        self.assertTrue(result['backup'])
        backup = Path(result['backup'])
        self.assertTrue((backup / 'records.json').is_file())
        self.assertTrue((backup / 'attachments' / original['id'] / 'run.csv').is_file())
        self.assertEqual({r['id'] for r in records.load_records()},
                         {original['id'], other['id'], incoming['id']})

    def test_orphan_attachment_never_overwritten(self):
        rec = self.create_record()
        self.sync.upload([rec['id']])
        records.save_records([])
        orphan = records.ATTACHMENTS_DIR / rec['id'] / 'run.csv'
        orphan.write_text('local orphan must survive', encoding='utf-8')
        with self.assertRaisesRegex(github_sync.SyncError, '保護'):
            self.sync.download()
        self.assertEqual(orphan.read_text(encoding='utf-8'), 'local orphan must survive')
        self.assertEqual(records.load_records(), [])

    def test_backup_failure_prevents_import(self):
        incoming = records.new_record(scenario='remote-only')
        self.sync.files[f"{github_sync.REMOTE_RECORDS}/{incoming['id']}.json"] = self.sync._record_payload(incoming)
        with patch.object(self.sync, '_backup_before_download',
                          side_effect=github_sync.SyncError('backup failed')):
            with self.assertRaises(github_sync.SyncError):
                self.sync.download()
        self.assertEqual(records.load_records(), [])

    def test_public_repository_upload_blocked(self):
        rec = self.create_record()
        old_api = self.sync._api
        def public_api(method, endpoint, data=None, *, allow_404=False):
            if endpoint == f'repos/{self.sync.repo}':
                return {'full_name': self.sync.repo, 'private': False}
            return old_api(method, endpoint, data, allow_404=allow_404)
        self.sync._api = public_api
        with self.assertRaisesRegex(github_sync.SyncError, '非公開'):
            self.sync.upload([rec['id']])
        self.assertEqual(self.sync.files, {})

    def test_unknown_visibility_upload_blocked(self):
        rec = self.create_record()
        old_api = self.sync._api
        def unknown_api(method, endpoint, data=None, *, allow_404=False):
            if endpoint == f'repos/{self.sync.repo}':
                return {'full_name': self.sync.repo}
            return old_api(method, endpoint, data, allow_404=allow_404)
        self.sync._api = unknown_api
        with self.assertRaises(github_sync.SyncError):
            self.sync.upload([rec['id']])


    def test_download_legacy_record_with_attachment(self):
        rec = self.create_record()
        self.sync.upload([rec["id"]])
        new_manifest = f"{github_sync.REMOTE_RECORDS}/{rec['id']}.json"
        new_attachment = f"{github_sync.REMOTE_ATTACHMENTS}/{rec['id']}/run.csv"
        self.sync.files[f"{github_sync.LEGACY_REMOTE_RECORDS}/{rec['id']}.json"] = self.sync.files.pop(new_manifest)
        self.sync.files[f"{github_sync.LEGACY_REMOTE_ATTACHMENTS}/{rec['id']}/run.csv"] = self.sync.files.pop(new_attachment)
        records.save_records([])
        (self.data / 'attachments' / rec['id'] / 'run.csv').unlink()
        result = self.sync.download()
        self.assertEqual(result['remote'], 1)
        self.assertEqual(result['added'], 1)
        self.assertTrue((self.data / 'attachments' / rec['id'] / 'run.csv').exists())

    def test_upload_skips_identical_legacy_record_without_migration(self):
        rec = self.create_record()
        old_path = f"{github_sync.LEGACY_REMOTE_RECORDS}/{rec['id']}.json"
        self.sync.files[old_path] = self.sync._record_payload(rec)
        self.assertEqual(self.sync.upload([rec['id']]), {'uploaded': 0, 'skipped': 1})
        self.assertNotIn(f"{github_sync.REMOTE_RECORDS}/{rec['id']}.json", self.sync.files)

    def test_upload_blocks_different_legacy_record(self):
        rec = self.create_record()
        old = dict(rec)
        old['notes'] = 'different old record'
        old_path = f"{github_sync.LEGACY_REMOTE_RECORDS}/{rec['id']}.json"
        self.sync.files[old_path] = self.sync._record_payload(old)
        before = dict(self.sync.files)
        with self.assertRaises(github_sync.SyncError):
            self.sync.upload([rec['id']])
        self.assertEqual(self.sync.files, before)

    def test_conflicting_new_and_old_manifest_rejected_on_download(self):
        rec = self.create_record()
        self.sync.upload([rec['id']])
        old = dict(rec)
        old['notes'] = 'different old record'
        self.sync.files[f"{github_sync.LEGACY_REMOTE_RECORDS}/{rec['id']}.json"] = self.sync._record_payload(old)
        before = records.load_records()
        with self.assertRaises(github_sync.SyncError):
            self.sync.download()
        self.assertEqual(records.load_records(), before)

    def test_identical_manifest_in_two_paths_is_one_remote_record(self):
        rec = self.create_record()
        self.sync.upload([rec['id']])
        same = self.sync.files[f"{github_sync.REMOTE_RECORDS}/{rec['id']}.json"]
        self.sync.files[f"{github_sync.LEGACY_REMOTE_RECORDS}/{rec['id']}.json"] = same
        result = self.sync.download()
        self.assertEqual(result['remote'], 1)
        self.assertEqual(result['skipped'], 1)


if __name__ == "__main__":
    unittest.main()
