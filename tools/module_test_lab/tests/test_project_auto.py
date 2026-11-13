"""Two-PC autosync, conflict, cancellation, recovery and concurrent-save tests."""
from pathlib import Path
import base64
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import unquote

SOURCE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(SOURCE))
import project_store as store
import project_share
import project_auto_core as core
import records


class Server:
    def __init__(self):self.files={};self.private=True;self.calls=[];self.fail_put=None


class FakeAPI(core.ProjectAPI):
    def __init__(self,server):super().__init__(repository='club/data');self.server=server
    def _api(self,method,endpoint,data=None,*,allow_404=False):
        if self.cancelled():raise core.Cancelled('cancelled')
        server=self.server;server.calls.append((method,endpoint))
        if endpoint==f'repos/{self.repo}':return {'private':server.private}
        prefix=f'repos/{self.repo}/contents/'
        assert endpoint.startswith(prefix),endpoint
        path=unquote(endpoint[len(prefix):].split('?',1)[0])
        if method=='PUT':
            if server.fail_put==path:raise core.SyncError('simulated offline')
            assert path not in server.files,'remote overwrite attempted'
            server.files[path]=base64.b64decode(data['content'])
            return {'content':{'path':path}}
        if path in server.files:
            return {'type':'file','encoding':'base64','content':base64.b64encode(server.files[path]).decode()}
        children={}
        for name,raw in sorted(server.files.items()):
            if not name.startswith(path+'/'):continue
            rest=name[len(path)+1:];first=rest.split('/',1)[0]
            kind='dir' if '/' in rest else 'file'
            previous=children.get(first,{}).get('sha','')
            sha=hashlib.sha1(previous.encode()+raw).hexdigest()
            children[first]={'name':first,'type':kind,'sha':sha}
        return list(children.values()) if children else None


