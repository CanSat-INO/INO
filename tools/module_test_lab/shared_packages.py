"""Immutable ZIP packages in a user-selected folder. No cloud SDK or extraction."""
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import tempfile
import zipfile
import stat
import project_store as store

FORMAT='cansat-shared-zip-1'
MAX_FILES=5000
MAX_TOTAL=20*1024**3
MAX_MANIFEST=4*1024**2


def relative(name):
    if (not isinstance(name,str) or not name or len(name)>4096 or '\\' in name or ':' in name
            or any(ord(c)<32 for c in name) or PurePosixPath(name).is_absolute()
            or PurePosixPath(name).as_posix()!=name or any(p in ('','.','..') for p in name.split('/'))):
        raise ValueError('ZIP内のパスが不正です。')
    return name


def check_cancel(cancelled):
    if cancelled():raise ValueError('ZIP処理を停止しました。元のファイルは残っています。')


def file_hash(path,cancelled=lambda:False):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        while True:
            check_cancel(cancelled);chunk=stream.read(1024*1024)
            if not chunk:break
            digest.update(chunk)
    return digest.hexdigest()


def root_folder(value):
    if not value:raise ValueError('共有フォルダーが未設定です。ホームの共有設定で、このPCから開ける場所を指定してください。')
    root=store._safe_chain(Path(value).expanduser())
    if not root.is_dir():raise ValueError('共有フォルダーに接続できません。')
    return root


def validate_reference(ref,project_id,record_id):
    if not isinstance(ref,dict) or ref.get('format')!=FORMAT:raise ValueError('ZIPの登録情報が不正です。')
    if not store.ID_RE.fullmatch(str(project_id)) or not store.ID_RE.fullmatch(str(record_id)):
        raise ValueError('ZIPのプロジェクト・実験IDが不正です。')
    if ref.get('project_id')!=project_id or ref.get('record_id')!=record_id:
        raise ValueError('別のプロジェクト・実験のZIPです。')
    for field in ('sha256','manifest_sha256'):
        if not re.fullmatch('[a-f0-9]{64}',str(ref.get(field,''))):raise ValueError('ZIPのハッシュが不正です。')
    expected=f'cansat-projects/{project_id}/packages/{record_id}/{ref["manifest_sha256"]}/bundle.zip'
    if relative(ref.get('relative_path'))!=expected:raise ValueError('ZIPの保存先が登録情報と一致しません。')
    if ref.get('kind') not in ('attachments','models'):raise ValueError('ZIPの種類が不正です。')
    for field,limit in (('bytes',MAX_TOTAL+16*1024**2),('source_bytes',MAX_TOTAL),('file_count',MAX_FILES)):
        if type(ref.get(field)) is not int or not 0<=ref[field]<=limit:raise ValueError('ZIPのサイズ・件数情報が不正です。')
    store._text(ref.get('name'),'ZIP名',200,True)
    return ref


def collect(sources,folder=False):
    result=[]
    if folder:
        if len(sources)!=1:raise ValueError('モデルのフォルダーを1個選んでください。')
        base=store._safe_chain(Path(sources[0]).expanduser())
        if not base.is_dir():raise ValueError('モデルのフォルダーが見つかりません。')
        paths=[]
        for parent,dirs,files in os.walk(base,followlinks=False):
            parent=Path(parent)
            for name in dirs:
                if (parent/name).is_symlink():raise ValueError('モデル内のリンクはZIPに含めません。リンクを確認してください。')
            dirs[:]=[d for d in dirs if d not in ('.git','.venv','__pycache__','.pytest_cache')]
            paths.extend(parent/name for name in files)
            if len(paths)>MAX_FILES:raise ValueError(f'資料は{MAX_FILES}ファイルまでです。')
        result=[(p.relative_to(base).as_posix(),p) for p in paths]
    else:
        result=[(Path(p).name,Path(p).expanduser()) for p in sources]
    if not result or len(result)>MAX_FILES:raise ValueError(f'資料は1～{MAX_FILES}ファイルにしてください。')
    seen=set();total=0
    for name,path in result:
        relative(name);safe=store._safe_chain(path)
        if not safe.is_file() or name.casefold() in seen:raise ValueError('同名・非対応のファイルがあります。')
        seen.add(name.casefold());total+=safe.stat().st_size
        if total>MAX_TOTAL:raise ValueError('1個の資料ZIPの元データは20GiBまでです。')
    return result,total


