"""Opt-in GitHub project sharing. Network jobs never change the local ledger."""
from __future__ import annotations
import base64
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from github_sync import GitHubSync, SyncError, MAX_SYNC_ATTACHMENT_BYTES, MAX_REMOTE_MANIFEST_BYTES, _check_filename
import project_share
import project_store as store
import records
import project_settings
import project_transport as transport
import shared_packages

REMOTE = 'data/ino/projects'
BATCH = 3
INTERVAL = 60


class Cancelled(SyncError):
    pass


def document(project):
    return project_share.document(project)


def settings_path(project_id):
    return project_settings.path(project_id)


def enabled(project_id):
    return project_settings.read(project_id)['enabled']


def set_enabled(project_id,value):
    project_settings.set_enabled(project_id,value)


def catalog_enabled():
    return project_settings.catalog()['enabled']


def set_catalog_enabled(value):
    old=project_settings.catalog()
    if value and not old['repository']:raise ValueError('取得先リポジトリを指定してください。')
    project_settings.catalog(False,repository=old['repository'],branch=old['branch'],enabled=value)


def payload(record,storage=None):
    return (json.dumps({'format':records.FORMAT,'version':records.FORMAT_VERSION,'records':[record],**({'storage':storage} if storage else {})},
                       ensure_ascii=False,indent=2,sort_keys=True,allow_nan=False)+'\n').encode('utf-8')


def digest(record):
    try:raw=payload(record)
    except ValueError:
        # Legacy JSON may contain NaN. Detect its local changes without allowing
        # it through validate_record or blocking other valid experiments.
        raw=json.dumps(record,ensure_ascii=False,sort_keys=True).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def validate_record(record, project_id):
    if not isinstance(record,dict) or record.get('project_id') != project_id:
        raise SyncError('別プロジェクトの記録は自動共有しません。')
    rid=record.get('id')
    if not isinstance(rid,str) or not store.ID_RE.fullmatch(rid):
        raise SyncError('実験IDが不正です。')
    if len(payload(record)) > MAX_REMOTE_MANIFEST_BYTES:
        raise SyncError('実験記録が大きすぎるため未送信です。')
    items=record.get('attachments',[])
    if not isinstance(items,list) or len(items)>20:
        raise SyncError('添付は1件の実験につき20個までです。')
    seen=set()
    for item in items:
        if not isinstance(item,dict):
            raise SyncError('添付情報が不正です。')
        name=item.get('name');_check_filename(name)
        if name.casefold() in seen or not re.fullmatch('[0-9a-f]{64}',str(item.get('sha256',''))):
            raise SyncError('添付名またはSHA256が不正です。')
        if 'bytes' in item and (type(item['bytes']) is not int or item['bytes']<0):
            raise SyncError('添付サイズの情報が不正です。')
        seen.add(name.casefold())
    refs=record.get('shared_files',[])
    if not isinstance(refs,list) or len(refs)>20:raise SyncError('共有ZIPの件数が不正です。')
    for ref in refs:shared_packages.validate_reference(ref,project_id,rid)
    return rid


