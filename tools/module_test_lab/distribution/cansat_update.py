"""Small stdlib client for the reviewed GUI release channel, not a repo updater."""
from __future__ import annotations

import contextlib
import ast
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

REMOTE = 'https://github.com/CanSat-INO/INO.git'
BRANCH = 'cansat-lab-stable'
FORMAT = 'cansat-gui-release-1'
APP = 'tools/module_test_lab'
MAX_BYTES = 24 * 1024 * 1024
UPDATER_PROTOCOL = 2  # Stable bootstrap-compatible client version.
COMMIT = re.compile(r'^[0-9a-f]{40}$')


def safe(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('更新用の保存先にシンボリックリンクがあります。')
    return path


def atomic(path, raw):
    path = safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.new-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def run(args, **kwargs):
    if args and args[0] == 'git':
        args = ['git', '-c', 'core.autocrlf=false', '-c', 'core.attributesFile=', *args[1:]]
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='Never',
               GIT_SSH_COMMAND='ssh -oBatchMode=yes -oConnectTimeout=5')
    for key in list(env):
        if key.startswith('GIT_') and key not in ('GIT_TERMINAL_PROMPT', 'GIT_SSH_COMMAND'):
            env.pop(key)
    env['GCM_INTERACTIVE'] = 'Never'
    if args and args[0] == 'git' and REMOTE in args and shutil.which('gh'):
        # Reuse the Ubuntu account already used by the app's GitHub features.
        # This is per command; never modify global Git credential settings.
        args = ['git', '-c', 'credential.helper=', '-c',
                'credential.helper=!gh auth git-credential', *args[1:]]
    return subprocess.run(args, env=env, check=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=12, **kwargs).stdout