def create(root,project_id,record_id,sources,*,folder=False,cancelled=lambda:False):
    if not store.ID_RE.fullmatch(str(project_id)) or not store.ID_RE.fullmatch(str(record_id)):
        raise ValueError('資料のプロジェクト・実験IDが不正です。')
    root=root_folder(root)
    if folder:
        source=store._safe_chain(Path(sources[0]))
        if source==root or source in root.parents:raise ValueError('共有先フォルダーを含むフォルダーは選べません。')
    files,total=collect(sources,folder)
    entries=[]
    for name,path in files:
        check_cancel(cancelled)
        entries.append({'path':name,'bytes':path.stat().st_size,'sha256':file_hash(path,cancelled)})
    manifest={'format':FORMAT,'project_id':project_id,'record_id':record_id,
              'kind':'models' if folder else 'attachments','files':entries}
    raw=json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
    if len(raw)>MAX_MANIFEST:raise ValueError('資料のファイル一覧が大きすぎます。')
    key=hashlib.sha256(raw).hexdigest()
    relative_path=f'cansat-projects/{project_id}/packages/{record_id}/{key}/bundle.zip'
    target=store._safe_chain(root/relative_path);directory=target.parent
    name=Path(sources[0]).name if len(sources)==1 else f'{len(sources)}ファイル'
    store._text(name,'ZIP名',200,True)
    def reference():
        return {'format':FORMAT,'project_id':project_id,'record_id':record_id,'relative_path':relative_path,
                'manifest_sha256':key,'sha256':file_hash(target,cancelled),'bytes':target.stat().st_size,
                'source_bytes':total,'file_count':len(entries),'kind':manifest['kind'],'name':name}
    if directory.exists():
        if not target.is_file():raise ValueError('同名の資料フォルダーを保護するため停止します。')
        with zipfile.ZipFile(target) as archive:
            if archive.getinfo('bundle.json').file_size>MAX_MANIFEST:raise ValueError('既存ZIPの一覧が大きすぎます。')
            if archive.read('bundle.json')!=raw:raise ValueError('既存の資料ZIPは上書きしません。')
        result=reference();verify(root,result,project_id,record_id,cancelled=cancelled);return result
    if shutil.disk_usage(root).free<total+32*1024**2:
        raise ValueError('共有先の空き容量が不足しています。元データは変更していません。')
    directory.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.incoming-',dir=directory.parent) as temporary:
        stage=Path(temporary)/key;stage.mkdir();temporary_zip=stage/'bundle.zip'
        with temporary_zip.open('w+b') as output:
            with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,allowZip64=True) as archive:
                archive.writestr('bundle.json',raw)
                for item,(name,path) in zip(entries,files):
                    digest=hashlib.sha256();length=0
                    with path.open('rb') as incoming,archive.open('files/'+name,'w',force_zip64=True) as outgoing:
                        while True:
                            check_cancel(cancelled);chunk=incoming.read(1024*1024)
                            if not chunk:break
                            digest.update(chunk);length+=len(chunk);outgoing.write(chunk)
                    if length!=item['bytes'] or digest.hexdigest()!=item['sha256']:
                        raise ValueError('処理中に元ファイルが変わりました。完成ZIPとして登録しません。')
            output.flush();os.fsync(output.fileno())
        check_cancel(cancelled)
        if directory.exists():raise ValueError('同じ資料が同時に作成されました。上書きせず、再実行してください。')
        os.rename(stage,directory)
    return reference()


def locate(root,ref,project_id,record_id):
    validate_reference(ref,project_id,record_id)
    return store._safe_chain(root_folder(root)/ref['relative_path'])


def verify(root,ref,project_id,record_id,*,cancelled=lambda:False):
    target=locate(root,ref,project_id,record_id)
    if not target.is_file():raise ValueError('ZIPファイル待ちです。共有フォルダーの場所・同期状況を確認してください。')
    if target.stat().st_size!=ref['bytes'] or file_hash(target,cancelled)!=ref['sha256']:
        raise ValueError('ZIPのサイズ・SHA256が一致しません。使用せず共有元を確認してください。')
    with zipfile.ZipFile(target) as archive:
        members=archive.infolist();names=[m.filename for m in members]
        if len(members)>MAX_FILES+1 or len(names)!=len(set(names)):raise ValueError('ZIPの項目数・重複が不正です。')
        if archive.getinfo('bundle.json').file_size>MAX_MANIFEST:raise ValueError('ZIPの一覧が大きすぎます。')
        raw=archive.read('bundle.json')
        if hashlib.sha256(raw).hexdigest()!=ref['manifest_sha256']:raise ValueError('ZIP内の登録情報が一致しません。')
        manifest=json.loads(raw)
        if (not isinstance(manifest,dict) or manifest.get('format')!=FORMAT or manifest.get('project_id')!=project_id
                or manifest.get('record_id')!=record_id or manifest.get('kind')!=ref['kind']):
            raise ValueError('別プロジェクト・実験の資料です。')
        files=manifest.get('files')
        if not isinstance(files,list) or len(files)!=ref['file_count']:raise ValueError('ZIPのファイル一覧が不正です。')
        expected={'bundle.json'};total=0;seen=set()
        for item in files:
            if not isinstance(item,dict) or type(item.get('bytes')) is not int or not re.fullmatch('[a-f0-9]{64}',str(item.get('sha256',''))):
                raise ValueError('ZIP内のファイル情報が不正です。')
            name=relative(item['path']);expected.add('files/'+name)
            if name.casefold() in seen:raise ValueError('ZIP内のファイル名が重複しています。')
            seen.add(name.casefold())
            info=archive.getinfo('files/'+name)
            if info.is_dir() or stat.S_ISLNK(info.external_attr>>16) or info.file_size!=item['bytes'] or info.file_size<0:raise ValueError('ZIP内のファイルサイズ・種類が不正です。')
            total+=info.file_size
            if total>MAX_TOTAL:raise ValueError('ZIPの展開サイズが上限を超えています。')
            digest=hashlib.sha256()
            with archive.open(info) as stream:
                while True:
                    check_cancel(cancelled);chunk=stream.read(1024*1024)
                    if not chunk:break
                    digest.update(chunk)
            if digest.hexdigest()!=item['sha256']:raise ValueError('ZIP内のファイル内容が一致しません。')
        if set(names)!=expected or total!=ref['source_bytes']:raise ValueError('ZIP内に未登録のファイルがあります。')
    return target