class ProjectAPI(GitHubSync):
    """Short, cancellable requests, paced writes, and server-directed backoff."""
    def __init__(self, repository=None,branch='main',cancelled=lambda:False):
        if repository is None:repository,branch=project_settings.current_destination()
        repository,branch=project_settings.destination(repository,branch)
        super().__init__(repository,branch)
        self.cancelled=cancelled
        self.last_write=0.0

    def _api(self, method, endpoint, data=None, *, allow_404=False):
        if self.cancelled():
            raise Cancelled('同期を停止しました。保存済みデータはPC内に残っています。')
        if method != 'GET':
            while time.monotonic()-self.last_write < 1:
                if self.cancelled():raise Cancelled('同期を停止しました。')
                time.sleep(.05)
        command=['gh','api','--hostname','github.com','--include','--method',method,
                 '-H','Accept: application/vnd.github+json',endpoint]
        if data is not None:command+=['--input','-']
        try:
            response=subprocess.run(command,input=json.dumps(data) if data is not None else None,
                capture_output=True,text=True,encoding='utf-8',timeout=15,
                env=dict(os.environ,GH_PROMPT_DISABLED='1',GIT_TERMINAL_PROMPT='0'))
        except FileNotFoundError as exc:
            error=SyncError('GitHub接続用のghが見つかりません。');error.reason='cli_missing'
            raise error from exc
        except (OSError,subprocess.TimeoutExpired) as exc:
            error=SyncError('GitHubへ接続できません。PC内の保存は継続できます。');error.reason='network'
            raise error from exc
        if method!='GET':self.last_write=time.monotonic()
        if response.returncode and not response.stdout.lstrip().startswith('HTTP/'):
            hint=(response.stderr or '').lower()
            error=SyncError('GitHubへの接続を確認できません。')
            if response.returncode==4 or 'gh auth login' in hint or 'not logged' in hint:error.reason='auth'
            elif any(word in hint for word in ('resolve host','connection','timeout','tls handshake')):error.reason='network'
            else:error.reason='response'
            raise error
        return self.parse_response(response.stdout,response.returncode,allow_404)

    @staticmethod
    def parse_response(stdout,returncode,allow_404=False):
        header,separator,body=stdout.replace('\r\n','\n').partition('\n\n')
        match=re.match(r'HTTP/\S+ (\d{3})',header)
        if not match or not separator:
            error=SyncError('GitHubの応答を確認できません。接続と認証を確認してください。');error.reason='response'
            raise error
        code=int(match[1]);headers={}
        for line in header.splitlines()[1:]:
            if ':' in line:
                key,value=line.split(':',1);headers[key.lower()]=value.strip()
        if code==404 and allow_404:return None
        if returncode or code>=400:
            error=SyncError('GitHubの権限・通信制限・更新競合を確認してください。未送信データはPC内に残ります。')
            error.http_status=code
            if code==401:error.reason='auth'
            elif code==429 or (code==403 and (headers.get('x-ratelimit-remaining')=='0' or 'retry-after' in headers)):error.reason='rate'
            elif code==403:error.reason='permission'
            elif code==404:error.reason='repository'
            elif code in (409,422):error.reason='conflict'
            elif code>=500:error.reason='network'
            else:error.reason='unknown'
            delay=60
            try:
                delay=max(delay,int(headers.get('retry-after','0')))
                if headers.get('x-ratelimit-remaining')=='0':
                    delay=max(delay,int(headers.get('x-ratelimit-reset','0'))-int(time.time())+1)
            except ValueError:
                delay=max(delay,3600)
            if code in (401,403):delay=max(delay,300)
            if code==429 and 'retry-after' not in headers:delay=max(delay,3600)
            error.retry_after=delay
            raise error
        try:return json.loads(body) if body.strip() else {}
        except ValueError as exc:
            error=SyncError('GitHubからJSON以外の応答が届きました。');error.reason='response'
            raise error from exc

    def listing(self,path):
        items=self._api('GET',self._contents_url(path,ref=True),allow_404=True)
        if items is None:return []
        if not isinstance(items,list) or len(items)>=1000:
            raise SyncError('共有一覧の形式または件数上限を確認してください。')
        return items

    def catalog(self, cache=None):
        info=self.repository_info()  # Read-only catalog works for Public and Private.
        cache=cache or {};new={};result=[]
        entries=self.listing(REMOTE)
        if len(entries)>100:raise SyncError('プロジェクトが100件を超えています。一覧の管理方式を確認してください。')
        for entry in entries:
            pid=entry.get('name','')
            if entry.get('type')!='dir' or not store.ID_RE.fullmatch(pid):continue
            old=cache.get(pid)
            if old and old[0]==entry.get('sha'):
                doc=old[1]
            else:
                raw=self._get_file(f'{REMOTE}/{pid}/project.json')
                if raw is None or len(raw)>project_share.MAX_BYTES:continue
                doc=json.loads(raw)
                metadata=project_share.validate(doc)
                if metadata['id']!=pid:raise SyncError('共有一覧のプロジェクトIDが一致しません。')
            new[pid]=(entry.get('sha'),doc);result.append(doc)
        return {'projects':result,'cache':new,'private':info['private']}

    def cycle(self,doc,local,attachment_root,deleted,cache=None,shared_root="",public_consent=None):
        project_id=project_share.validate(doc)['id']
        if any(not isinstance(r,dict) or not isinstance(r.get('id'),str) for r in local):
            raise SyncError('ローカル台帳のIDを確認してください。')
        if len({r['id'] for r in local})!=len(local):raise SyncError('ローカル台帳に重複IDがあります。')
        root=f'{REMOTE}/{project_id}'
        info=self.repository_info(require_push=True)
        if not info['private'] and not project_settings.public_consent_valid(
                public_consent, self.repo, self.branch, project_id):
            raise SyncError('公開GitHubへの送信は未許可です。公開内容と共有先を確認し、公開への同意を行ってください。')
        raw=self._get_file(root+'/project.json')
        if raw is None:
            self._put_new_file(root+'/project.json',
                (json.dumps(doc,ensure_ascii=False,sort_keys=True)+'\n').encode(),
                f'projects: share {project_id[:8]}')
            metadata_differs=False
        else:
            if len(raw)>project_share.MAX_BYTES:raise SyncError('共有プロジェクト情報が大きすぎます。')
            remote=project_share.validate(json.loads(raw))
            if remote['id']!=project_id:raise SyncError('共有先のプロジェクトIDが異なります。')
            metadata_differs=remote!=project_share.validate(doc)
        listing={e['name'][:-5]:e for e in self.listing(root+'/records')
                 if e.get('type')=='file' and isinstance(e.get('name'),str)
                 and e['name'].endswith('.json') and store.ID_RE.fullmatch(e['name'][:-5])}
        cache={k:v for k,v in (cache or {}).items() if k in listing}
        conflicts=set();blocked={};received=[];confirmed={};sent=0;transports=[]
        local={r['id']:r for r in local}
        # Only a small batch is transferred per cycle. Cached blob IDs avoid
        # downloading the same manifests or attachments every minute.
        processed=0
        for rid,rec in sorted(local.items()):
            try:
                validate_record(rec,project_id)
                fingerprint=digest(rec)
            except (SyncError,ValueError) as exc:
                blocked[rid]=str(exc);continue
            entry=listing.get(rid);known=cache.get(rid)
            if entry and known and known[0]==entry.get('sha'):
                if fingerprint==known[1]:confirmed[rid]=fingerprint
                else:conflicts.add(rid)
                continue
            if processed>=BATCH:continue
            processed+=1
            if entry:
                remote,storage=self.read_envelope(root,rid)
                if storage:transports.append((remote,storage))
                remote_digest=digest(remote);cache[rid]=(entry.get('sha'),remote_digest)
                if fingerprint==remote_digest:confirmed[rid]=fingerprint
                else:conflicts.add(rid)
                continue
            try:
                content,storage=transport.prepare(rec,attachment_root,shared_root,self.cancelled)
                if len(payload(rec,storage))>MAX_REMOTE_MANIFEST_BYTES:raise ValueError('ZIPの登録情報を含む実験記録が大きすぎます。')
            except (ValueError,OSError) as exc:
                blocked[rid]=str(exc);processed-=1;continue
            if storage:transports.append((rec,storage))
            for name,raw in content.items():
                self._put_new_file(f'{root}/attachments/{rid}/{name}',raw,f'projects: attach {rid[:8]}')
            self._put_new_file(f'{root}/records/{rid}.json',payload(rec,storage),f'projects: record {rid[:8]}')
            confirmed[rid]=fingerprint;sent+=1
        for rid,entry in sorted(listing.items()):
            if rid in local or rid in deleted:continue
            if len(received)>=BATCH:break
            rec,storage=self.read_envelope(root,rid)
            heavy=set(storage["heavy_names"]) if storage else set()
            content={}
            for item in rec.get('attachments',[]):
                if item['name'] in heavy:continue
                raw=self._get_file(f'{root}/attachments/{rid}/{item["name"]}')
                if raw is None or len(raw)>MAX_SYNC_ATTACHMENT_BYTES or hashlib.sha256(raw).hexdigest()!=item['sha256']:
                    raise SyncError('受信した添付のサイズ・SHA256が一致しません。既存データは上書きしません。')
                if 'bytes' in item and item['bytes']!=len(raw):raise SyncError('受信した添付サイズの記録が一致しません。')
                content[item['name']]=raw
            received.append((rec,content,storage))
            cache[rid]=(entry.get('sha'),digest(rec))
        return {'cache':cache,'confirmed':confirmed,'sent':sent,'conflicts':sorted(conflicts),
                'blocked':blocked,'received':received,'metadata_differs':metadata_differs,'transports':transports}

    def read_record(self,root,rid):
        return self.read_envelope(root,rid)[0]

    def read_envelope(self,root,rid):
        raw=self._get_file(f'{root}/records/{rid}.json')
        if raw is None or len(raw)>MAX_REMOTE_MANIFEST_BYTES:raise SyncError('共有実験の形式・サイズが不正です。')
        obj=json.loads(raw)
        if (not isinstance(obj,dict) or obj.get('format')!=records.FORMAT or obj.get('version')!=records.FORMAT_VERSION
                or not isinstance(obj.get('records'),list) or len(obj['records'])!=1):
            raise SyncError('共有実験の形式が不正です。')
        rec=obj['records'][0];pid=root.rsplit('/',1)[1]
        if validate_record(rec,pid)!=rid:raise SyncError('共有実験のIDが一致しません。')
        storage=transport.validate(obj.get("storage"),rec)
        return rec,storage


