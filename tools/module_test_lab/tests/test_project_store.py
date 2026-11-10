"""Project isolation tests. Standard library only; no production HOME or network."""
from __future__ import annotations
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import project_store as store


class ProjectStoreTests(unittest.TestCase):
    def setUp(self):
        temp_parent = ('\\\\?\\' + str(Path(tempfile.gettempdir()).resolve())) if os.name == 'nt' else None
        self.temp = tempfile.TemporaryDirectory(prefix='cansat-project-test-', dir=temp_parent)
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / 'cansat_module_lab_data'
        self.root.mkdir()
        self.legacy = self.root / 'records.json'
        self.legacy.write_text('{"legacy_sentinel": true}', encoding='utf-8')
        self.original = self.legacy.read_bytes()

    def project(self, name='Project A'):
        return store.create_project(name, 'Team', 'Offline test', self.root)

    def child(self, code, project=None, check=True):
        env = dict(os.environ, HOME=str(self.home), USERPROFILE=str(self.home), PYTHONPATH=str(ROOT), PYTHONIOENCODING='utf-8')
        if project:
            env[store.PROJECT_ENV] = project.id
        else:
            env.pop(store.PROJECT_ENV, None)
        result = subprocess.run([sys.executable, '-c', code], env=env, cwd=ROOT,
                                text=True, capture_output=True, encoding='utf-8')
        if check and result.returncode:
            self.fail(result.stderr or result.stdout)
        return result

    def tearDown(self):
        self.assertEqual(self.original, self.legacy.read_bytes())

    def test_listing_does_not_create_project_folders(self):
        before = set(self.root.iterdir())
        self.assertEqual(store.list_projects(self.root), ([], 0))
        self.assertEqual(set(self.root.iterdir()), before)

    def test_create_reload_and_duplicate_names_have_distinct_ids(self):
        first, second = self.project(), self.project()
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(store.read_project(first.id, self.root), first)
        self.assertEqual(len(store.list_projects(self.root)[0]), 2)
        self.assertEqual(json.loads((first.directory/'records.json').read_text())['records'], [])
        self.assertTrue((first.directory/'sessions').is_dir())

    def test_invalid_name_creates_nothing(self):
        for name in ('', ' ', 'x'*121, 'a\x00b', 'a\nb'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.project(name)
        self.assertFalse((self.root/'projects').exists())

    def test_invalid_id_and_untrusted_metadata_rejected(self):
        for value in ('../legacy', '/tmp', 'A'*32, '', 'x', 'a'*31):
            with self.assertRaises(ValueError):
                store.read_project(value, self.root)
        project = self.project()
        metadata = project.directory/'project.json'
        obj = json.loads(metadata.read_text())
        obj['id'] = 'a'*32 if project.id != 'a'*32 else 'b'*32
        metadata.write_text(json.dumps(obj))
        self.assertEqual(store.list_projects(self.root), ([], 1))

    def test_symlink_project_refused(self):
        external = self.home/'external'; external.mkdir()
        parent = self.root/'projects'; parent.mkdir()
        try:
            (parent/('a'*32)).symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest('Symlink creation is not permitted on this host')
        with self.assertRaises(ValueError):
            store.read_project('a'*32, self.root)
        self.assertEqual(list(external.iterdir()), [])

    def test_storage_and_restart_are_isolated(self):
        first, second = self.project('A'), self.project('B')
        result = self.child('import records; r=records.new_record(scenario="A experiment"); records.add_record(r); print(r["project_id"])', first)
        self.assertEqual(result.stdout.strip(), first.id)
        self.assertEqual(self.child('import records; print(len(records.load_records()))', first).stdout.strip(), '1')
        self.assertEqual(self.child('import records; print(len(records.load_records()))', second).stdout.strip(), '0')

    def test_attachment_export_and_cross_project_import(self):
        first, second = self.project('A'), self.project('B')
        output = self.home/'a.zip'
        log = self.home/'a.csv'; log.write_text('time_s,a\n0,1\n1,2\n')
        code = ('from pathlib import Path; import records; r=records.new_record(scenario="A"); '
                f'records.add_record(r,[Path({str(log)!r})]); records.export_bundle([r["id"]],Path({str(output)!r}))')
        self.child(code, first)
        before = (second.directory/'records.json').read_bytes()
        failure = self.child(f'import records; from pathlib import Path; records.import_bundle(Path({str(output)!r}))', second, check=False)
        self.assertNotEqual(failure.returncode, 0)
        self.assertEqual(before, (second.directory/'records.json').read_bytes())
        self.assertEqual(list((second.directory/'attachments').iterdir()), [])

    def test_exports_sessions_backups_and_trash_have_separate_paths(self):
        first, second = self.project('A'), self.project('B')
        code = 'import project_store as p,json; print(json.dumps([p.export_path("x.json"),p.export_path("s.json",session=True),str(p.backup_dir()),str(p.trash_dir())]))'
        a = json.loads(self.child(code, first).stdout)
        b = json.loads(self.child(code, second).stdout)
        self.assertTrue(all(first.id in value for value in a))
        self.assertTrue(all(second.id in value for value in b))
        self.assertTrue(all(x != y for x,y in zip(a,b)))

    def test_wrong_project_low_level_write_is_rejected(self):
        first, second = self.project('A'), self.project('B')
        with patch.dict(os.environ, {store.PROJECT_ENV:first.id}):
            with self.assertRaises(ValueError):
                store.validate_record_project({'project_id':second.id})
            source = {'id':'a'*32}
            imported = store.validate_record_project(source, allow_unclassified=True)
            self.assertEqual(imported['project_id'], first.id)
            self.assertNotIn('project_id', source)

    def test_workflow_project_tag_roundtrip_and_legacy_compatibility(self):
        from v20_workflow_core import make_session, save_session, load_session
        path = self.home/'session.json'
        old = make_session(None, None)
        save_session(old, path)
        self.assertEqual(load_session(path), old)
        old['project_id'] = self.project().id
        save_session(old, path)
        self.assertEqual(load_session(path), old)
        old['project_id'] = '../other'
        with self.assertRaises(ValueError):
            save_session(old, path)

    def test_network_download_skips_other_projects(self):
        project = self.project()
        code = '''import sys,json
sys.path.insert(0, "tests")
import records,github_sync
from test_github_sync import FakeGitHub
s=FakeGitHub()
foreign=records.new_record(scenario="Foreign")
foreign["project_id"]="f"*32
mine=records.new_record(scenario="Mine")
for rec in (foreign,mine):
    s.files[f"{github_sync.REMOTE_RECORDS}/{rec['id']}.json"]=s._record_payload(rec)
r=s.download()
assert r['added']==1 and r['skipped_project']==1,r
assert [x['scenario'] for x in records.load_records()]==['Mine']
print('OK')
'''
        self.assertEqual(self.child(code, project).stdout.strip(), 'OK')

    def test_v16_real_sample_save_is_project_scoped(self):
        project = self.project()
        code = '''import records
from pathlib import Path
from v16_experiment_core import save_experiment,MODULES,PHASES
r=save_experiment(name='BNO055 scoped',module=MODULES[0],phase=PHASES[0],tester='Team',hardware='BNO055',code_version='test',csv_path=Path('v15_samples/imu_bno055_sample.csv'))
assert r['project_id']==records.project_store.active_id()
assert len(records.load_records())==1
assert (records.ATTACHMENTS_DIR/r['id']/'imu_bno055_sample.csv').is_file()
print('OK')
'''
        self.assertEqual(self.child(code,project).stdout.strip(),'OK')

    def test_delete_restore_stays_in_same_project(self):
        first,second=self.project('A'),self.project('B')
        archive=self.child('import records,record_trash; r=records.new_record(scenario="A"); records.add_record(r); print(record_trash.delete_selected([r["id"]])["archive"])',first).stdout.strip()
        before=(second.directory/'records.json').read_bytes()
        failure=self.child(f'import record_trash; from pathlib import Path; record_trash.restore_archive(Path({archive!r}))',second,check=False)
        self.assertNotEqual(failure.returncode,0)
        self.assertEqual(before,(second.directory/'records.json').read_bytes())
        self.assertEqual(self.child(f'import record_trash; from pathlib import Path; print(record_trash.restore_archive(Path({archive!r}))["restored"])',first).stdout.strip(),'1')


if __name__ == '__main__':
    unittest.main()
