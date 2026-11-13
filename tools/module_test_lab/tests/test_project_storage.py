"""Hybrid Git/ZIP transport and per-PC destination isolation, temporary data only."""
from pathlib import Path
import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import project_store as store
import project_share as share
import project_settings as settings
import shared_packages as packages
import project_transport as transport
import project_auto_core as core
import records
from test_project_auto import Server,FakeAPI


class StorageTests(unittest.TestCase):
    def setUp(self):
        parent=('\\\\?\\'+str(Path(tempfile.gettempdir()).resolve())) if os.name=='nt' else None
        self.temp=tempfile.TemporaryDirectory(prefix='cansat-zip-',dir=parent);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.host=self.root/'host';self.member=self.root/'member'
        self.shared=self.root/'shared';self.shared.mkdir()
        self.project=store.create_project('INO 2026','A','',self.host/'cansat_module_lab_data',year=2026,team='INO')
        self.doc=core.document(self.project)
        self.joined=share.register(self.doc,self.member/'cansat_module_lab_data').project
        self.server=Server();self.api=FakeAPI(self.server);self.patches=[];self.use(self.project,self.host)
    def use(self,project,home):
        for p in reversed(self.patches):p.stop()
        self.patches=[patch.object(store,'base_dir',return_value=home/'cansat_module_lab_data'),
            patch.object(records,'DATA_DIR',project.directory),patch.object(records,'RECORDS_FILE',project.directory/'records.json'),
            patch.object(records,'ATTACHMENTS_DIR',project.directory/'attachments'),patch.dict(os.environ,{store.PROJECT_ENV:project.id})]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
    def source(self,name='model.sdf',raw=b'<sdf>test</sdf>'):
        p=self.root/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_bytes(raw);return p
    def create(self,**kwargs):
        return packages.create(self.shared,self.project.id,'a'*32,[self.source()],**kwargs)
    def cycle(self):
        return self.api.cycle(self.doc,records.load_records(),records.ATTACHMENTS_DIR,set(),shared_root=str(self.shared))
    def test_project_year_team_share_and_old_projects(self):
        self.assertEqual((self.joined.year,self.joined.team),(2026,'INO'))
        old=store.create_project('old');self.assertIsNone(old.year);self.assertEqual(old.team,'')
        updated=store.update_group(old.id,2027,'new');self.assertEqual(updated.id,old.id)
        for bad in (True,1999,2201,'2026'):
            with self.assertRaises(ValueError):store.project_year(bad)
    def test_settings_opt_in_preserves_folder_and_independent_projects(self):
        other=store.create_project('another',year=2027,team='CanSat')
        settings.save(self.project.id,'https://github.com/club/ino.git','data',str(self.shared))
        settings.save(other.id,'club/next','main')
        core.set_enabled(self.project.id,True)
        value=settings.read(self.project.id)
        self.assertEqual((value['repository'],value['branch'],value['shared_root']),('club/ino','data',str(self.shared)))
        self.assertTrue(value['enabled']);self.assertFalse(settings.read(other.id)['enabled'])
        self.assertNotIn(str(self.shared),json.dumps(core.document(self.project)))
        settings.save(self.project.id,'club/new','main',str(self.shared));self.assertFalse(core.enabled(self.project.id))
    def test_unconfigured_named_project_never_silently_targets_ino(self):
        with self.assertRaises(ValueError):settings.current_destination()
        with self.assertRaises(ValueError):core.ProjectAPI()
        store.atomic_json(settings.path(self.project.id),{'format':'cansat-auto-settings-1','enabled':True})
        self.assertFalse(core.enabled(self.project.id))
        with self.assertRaises(ValueError):core.set_enabled(self.project.id,True)
    def test_invalid_destinations_and_local_data_folder_refused(self):
        for repo,branch in (('https://evil.example/owner/repo','main'),('club/repo','../main'),('club/repo','-option'),('club/repo/extra','main')):
            with self.assertRaises(ValueError):settings.destination(repo,branch)
        before=(self.project.directory/'records.json').read_bytes()
        with self.assertRaises(ValueError):settings.save(self.project.id,'club/repo','main',str(self.project.directory))
        self.assertEqual((self.project.directory/'records.json').read_bytes(),before)
    def test_catalog_sources_are_explicit_and_remembered(self):
        self.assertFalse(settings.catalog()['enabled'])
        with self.assertRaises(ValueError):core.set_catalog_enabled(True)
        settings.catalog(False,repository='club/ino',branch='records');core.set_catalog_enabled(True)
        self.assertEqual(settings.catalog(),{'repository':'club/ino','branch':'records','enabled':True})
    def test_create_verify_relative_reference_and_retry_no_duplicate(self):
        ref=self.create();self.assertEqual(packages.verify(self.shared,ref,self.project.id,'a'*32),self.shared/ref['relative_path'])
        second=self.create();self.assertEqual(ref,second)
        self.assertEqual(len(list(self.shared.rglob('bundle.zip'))),1)
        self.assertNotIn(str(self.root),json.dumps(ref))
        self.assertEqual(self.source().read_bytes(),b'<sdf>test</sdf>')
    def test_models_preserve_structure_without_git_or_python_caches(self):
        folder=self.root/'robot';self.source('robot/meshes/body.stl',b'body');self.source('robot/model.sdf',b'model')
        self.source('robot/.git/secret',b'exclude');self.source('robot/__pycache__/x.pyc',b'exclude')
        ref=packages.create(self.shared,self.project.id,'a'*32,[folder],folder=True)
        self.assertEqual(ref['kind'],'models');self.assertEqual(ref['file_count'],2)
        packages.verify(self.shared,ref,self.project.id,'a'*32)
    def test_cancel_and_disk_full_leave_no_completed_zip(self):
        with self.assertRaises(ValueError):self.create(cancelled=lambda:True)
        with patch.object(packages.shutil,'disk_usage',return_value=type('Usage',(),{'free':0})()):
            with self.assertRaises(ValueError):self.create()
        self.assertFalse(list(self.shared.rglob('bundle.zip')))
    def test_path_escape_wrong_project_and_missing_or_corrupt_zip_refused(self):
        ref=self.create()
        with self.assertRaises(ValueError):packages.validate_reference(ref,'b'*32,'a'*32)
        for name in ('../x','/abs','a\\b','a//b','a/./b','C:x'):
            with self.assertRaises(ValueError):packages.relative(name)
        wrong=copy.deepcopy(ref);wrong['relative_path']='../escape'
        with self.assertRaises(ValueError):packages.verify(self.shared,wrong,self.project.id,'a'*32)
        other=self.root/'other';other.mkdir()
        with self.assertRaisesRegex(ValueError,'待ち'):packages.verify(other,ref,self.project.id,'a'*32)
        (self.shared/ref['relative_path']).write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'SHA256'):packages.verify(self.shared,ref,self.project.id,'a'*32)
    def test_duplicate_names_and_recursive_shared_root_refused(self):
        a=self.source('a/model.sdf');b=self.source('b/MODEL.sdf')
        with self.assertRaises(ValueError):packages.create(self.shared,self.project.id,'a'*32,[a,b])
        with self.assertRaises(ValueError):packages.create(self.shared,self.project.id,'a'*32,[self.root],folder=True)
    def test_heavy_attachment_goes_only_to_zip_and_received_record_stays_identical(self):
        file=self.source('big.csv',b'0123456789'*(110*1024))
        small=self.source('small.csv',b'time,z\n0,9.8')
        original=records.add_record(records.new_record(scenario='large data'),[file,small])
        result=self.cycle();self.assertEqual(result['sent'],1)
        self.assertFalse(any(p.endswith('/big.csv') for p in self.server.files))
        wire=json.loads(self.server.files[f'{core.REMOTE}/{self.project.id}/records/{original["id"]}.json'])
        self.assertEqual(wire['records'],[original]);self.assertNotIn(str(self.shared),json.dumps(wire))
        self.assertEqual(wire['storage']['heavy_names'],['big.csv'])
        self.use(self.joined,self.member);incoming=self.cycle()
        self.assertEqual(core.receive(incoming['received'])['added'],1)
        self.assertEqual(records.load_records(),[original])
        target=records.ATTACHMENTS_DIR/original['id']
        self.assertTrue((target/'small.csv').is_file());self.assertFalse((target/'big.csv').exists())
        value=transport.load(original)
        transport.restore(self.shared,original,value)
        self.assertEqual((target/'big.csv').read_bytes(),file.read_bytes())
        self.assertEqual(records.load_records(),[original])
    def test_zip_retry_after_network_loss_reuses_same_package(self):
        original=records.add_record(records.new_record(),[self.source('big.dat',b'x'*1000000)])
        self.server.fail_put=f'{core.REMOTE}/{self.project.id}/records/{original["id"]}.json'
        with self.assertRaises(core.SyncError):self.cycle()
        self.assertEqual(len(list(self.shared.rglob('bundle.zip'))),1)
        self.server.fail_put=None;self.assertEqual(self.cycle()['sent'],1)
        self.assertEqual(len(list(self.shared.rglob('bundle.zip'))),1)
    def test_missing_shared_root_leaves_large_record_pending_and_small_record_sends(self):
        big=records.add_record(records.new_record(),[self.source('big.dat',b'x'*1000000)])
        small=records.add_record(records.new_record())
        result=self.api.cycle(self.doc,records.load_records(),records.ATTACHMENTS_DIR,set())
        self.assertIn(big['id'],result['blocked']);self.assertIn(small['id'],result['confirmed'])
        self.assertEqual(len(records.load_records()),2)
    def test_receive_without_zip_does_not_download_or_expand_it(self):
        original=records.add_record(records.new_record(),[self.source('big.dat',b'x'*1000000)])
        self.cycle();self.use(self.joined,self.member)
        self.shared.rename(self.root/'unavailable')
        incoming=self.cycle();core.receive(incoming['received'])
        self.assertEqual(records.load_records(),[original])
        self.assertFalse((records.ATTACHMENTS_DIR/original['id']/'big.dat').exists())
        with self.assertRaises(ValueError):transport.restore(self.shared,original,transport.load(original))
    def test_restore_refuses_existing_different_attachment(self):
        original=records.add_record(records.new_record(),[self.source('big.dat',b'x'*1000000)])
        self.cycle();self.use(self.joined,self.member);core.receive(self.cycle()['received'])
        path=records.ATTACHMENTS_DIR/original['id']/'big.dat';path.write_bytes(b'member local')
        with self.assertRaises(ValueError):transport.restore(self.shared,original,transport.load(original))
        self.assertEqual(path.read_bytes(),b'member local')
    def test_material_reference_shares_without_binary_git_payload(self):
        rec=records.new_record(mode='共有資料');ref=packages.create(self.shared,self.project.id,rec['id'],[self.source()])
        rec['shared_files']=[ref];records.add_record(rec)
        self.assertEqual(self.cycle()['sent'],1)
        self.assertFalse(any('/attachments/' in p for p in self.server.files))
        self.use(self.joined,self.member);core.receive(self.cycle()['received'])
        self.assertEqual(records.load_records(),[rec]);packages.verify(self.shared,ref,rec['project_id'],rec['id'])
    def test_forged_transport_cannot_reference_other_record_or_changed_canonical_record(self):
        rec=records.add_record(records.new_record(),[self.source('big.dat',b'x'*1000000)])
        self.cycle();self.use(self.joined,self.member);entry=self.cycle()['received'][0]
        bad=copy.deepcopy(entry[2]);bad['shared_zip']['record_id']='b'*32
        with self.assertRaises(ValueError):core.receive([(entry[0],entry[1],bad)])
        changed=copy.deepcopy(entry[0]);changed['notes']='tampered'
        with self.assertRaises(ValueError):core.receive([(changed,entry[1],entry[2])])
        self.assertEqual(records.load_records(),[])

    def test_source_changed_before_zip_creation_is_not_published_as_original(self):
        source=self.source('big.dat',b'x'*1000000)
        rec=records.add_record(records.new_record(),[source])
        original_create=packages.create
        def mutate_then_create(*args,**kwargs):
            (records.ATTACHMENTS_DIR/rec['id']/'big.dat').write_bytes(b'y'*1000000)
            return original_create(*args,**kwargs)
        with patch.object(packages,'create',side_effect=mutate_then_create):result=self.cycle()
        self.assertIn(rec['id'],result['blocked'])
        self.assertNotIn(f'{core.REMOTE}/{self.project.id}/records/{rec["id"]}.json',self.server.files)

    def test_zip_changed_after_verification_is_not_restored(self):
        rec=records.add_record(records.new_record(),[self.source('big.dat',b'x'*1000000)])
        self.cycle();self.use(self.joined,self.member);core.receive(self.cycle()['received'])
        value=transport.load(rec);original_verify=packages.verify
        def mutate_after_verify(*args,**kwargs):
            path=original_verify(*args,**kwargs)
            with zipfile.ZipFile(path) as archive:manifest=archive.read('bundle.json')
            with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('bundle.json',manifest);archive.writestr('files/big.dat',b'y'*1000000)
            return path
        with patch.object(packages,'verify',side_effect=mutate_after_verify):
            with self.assertRaises(ValueError):transport.restore(self.shared,rec,value)
        self.assertFalse((records.ATTACHMENTS_DIR/rec['id']/'big.dat').exists())
        self.assertEqual(records.load_records(),[rec])


if __name__=='__main__':unittest.main()