class ProjectAutoTests(unittest.TestCase):
    def setUp(self):
        parent=('\\\\?\\'+str(Path(tempfile.gettempdir()).resolve())) if os.name=='nt' else None
        self.temp=tempfile.TemporaryDirectory(prefix='cansat-auto-',dir=parent);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.host=self.root/'host';self.member=self.root/'member'
        self.project=store.create_project('自動共有','INO','Two-PC test',self.host/'cansat_module_lab_data')
        self.doc=core.document(self.project)
        self.joined=project_share.register(self.doc,self.member/'cansat_module_lab_data').project
        self.server=Server();self.api=FakeAPI(self.server)
        self.remote=f'{core.REMOTE}/{self.project.id}'
        self.use(self.project)
        self.sentinel=self.root/'firmware.ino';self.sentinel.write_text('team firmware')
    def use(self,project):
        if hasattr(self,'patches'):
            for p in reversed(self.patches):p.stop()
        self.patches=[patch.object(records,'DATA_DIR',project.directory),
            patch.object(records,'RECORDS_FILE',project.directory/'records.json'),
            patch.object(records,'ATTACHMENTS_DIR',project.directory/'attachments'),
            patch.dict(os.environ,{store.PROJECT_ENV:project.id})]
        for p in self.patches:p.start()
    def tearDown(self):
        self.assertEqual(self.sentinel.read_text(),'team firmware')
        for p in reversed(self.patches):p.stop()
    def record(self,name='run',attach=True):
        rec=records.new_record(scenario=name)
        sources=[]
        if attach:
            file=self.root/(rec['id']+'.csv');file.write_text('time_s,z\n0,9.8\n1,9.7\n');sources=[file]
        return records.add_record(rec,sources)
    def cycle(self,cache=None):
        from record_trash import deleted_ids
        return self.api.cycle(self.doc,records.load_records(),records.ATTACHMENTS_DIR,deleted_ids(),cache)

    def test_two_pcs_upload_catalog_join_and_receive_attachments(self):
        original=self.record()
        self.assertEqual(self.cycle()['sent'],1)
        catalog=self.api.catalog();self.assertEqual(catalog['projects'],[self.doc])
        self.use(self.joined)
        self.assertEqual(records.load_records(),[])
        result=self.cycle();self.assertEqual(core.receive(result['received'])['added'],1)
        self.assertEqual(records.load_records()[0],original)
        item=original['attachments'][0]
        self.assertTrue((records.ATTACHMENTS_DIR/original['id']/item['name']).is_file())
        self.assertEqual(core.receive(result['received'])['added'],0)

    def test_same_record_conflict_never_overwrites_either_pc(self):
        rec=self.record();self.cycle()
        remote_before=dict(self.server.files)
        changed=copy.deepcopy(rec);changed['notes']='local later edit';records.save_records([changed])
        result=self.cycle()
        self.assertEqual(result['conflicts'],[rec['id']])
        self.assertEqual(self.server.files,remote_before)
        self.assertEqual(core.receive([(rec,{a['name']:(records.ATTACHMENTS_DIR/rec['id']/a['name']).read_bytes()
                                               for a in rec['attachments']})])['conflicts'],[rec['id']])
        self.assertEqual(records.load_records(),[changed])

    def test_changed_local_data_during_network_is_preserved_at_merge(self):
        incoming=self.record();self.cycle();self.use(self.joined)
        result=self.cycle()
        local=self.record('saved while network request was running',False)
        self.assertEqual(core.receive(result['received'])['added'],1)
        self.assertEqual({r['id'] for r in records.load_records()},{incoming['id'],local['id']})

    def test_corrupt_attachment_is_not_imported(self):
        rec=self.record();self.cycle()
        self.server.files[f'{self.remote}/attachments/{rec["id"]}/{rec["attachments"][0]["name"]}']=b'BAD'
        self.use(self.joined);before=records.RECORDS_FILE.read_bytes()
        with self.assertRaises(core.SyncError):self.cycle()
        self.assertEqual(records.RECORDS_FILE.read_bytes(),before)
        self.assertEqual(list(records.ATTACHMENTS_DIR.iterdir()),[])

    def test_other_project_manifest_is_rejected(self):
        rec=self.record(False);self.cycle();path=f'{self.remote}/records/{rec["id"]}.json'
        bad=copy.deepcopy(rec);bad['project_id']='a'*32
        self.server.files[path]=core.payload(bad)
        self.use(self.joined)
        with self.assertRaises(core.SyncError):self.cycle()
        self.assertEqual(records.load_records(),[])

    def test_offline_incomplete_upload_is_retryable_and_not_visible(self):
        rec=self.record();manifest=f'{self.remote}/records/{rec["id"]}.json'
        self.server.fail_put=manifest
        with self.assertRaises(core.SyncError):self.cycle()
        self.assertNotIn(manifest,self.server.files)
        self.use(self.joined)
        self.assertEqual(self.cycle()['received'],[])
        self.use(self.project);self.server.fail_put=None
        self.assertEqual(self.cycle()['sent'],1)
        self.assertIn(manifest,self.server.files)

    def test_public_repository_blocks_all_writes(self):
        self.record();self.server.private=False
        with self.assertRaises(core.SyncError):self.cycle()
        self.assertEqual(self.server.files,{})

    def test_repeated_unchanged_sync_has_no_writes_or_backups(self):
        self.record();first=self.cycle();second=self.cycle(first['cache'])
        self.server.calls=[]
        third=self.cycle(second['cache'])
        self.assertEqual(third['sent'],0)
        self.assertTrue(all(method=='GET' for method,path in self.server.calls))
        self.assertEqual(len(self.server.calls),3) # repo privacy, metadata, directory only
        self.assertFalse((records.DATA_DIR/'.autosync/ledger-before-import.json').exists())

    def test_locally_deleted_record_is_not_resurrected(self):
        import record_trash
        rec=self.record();self.cycle()
        self.use(self.joined);job=self.cycle();core.receive(job['received'])
        record_trash.delete_selected([rec['id']],self.root/'trash')
        self.assertEqual(core.receive(job['received'])['added'],0)
        self.assertEqual(self.cycle()['received'],[])
        self.assertEqual(records.load_records(),[])

    def test_single_ledger_backup_and_interrupted_import_recovery(self):
        rec=self.record();self.cycle();self.use(self.joined)
        job=self.cycle()
        with patch.object(records,'save_records',side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):core.receive(job['received'])
        self.assertEqual(records.load_records(),[])
        self.assertEqual(core.receive(job['received'])['added'],1)
        backups=list((records.DATA_DIR/'.autosync').iterdir())
        self.assertEqual([p.name for p in backups],['ledger-before-import.json'])
        self.assertEqual(json.loads(backups[0].read_text())['records'],[])
        self.assertEqual(core.receive(job['received'])['added'],0)
        self.assertEqual(records.load_records()[0]['id'],rec['id'])

    def test_large_attachment_does_not_starve_other_records(self):
        large=[]
        for number in range(4):
            rec=self.record(str(number));large.append(rec)
            path=records.ATTACHMENTS_DIR/rec['id']/rec['attachments'][0]['name']
            path.write_bytes(b'x'*(core.MAX_SYNC_ATTACHMENT_BYTES+1))
        good=self.record('good',False)
        result=self.cycle()
        self.assertEqual(len(result['blocked']),4)
        self.assertIn(good['id'],result['confirmed'])
        self.assertEqual(result['sent'],1)

    def test_scope_settings_are_local_opt_in_and_preserved(self):
        with patch.object(store,'base_dir',return_value=self.host/'cansat_module_lab_data'):
            self.assertFalse(core.enabled(self.project.id))
            self.assertFalse((self.project.directory/'.autosync').exists())
            import project_settings
            with self.assertRaises(ValueError):core.set_enabled(self.project.id,True)
            project_settings.save(self.project.id,'club/data','main')
            core.set_enabled(self.project.id,True);self.assertTrue(core.enabled(self.project.id))
            core.set_enabled(self.project.id,False);self.assertFalse(core.enabled(self.project.id))
            self.assertFalse(core.catalog_enabled())
            project_settings.catalog(False,repository='club/data')
            core.set_catalog_enabled(True);self.assertTrue(core.catalog_enabled())

    def test_nonfinite_legacy_metric_does_not_block_valid_record(self):
        bad=self.record('old NaN metric',False);good=self.record('valid metric',False)
        bad['metrics']={'old_value':float('nan')};records.save_records([bad,good])
        self.assertIsInstance(core.digest(bad),str)
        result=self.cycle()
        self.assertIn(bad['id'],result['blocked'])
        self.assertIn(good['id'],result['confirmed'])
        self.assertNotIn(f'{self.remote}/records/{bad["id"]}.json',self.server.files)

    def test_incorrect_declared_attachment_size_stays_unsent(self):
        bad=self.record();bad['attachments'][0]['bytes']+=1;records.save_records([bad])
        result=self.cycle()
        self.assertIn(bad['id'],result['blocked'])
        self.assertNotIn(f'{self.remote}/records/{bad["id"]}.json',self.server.files)

    def test_api_backoff_headers_and_cancel_before_request(self):
        future=int(core.time.time())+250
        response=f'HTTP/2.0 429 Too Many Requests\r\nRetry-After: 120\r\nX-RateLimit-Remaining: 0\r\nX-RateLimit-Reset: {future}\r\n\r\n{{}}'
        with self.assertRaises(core.SyncError) as result:core.ProjectAPI.parse_response(response,1)
        self.assertGreaterEqual(result.exception.retry_after,250)
        api=core.ProjectAPI(repository='club/data',cancelled=lambda:True)
        with patch.object(core.subprocess,'run') as run:
            with self.assertRaises(core.Cancelled):api._api('GET','repos/CanSat-INO/INO')
            run.assert_not_called()
        self.assertEqual(core.ProjectAPI.parse_response('HTTP/2.0 200 OK\nContent-Type: application/json\n\n{"private":true}',0),{'private':True})

    def test_parallel_saves_preserve_all_records(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            ids=list(pool.map(lambda number:records.add_record(records.new_record(scenario=str(number)))['id'],range(24)))
        self.assertEqual({r['id'] for r in records.load_records()},set(ids))

    def test_separate_processes_preserve_each_others_saves(self):
        env=dict(os.environ,HOME=str(self.host),USERPROFILE=str(self.host),PYTHONPATH=str(SOURCE),
                 PYTHONDONTWRITEBYTECODE='1',CANSAT_LAB_PROJECT_ID=self.project.id)
        code='import records\nfor i in range(12):records.add_record(records.new_record(scenario=str(i)))'
        first=subprocess.Popen([sys.executable,'-c',code],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        second=subprocess.Popen([sys.executable,'-c',code],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        for process in (first,second):
            stdout,stderr=process.communicate(timeout=30)
            self.assertEqual(process.returncode,0,stderr.decode(errors='replace'))
        self.assertEqual(len(records.load_records()),24)


if __name__=='__main__':unittest.main()
