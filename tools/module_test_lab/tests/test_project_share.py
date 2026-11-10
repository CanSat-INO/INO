"""Two-PC project registration and existing experiment handoff in isolated homes."""
from pathlib import Path
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
import project_share as share
import project_store as store


class ProjectShareTests(unittest.TestCase):
    def setUp(self):
        parent = ('\\\\?\\' + str(Path(tempfile.gettempdir()).resolve())) if os.name == 'nt' else None
        self.temp = tempfile.TemporaryDirectory(prefix='cansat-share-test-', dir=parent)
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.host_home = self.base / 'host'
        self.member_home = self.base / 'member'
        self.host = self.host_home / 'cansat_module_lab_data'
        self.member = self.member_home / 'cansat_module_lab_data'
        self.member.mkdir(parents=True)
        (self.member / 'records.json').write_text('legacy ledger sentinel')
        self.project = store.create_project('CanSat 実験', 'INO Team', 'センサー評価', self.host)
        self.path = self.base / 'project.cansat-project.json'
        share.export_share(self.project.id, self.path, self.host)
        self.document = share.read_share(self.path)

    def tearDown(self):
        self.assertEqual((self.member / 'records.json').read_text(), 'legacy ledger sentinel')

    def files(self, folder):
        return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                for p in folder.rglob('*') if p.is_file()}

    def child(self, home, code, project_id):
        env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), PYTHONPATH=str(SOURCE),
                   CANSAT_LAB_PROJECT_ID=project_id, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([sys.executable, '-c', code], env=env, cwd=SOURCE,
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_register_same_id_on_second_pc_with_empty_ledger(self):
        result = share.register(self.document, self.member)
        self.assertTrue(result.created)
        self.assertEqual((result.project.id, result.project.name, result.project.owner, result.project.purpose),
                         (self.project.id, self.project.name, self.project.owner, self.project.purpose))
        self.assertNotEqual(result.project.directory, self.project.directory)
        self.assertEqual(json.loads((result.project.directory / 'records.json').read_text())['records'], [])

    def test_export_is_metadata_only_even_when_experiments_exist(self):
        (self.project.directory / 'records.json').write_text('PRIVATE EXPERIMENT')
        (self.project.directory / 'sessions/private.json').write_text('SECRET SESSION')
        (self.project.directory / 'attachments/private.csv').write_text('SECRET DATA')
        output = self.base / 'minimal.json'
        size = share.export_share(self.project.id, output, self.host)
        self.assertLess(size, 4096)
        raw = output.read_text(encoding='utf-8')
        for secret in ('PRIVATE', 'SECRET', str(self.host_home)):
            self.assertNotIn(secret, raw)
        self.assertEqual(set(json.loads(raw)['project']), {'id', 'name', 'owner', 'purpose'})

    def test_repeat_preserves_records_attachments_sessions_and_metadata(self):
        result = share.register(self.document, self.member)
        directory = result.project.directory
        (directory / 'records.json').write_text('local experiment sentinel')
        (directory / 'attachments/local.csv').write_text('keep my attachment')
        (directory / 'sessions/work.json').write_text('keep my draft')
        before = self.files(directory)
        changed = copy.deepcopy(self.document)
        changed['project']['name'] = 'Host renamed project'
        changed['project']['owner'] = 'Different owner'
        repeated = share.register(changed, self.member)
        self.assertFalse(repeated.created)
        self.assertTrue(repeated.metadata_differs)
        self.assertEqual(self.files(directory), before)
        self.assertEqual(len(store.list_projects(self.member)[0]), 1)

    def test_same_name_different_ids_remain_separate(self):
        local = store.create_project(self.project.name, root=self.member)
        imported = share.register(self.document, self.member)
        self.assertNotEqual(local.id, imported.project.id)
        self.assertEqual(len(store.list_projects(self.member)[0]), 2)

    def test_existing_incomplete_folder_is_never_overwritten(self):
        target = self.member / 'projects' / self.project.id
        target.mkdir(parents=True)
        (target / 'records.json').write_text('unfinished but valuable')
        before = self.files(self.member)
        with self.assertRaises(ValueError):
            share.register(self.document, self.member)
        self.assertEqual(self.files(self.member), before)

    def test_untrusted_fields_rejected_before_creating_directories(self):
        invalid = []
        for value in ('../other', 'A'*32, '/tmp/project'):
            obj = copy.deepcopy(self.document); obj['project']['id'] = value; invalid.append(obj)
        obj = copy.deepcopy(self.document);obj['project']['directory'] = '/tmp';invalid.append(obj)
        obj = copy.deepcopy(self.document);obj['project']['name'] = 'x\x00y';invalid.append(obj)
        obj = copy.deepcopy(self.document);obj['project']['name'] = 'a'*121;invalid.append(obj)
        invalid.extend([None, [], {'format':'unknown','project':{}}, {'format':share.FORMAT,'project':[]}])
        for obj in invalid:
            with self.subTest(obj=obj):
                with self.assertRaises(ValueError):share.register(obj, self.member)
        self.assertFalse((self.member / 'projects').exists())

    def test_read_duplicate_keys_oversize_and_experiment_json_rejected(self):
        for raw in ('{"format":"x","format":"y","project":{}}', ' '* (share.MAX_BYTES+1),
                    '{"format":"cansat-module-lab-records","records":[]}', 'not json'):
            path = self.base / 'invalid.json';path.write_text(raw)
            with self.assertRaises(ValueError):share.read_share(path)
        self.assertFalse((self.member / 'projects').exists())

    def test_export_never_replaces_existing_file(self):
        before = self.path.read_bytes()
        with self.assertRaises(FileExistsError):share.export_share(self.project.id, self.path, self.host)
        self.assertEqual(self.path.read_bytes(), before)

    def test_read_preview_has_no_registration_side_effects(self):
        before = self.files(self.member)
        self.assertEqual(share.validate(share.read_share(self.path))['id'], self.project.id)
        self.assertEqual(self.files(self.member), before)
        self.assertFalse((self.member / 'projects').exists())

    def test_io_failure_never_advertises_partial_project(self):
        with patch.object(share.os, 'rename', side_effect=OSError('simulated full disk')):
            with self.assertRaises(OSError):share.register(self.document, self.member)
        self.assertEqual(store.list_projects(self.member)[0], [])
        self.assertEqual(list((self.member / 'projects').glob('.share-*')), [])

    def test_link_target_is_refused(self):
        projects = self.member / 'projects';projects.mkdir()
        external = self.base / 'external';external.mkdir()
        try:
            (projects / self.project.id).symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest('Symlink creation is not permitted on this host')
        with self.assertRaises(ValueError):share.register(self.document, self.member)
        self.assertEqual(list(external.iterdir()), [])

    def test_registered_member_receives_real_experiment_with_existing_zip(self):
        share.register(self.document, self.member)
        attachment = self.base / 'sensor.csv';attachment.write_text('time_s,z\n0,9.8\n1,9.7\n')
        bundle = self.base / 'experiment.zip'
        host_code = ('from pathlib import Path;import records;'
                     'r=records.new_record(scenario="Shared real experiment");'
                     f'records.add_record(r,[Path({str(attachment)!r})]);'
                     f'records.export_bundle([r["id"]],Path({str(bundle)!r}));print(r["id"])')
        record_id = self.child(self.host_home, host_code, self.project.id)
        self.assertEqual(self.child(self.member_home, 'import records;print(len(records.load_records()))', self.project.id), '0')
        code = ('from pathlib import Path;import records;'
                f'assert records.import_bundle(Path({str(bundle)!r}))["added"]==1;'
                f'assert records.import_bundle(Path({str(bundle)!r}))["skipped"]==1;'
                'r=records.load_records()[0];'
                f'assert r["id"]=={record_id!r} and r["project_id"]=={self.project.id!r};'
                'assert (records.ATTACHMENTS_DIR/r["id"]/"sensor.csv").read_text()=="time_s,z\\n0,9.8\\n1,9.7\\n";print("OK")')
        self.assertEqual(self.child(self.member_home, code, self.project.id), 'OK')


if __name__ == '__main__':
    unittest.main()