def file_list(root):
    files = {}
    for p in sorted(root.rglob('*')):
        if p.is_symlink():
            raise ValueError('配布ファイルにリンクがあります。')
        if not p.is_file():
            continue
        name = p.relative_to(root).as_posix()
        if '__pycache__' in p.parts or name.endswith('.pyc'):
            continue
        files[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return files


def valid_name(name):
    if not isinstance(name, str) or '\\' in name or ':' in name:
        return False
    p = PurePosixPath(name)
    return (not p.is_absolute() and p.as_posix() == name and
            all(x not in ('.', '..', '') for x in name.split('/')) and
            name.startswith(APP + '/') and '.git' not in p.parts and
            '__pycache__' not in p.parts and not name.endswith('.pyc'))


def validate(root):
    root = safe(root)
    raw = safe(root / 'release.json').read_bytes()
    if len(raw) > 512 * 1024:
        raise ValueError('配布情報が大きすぎます。')
    obj = json.loads(raw)
    if (not isinstance(obj, dict) or obj.get('format') != FORMAT or obj.get('data_format') != 1 or
            obj.get('client_protocol') != 1):
        raise ValueError('この更新ツールでは扱えない配布形式です。')
    expected = obj.get('files')
    if not isinstance(expected, dict) or not expected or len(expected) > 1500:
        raise ValueError('配布ファイル一覧が不正です。')
    if any(not valid_name(n) or not isinstance(h, str) or
           not re.fullmatch('[0-9a-f]{64}', h) for n, h in expected.items()):
        raise ValueError('配布ファイルのパスまたはハッシュが不正です。')
    required = ['app.py', 'launch_v13_4.sh', 'project_store.py', 'project_hub.py']
    if any(APP + '/' + n not in expected for n in required):
        raise ValueError('起動に必要なファイルがありません。')
    actual = file_list(root)
    actual.pop('release.json', None)
    if actual != expected:
        raise ValueError('配布ファイルの内容が一致しません。')
    total = 0
    for name in expected:
        p = root / name
        total += p.stat().st_size
        if name.endswith('.py'):
            compile(p.read_bytes(), name, 'exec')
    if total > MAX_BYTES:
        raise ValueError('配布ファイルが大きすぎます。')
    return obj


def unpack(raw, target):
    if len(raw) > MAX_BYTES + 4 * 1024 * 1024:
        raise ValueError('更新アーカイブが大きすぎます。')
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        members = archive.getmembers()
        if len(members) > 1800 or sum(m.size for m in members) > MAX_BYTES:
            raise ValueError('更新アーカイブが大きすぎます。')
        seen = set()
        for member in members:
            name = member.name.rstrip('/')
            if member.isdir():
                if name not in ('tools', APP) and not valid_name(name):
                    raise ValueError('配布対象外のフォルダーです。')
                continue
            if (not member.isfile() or name in seen or
                    (name != 'release.json' and not valid_name(name))):
                raise ValueError('不正な更新アーカイブです。')
            seen.add(name)
            p = safe(target / name)
            p.parent.mkdir(parents=True, exist_ok=True)
            stream = archive.extractfile(member)
            p.write_bytes(stream.read())
    validate(target)


@contextlib.contextmanager
def update_lock(root):
    # POSIX advisory locks disappear on process exit; no stale lock recovery.
    import fcntl
    with open(safe(root / 'update.lock'), 'a') as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def state(root):
    path = safe(root / 'state.json')
    if not path.exists():
        return {}
    obj = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(obj, dict):
        raise ValueError('更新履歴が不正です。')
    for key in ('current', 'previous'):
        if obj.get(key) is not None and not COMMIT.fullmatch(str(obj[key])):
            raise ValueError('更新履歴のIDが不正です。')
    return obj


def save_state(root, obj):
    atomic(root / 'state.json', (json.dumps(obj, indent=2) + '\n').encode())


def release_path(root, revision):
    if not COMMIT.fullmatch(revision):
        raise ValueError('配布IDが不正です。')
    return safe(root / 'releases' / revision)


def fetch(root, remote=REMOTE):
    cache = safe(root / 'cache.git')
    if not cache.exists():
        run(['git', 'init', '--bare', str(cache)])
    run(['git', '--git-dir', str(cache), 'fetch', '--depth=1', '--no-tags', remote,
         'refs/heads/' + BRANCH])
    revision = run(['git', '--git-dir', str(cache), 'rev-parse', 'FETCH_HEAD']).decode().strip()
    target = release_path(root, revision)
    if target.exists():
        validate(target)
        return revision
    archive = run(['git', '--git-dir', str(cache), 'archive', '--format=tar', revision,
                   'release.json', APP])
    releases = safe(root / 'releases')
    releases.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.incoming-', dir=releases) as temp:
        folder = Path(temp) / 'release'
        folder.mkdir()
        unpack(archive, folder)
        os.replace(folder, target)
    return revision



def client_source_protocol(raw):
    """Require the v2 bootstrap contract without importing untrusted code."""
    try:
        node = ast.parse(raw.decode('utf-8'))
    except (UnicodeError, SyntaxError):
        return None
    for assignment in node.body:
        if (isinstance(assignment, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == 'UPDATER_PROTOCOL'
                    for t in assignment.targets) and
                isinstance(assignment.value, ast.Constant)):
            return assignment.value.value
    return None


def installed_bootstrap(root):
    """Load the fixed, locally installed bootstrap, not code from the release."""
    path = safe(Path(root) / 'cansat_bootstrap.py')
    spec = importlib.util.spec_from_file_location('cansat_installed_bootstrap', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stage_client(root, raw):
    """Create a verified immutable updater version; never replace a running script."""
    if len(raw) > 512 * 1024 or client_source_protocol(raw) != 2:
        raise ValueError('更新クライアントの互換性を確認できません。')
    compile(raw, 'cansat_update.py', 'exec')
    bootstrap = installed_bootstrap(root)
    digest = hashlib.sha256(raw).hexdigest()
    script = bootstrap.version_path(root, digest)
    if script.exists():
        if bootstrap.valid_client(root, digest) is None:
            raise ValueError('保存済み更新クライアントの内容が不正です。')
    else:
        parent = safe(root / 'clients')
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.incoming-', dir=parent) as tmp:
            directory = Path(tmp) / 'client'
            directory.mkdir()
            atomic(directory / 'cansat_update.py', raw)
            os.replace(directory, script.parent)
    return digest


def activate_client(root, digest):
    bootstrap = installed_bootstrap(root)
    info = bootstrap.read_state(root)
    if bootstrap.valid_client(root, digest) is None:
        raise ValueError('更新クライアントを検証できません。')
    if info.get('current') != digest:
        bootstrap.save_state(root, {'schema': 1, 'current': digest,
                                    'previous': info.get('current')})
        return True
    return False


def update_client_from_release(root, release):
    """Trusted GUI-release bytes are already hash-verified by validate()."""
    candidate = safe(release / APP / 'distribution' / 'cansat_update.py')
    if not candidate.is_file():
        return False
    validate(release)
    raw = candidate.read_bytes()
    # Never downgrade when visiting a legacy release.
    if client_source_protocol(raw) != 2:
        return False
    digest = stage_client(root, raw)
    return activate_client(root, digest)


def select(root, update=True, remote=REMOTE):
    root = safe(root)
    root.mkdir(parents=True, exist_ok=True)
    info = state(root)
    if update:
        try:
            with update_lock(root) as locked:
                if locked:
                    info = state(root)
                    revision = fetch(root, remote)
                    # This client is started through the fixed bootstrap.  Stage
                    # the next validated client for the next launch, never swap
                    # code under the process currently running.
                    update_client_from_release(root, release_path(root, revision))
                    if revision != info.get('current'):
                        info = {'current': revision, 'previous': info.get('current')}
                        save_state(root, info)
                        print('CanSat Simulation: GUIを更新しました (' + revision[:8] + ')。', file=sys.stderr)
        except (OSError, ValueError, SyntaxError, KeyError, tarfile.TarError, subprocess.SubprocessError):
            # Never dump credential-helper output or URLs with credentials.
            print('CanSat Simulation: 更新を確認できないため、保存済みのGUIを使用します。', file=sys.stderr)
    info = state(root)
    for revision in (info.get('current'), info.get('previous')):
        if revision:
            try:
                candidate = release_path(root, revision)
                validate(candidate)
                return revision, candidate
            except (OSError, ValueError, SyntaxError):
                continue
    raise ValueError('使用できるGUIがありません。GitHubへの接続を確認して再実行してください。')


def rollback(root):
    info = state(root)
    revision = info.get('previous')
    if not revision:
        raise ValueError('戻せるGUIがありません。')
    validate(release_path(root, revision))
    # Pin offline until the user explicitly re-enables startup updates.
    save_state(root, {'current': revision, 'previous': info.get('current')})
    atomic(root / 'paused', b'updates paused\n')


def main():
    root = safe(Path.home() / '.local/share/cansat-lab')
    args = sys.argv[1:]
    if args == ['--update-resume']:
        with contextlib.suppress(FileNotFoundError):
            safe(root / 'paused').unlink()
        print('起動時の更新を再開しました。')
        return 0
    if args == ['--update-rollback']:
        with update_lock(root) as locked:
            if not locked:
                raise ValueError('別の更新処理が実行中です。')
            rollback(root)
        print('前のGUIに戻しました。更新は一時停止中です。')
        return 0
    update = '--offline' not in args and not (root / 'paused').exists()
    args = [a for a in args if a != '--offline']
    revision, release = select(root, update)
    if args == ['--update-status']:
        print('GUI: ' + revision + '\n保存先: ' + str(release))
        print('起動時更新: ' + ('停止中' if (root / 'paused').exists() else '有効'))
        return 0
    config = json.loads((root / 'client.json').read_text(encoding='utf-8'))
    python = config['python']
    if not Path(python).is_file():
        raise ValueError('設定したGUI用Pythonが見つかりません。')
    env = dict(os.environ, CANSAT_GUI_PYTHON=python, PYTHONDONTWRITEBYTECODE='1',
               CANSAT_LAB_RELEASE=revision[:8])
    env.pop('CANSAT_LAB_PREVIEW', None)
    env.pop('CANSAT_LAB_PROJECT_ID', None)
    # Keep every existing IME setting in the verified launcher, per process.
    result = subprocess.run(['bash', str(release / APP / 'launch_v13_4.sh'), *args], env=env,
                            cwd=release / APP)
    if result.returncode:
        print('GUIが終了コード ' + str(result.returncode) + ' で終了しました。'
              '必要なら cansat-lab --update-rollback で前のGUIに戻せます。', file=sys.stderr)
    return result.returncode


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
