"""Per-project destinations; machine-specific folders never leave this PC."""
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
import project_store as store

PUBLIC_SCOPE = 'project-records-attachments-and-future-saves-v1'


def destination(repository,branch='main'):
    if not isinstance(repository,str) or not isinstance(branch,str):raise ValueError('GitHub共有先が不正です。')
    repository=repository.strip();branch=branch.strip()
    if repository.startswith('https://'):
        url=urlsplit(repository)
        if url.netloc!='github.com' or url.query or url.fragment:raise ValueError('github.com のリポジトリURLを指定してください。')
        repository=url.path.strip('/')
        if repository.endswith('.git'):repository=repository[:-4]
    elif repository.startswith('git@github.com:'):
        repository=repository[len('git@github.com:'):]
        if repository.endswith('.git'):repository=repository[:-4]
    if (not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository) or len(repository)>240
            or any(p in ('.','..') for p in repository.split('/'))):
        raise ValueError('GitHub共有先は owner/repository 形式で指定してください。')
    if (not re.fullmatch(r'[A-Za-z0-9_./-]+',branch) or len(branch)>200 or '..' in branch
            or branch.startswith(('/','-')) or branch.endswith(('/','.lock')) or '//' in branch):
        raise ValueError('共有先ブランチ名が不正です。')
    return repository,branch


def path(project_id):
    return store._safe_chain(store.read_project(project_id).directory/'.autosync/settings.json')


def public_consent_valid(value, repository, branch, project_id=None):
    """Fail closed unless the local opt-in matches this exact destination.

    A project-specific settings file supplies the project boundary. project_id is
    included for defense in depth when the authorization leaves that file.
    """
    if not isinstance(value, dict) or value.get('scope') != PUBLIC_SCOPE:
        return False
    if type(value.get('confirmed')) is not bool or not value['confirmed']:
        return False
    if project_id is None or value.get('project_id') != project_id:
        return False
    try:
        bound_repo, bound_branch = destination(value.get('repository'), value.get('branch'))
        expected_repo, expected_branch = destination(repository, branch)
    except ValueError:
        return False
    return same_destination((bound_repo, bound_branch), (expected_repo, expected_branch))


def set_public_consent(project_id, repository, branch):
    """Call only after the GUI has shown and received explicit PUBLIC consent."""
    value = read(project_id)
    if not value['repository'] or not same_destination(
            (value['repository'], value['branch']), destination(repository, branch)):
        raise ValueError('共有先が変更されました。公開への同意をやり直してください。')
    value['public_consent'] = {
        'confirmed': True, 'repository': value['repository'],
        'branch': value['branch'], 'project_id': project_id, 'scope': PUBLIC_SCOPE,
    }
    store.atomic_json(path(project_id), value)


def read(project_id):
    target=path(project_id)
    result={'format':'cansat-auto-settings-1','enabled':False,'repository':'','branch':'main','shared_root':'','public_consent':None}
    if not target.exists():return result
    if target.stat().st_size>16*1024:raise ValueError('共有設定が大きすぎます。')
    value=json.loads(target.read_text(encoding='utf-8'))
    if (not isinstance(value,dict) or value.get('format')!=result['format']
            or type(value.get('enabled')) is not bool):raise ValueError('共有設定を読み取れません。')
    result.update({k:value[k] for k in result if k in value})
    if not isinstance(result['repository'],str) or not isinstance(result['branch'],str):raise ValueError('GitHub共有先が不正です。')
    if result['repository']:result['repository'],result['branch']=destination(result['repository'],result['branch'])
    if not isinstance(result['shared_root'],str):raise ValueError('共有フォルダー設定が不正です。')
    # A previous INO-only prototype must not silently choose a destination.
    if not result['repository']:result['enabled']=False
    if not public_consent_valid(result['public_consent'], result['repository'], result['branch'], project_id):
        result['public_consent']=None
    return result


def save(project_id,repository,branch,shared_root=''):
    if not isinstance(shared_root,str):raise ValueError('共有フォルダー設定が不正です。')
    if repository:repository,branch=destination(repository,branch)
    elif not isinstance(repository,str):raise ValueError('GitHub共有先が不正です。')
    if shared_root:
        folder=store._safe_chain(Path(shared_root).expanduser())
        if not folder.is_dir():raise ValueError('このPCから開ける共有フォルダーを選んでください。')
        data=store._safe_chain(store.base_dir())
        if folder==data or data in folder.parents:raise ValueError('共有フォルダーには実験台帳の外のフォルダーを選んでください。')
        shared_root=str(folder)
    store.atomic_json(path(project_id),{'format':'cansat-auto-settings-1','enabled':False,
                      'repository':repository,'branch':branch,'shared_root':shared_root,'public_consent':None})


def current_destination():
    project_id=store.active_id()
    if not project_id:return 'CanSat-INO/INO','main' # Existing unclassified workflow.
    value=read(project_id)
    if not value['repository']:raise ValueError('プロジェクトのホームでGitHub共有先を設定してください。')
    return value['repository'],value['branch']


def same_destination(first,second):
    return first[0].lower()==second[0].lower() and first[1]==second[1]


def set_enabled(project_id,value):
    if type(value) is not bool:raise ValueError('共有設定が不正です。')
    settings=read(project_id)
    if value and not settings['repository']:raise ValueError('先にホームの共有設定でGitHub共有先を指定してください。')
    settings['enabled']=value
    if not value:settings['public_consent']=None
    store.atomic_json(path(project_id),settings)


def catalog(read_only=True,*,repository='',branch='main',enabled=False):
    target=store._safe_chain(store.base_dir()/'.project_catalog.json')
    if not read_only:
        if repository:repository,branch=destination(repository,branch)
        store.atomic_json(target,{'repository':repository,'branch':branch,'enabled':bool(enabled)})
    if not target.exists():return {'repository':'','branch':'main','enabled':False}
    if target.stat().st_size>16384:raise ValueError('一覧設定が大きすぎます。')
    value=json.loads(target.read_text(encoding='utf-8'))
    if not isinstance(value,dict) or type(value.get('enabled')) is not bool:raise ValueError('一覧設定が不正です。')
    repo=value.get('repository','');branch=value.get('branch','main')
    if repo:repo,branch=destination(repo,branch)
    return {'repository':repo,'branch':branch,'enabled':value['enabled'] and bool(repo)}