def receive(items):
    if not store.active_id():
        raise ValueError('未分類の台帳では自動共有を利用できません。')
    return _receive_locked(items)


@records.locked
def _receive_locked(items):
    """Merge on the GUI thread, re-reading current records under a short lock."""
    from record_trash import deleted_ids
    project_id=store.active_id()
    if not project_id:raise ValueError('未分類の台帳では自動共有を利用できません。')
    current=records.load_records();known={r['id']:r for r in current};deleted=deleted_ids()
    additions=[];conflicts=[]
    for entry in items:
        if len(entry) not in (2,3):raise ValueError('受信形式が不正です。')
        record,content=entry[:2];storage=entry[2] if len(entry)==3 else None
        rid=validate_record(record,project_id)
        transport.validate(storage,record)
        heavy=set(storage['heavy_names']) if storage else set()
        if rid in deleted:continue
        if rid in known:
            if known[rid]!=record:conflicts.append(rid)
            else:transport.save(record,storage)
            continue
        expected={a['name']:a['sha256'] for a in record.get('attachments',[]) if a['name'] not in heavy}
        if set(content)!=set(expected):raise ValueError('受信した添付の一覧が一致しません。')
        for name,raw in content.items():
            if len(raw)>MAX_SYNC_ATTACHMENT_BYTES or hashlib.sha256(raw).hexdigest()!=expected[name]:
                raise ValueError('受信添付の検証に失敗しました。')
        for item in record.get('attachments',[]):
            if item['name'] not in heavy and 'bytes' in item and item['bytes']!=len(content[item['name']]):
                raise ValueError('受信した添付サイズの記録が一致しません。')
        target=store._safe_chain(records.ATTACHMENTS_DIR/rid)
        if target.exists():
            if not target.is_dir() or {p.name for p in target.iterdir()}!=set(content):
                raise ValueError('同名の添付フォルダーを保護するため取り込みを止めました。')
            for name,raw in content.items():
                path=store._safe_chain(target/name)
                if not path.is_file() or path.read_bytes()!=raw:
                    raise ValueError('既存の添付ファイルは上書きしません。')
        additions.append((copy.deepcopy(record),content,target,storage));known[rid]=record
    if not additions:return {'added':0,'conflicts':conflicts}
    # One rolling, ledger-only recovery file. Never duplicate all attachments,
    # sessions or exports; previous user-created backups are untouched.
    backup=store._safe_chain(records.DATA_DIR/'.autosync/ledger-before-import.json')
    store.atomic_json(backup,{'format':records.FORMAT,'version':records.FORMAT_VERSION,'records':current})
    for rec,content,target,storage in additions:
        transport.save(rec,storage)
        if not target.exists():
            with tempfile.TemporaryDirectory(prefix='.auto-',dir=records.ATTACHMENTS_DIR) as temp:
                stage=Path(temp)/'attachments';stage.mkdir()
                for name,raw in content.items():(stage/name).write_bytes(raw)
                os.rename(stage,target)
        current.append(rec)
    records.save_records(current)
    return {'added':len(additions),'conflicts':conflicts}
