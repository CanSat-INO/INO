"""ZIP transport metadata, separate from the unchanged experiment record."""
import hashlib
import json
from pathlib import Path
import os
import tempfile
import zipfile
import records
import project_store as store
import shared_packages as packages
from github_sync import MAX_SYNC_ATTACHMENT_BYTES


def fingerprint(record):
    raw=json.dumps(record,ensure_ascii=False,sort_keys=True,allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def validate(value,record):
    if value is None:return None
    if not isinstance(value,dict) or set(value)!={'shared_zip','heavy_names','record_sha256'}:
        raise ValueError('ZIPの配送情報が不正です。')
    packages.validate_reference(value['shared_zip'],record['project_id'],record['id'])
    if value['shared_zip']['kind']!='attachments' or value['record_sha256']!=fingerprint(record):
        raise ValueError('ZIPと実験記録が一致しません。')
    names=value['heavy_names'];items={a['name']:a for a in record.get('attachments',[])}
    if (not isinstance(names,list) or not names
            or any(not isinstance(n,str) or n not in items for n in names) or len(names)!=len(set(names))):
        raise ValueError('ZIPの添付一覧が不正です。')
    if value['shared_zip']['file_count']!=len(names):raise ValueError('ZIPの添付数が一致しません。')
    if any(type(items[n].get('bytes')) is not int for n in names):raise ValueError('ZIP添付のサイズ情報が必要です。')
    if sum(items[n]['bytes'] for n in names)!=value['shared_zip']['source_bytes']:
        raise ValueError('ZIPの元データサイズが一致しません。')
    return value


def sidecar(record):
    return store._safe_chain(store.read_project(record['project_id']).directory/'.autosync/transports'/f"{record['id']}.json")


def save(record,value):
    if value is not None:store.atomic_json(sidecar(record),validate(value,record))


def load(record):
    path=sidecar(record)
    if not path.exists():return None
    if path.stat().st_size>16384:raise ValueError('ZIPの配送情報が大きすぎます。')
    return validate(json.loads(path.read_text(encoding='utf-8')),record)


def prepare(record,attachment_root,shared_root,cancelled):
    content={};heavy=[]
    for item in record.get('attachments',[]):
        path=store._safe_chain(Path(attachment_root)/record['id']/item['name'])
        if not path.is_file():raise ValueError('添付ファイルがありません: '+item['name'])
        size=path.stat().st_size
        if item.get('bytes',size)!=size or packages.file_hash(path,cancelled)!=item['sha256']:
            raise ValueError('保存時から添付が変わっています: '+item['name'])
        if size>MAX_SYNC_ATTACHMENT_BYTES:
            if 'bytes' not in item:raise ValueError('大きい添付のサイズ情報がありません。ZIP登録から共有してください。')
            heavy.append(path)
        else:
            raw=path.read_bytes()
            if len(raw)>MAX_SYNC_ATTACHMENT_BYTES or len(raw)!=size or hashlib.sha256(raw).hexdigest()!=item['sha256']:
                raise ValueError('処理中に添付が変わりました: '+item['name'])
            content[item['name']]=raw
    transport=None
    if heavy:
        ref=packages.create(shared_root,record['project_id'],record['id'],heavy,cancelled=cancelled)
        transport={'shared_zip':ref,'heavy_names':[p.name for p in heavy],'record_sha256':fingerprint(record)}
        validate(transport,record)
        with zipfile.ZipFile(packages.locate(shared_root,ref,record['project_id'],record['id'])) as archive:
            check_manifest(archive,record,transport)
    return content,transport


def check_manifest(archive,record,value):
    if archive.getinfo('bundle.json').file_size>packages.MAX_MANIFEST:raise ValueError('ZIPの一覧が大きすぎます。')
    manifest=json.loads(archive.read('bundle.json'))
    expected={a['name']:a for a in record['attachments'] if a['name'] in value['heavy_names']}
    actual={a['path']:a for a in manifest['files']}
    if set(actual)!=set(expected) or any(actual[n]['sha256']!=a['sha256'] or actual[n]['bytes']!=a['bytes'] for n,a in expected.items()):
        raise ValueError('ZIP内容が実験の添付情報と一致しません。')
    return expected


def restore(root,record,value,*,cancelled=lambda:False):
    """Materialize verified flat attachments only on explicit user request."""
    value=validate(value,record)
    if value is None:raise ValueError('復元できる添付ZIPがありません。')
    path=packages.verify(root,value['shared_zip'],record['project_id'],record['id'],cancelled=cancelled)
    with zipfile.ZipFile(path) as archive:
        expected=check_manifest(archive,record,value)
        # Stage fully before touching the existing attachments. Never overwrite.
        records.setup_data()
        with tempfile.TemporaryDirectory(prefix='.zip-restore-',dir=records.ATTACHMENTS_DIR) as temp:
            for name in expected:
                digest=hashlib.sha256();length=0
                with archive.open('files/'+name) as incoming, (Path(temp)/name).open('wb') as output:
                    while True:
                        packages.check_cancel(cancelled);chunk=incoming.read(1024*1024)
                        if not chunk:break
                        length+=len(chunk)
                        if length>expected[name]['bytes']:raise ValueError('復元中の添付サイズが一致しません。')
                        digest.update(chunk);output.write(chunk)
                if length!=expected[name]['bytes'] or digest.hexdigest()!=expected[name]['sha256']:
                    raise ValueError('復元中の添付SHA256が一致しません。')
            with records.transaction():
                current={r['id']:r for r in records.load_records()}
                if current.get(record['id'])!=record:raise ValueError('実験が変更・削除されたため復元を中止しました。')
                target=store._safe_chain(records.ATTACHMENTS_DIR/record['id']);target.mkdir(exist_ok=True)
                for name,item in expected.items():
                    existing=store._safe_chain(target/name)
                    if existing.exists() and (not existing.is_file() or packages.file_hash(existing)!=item['sha256']):
                        raise ValueError('既存の添付ファイルは上書きしません。')
                for name in expected:
                    existing=target/name
                    if not existing.exists():
                        # Link is exclusive, so even another process cannot be overwritten.
                        os.link(Path(temp)/name,existing)
    return path
