"""Publish only the GUI to an isolated release branch. Main is never changed."""
from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import cansat_update as client


def snapshot(source, target):
    source = Path(source).resolve()
    dest = target / client.APP
    dest.mkdir(parents=True)
    for p in sorted(source.rglob('*')):
        if p.is_symlink():
            raise ValueError('ソースにリンクがあります: ' + str(p))
        if not p.is_file() or '__pycache__' in p.parts or '.git' in p.parts or p.suffix == '.pyc':
            continue
        name = p.relative_to(source)
        path = dest / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, path)
    # Distribute the one-time setup tools alongside the GUI. A new PC needs
    # no copy of the maintainer's working tree and no added Python packages.
    setup = dest / 'distribution'
    setup.mkdir(exist_ok=True)
    for name in ('cansat_update.py', 'install_client.py', 'publish_release.py'):
        shutil.copyfile(Path(__file__).parent / name, setup / name)
    manifest = {'format':client.FORMAT, 'data_format':1, 'client_protocol':1,
                'files':client.file_list(target)}
    (target / 'release.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    client.validate(target)
    return manifest


def check_gui(root, python):
    source = root / client.APP
    # Tests use only a disposable home. They cannot open the existing ledger.
    with tempfile.TemporaryDirectory(prefix='cansat-release-check-') as temp:
        env = dict(os.environ, HOME=temp, USERPROFILE=temp, XDG_CONFIG_HOME=temp+'/config',
                   XDG_CACHE_HOME=temp+'/cache', QT_QPA_PLATFORM='offscreen',
                   PYTHONDONTWRITEBYTECODE='1')
        env.pop('CANSAT_LAB_PROJECT_ID', None)
        env.pop('CANSAT_LAB_PREVIEW', None)
        # Missing Qt must fail the release instead of becoming a skipped GUI suite.
        subprocess.run([python,'-c','from PySide6.QtTest import QTest; from PySide6.QtWidgets import QApplication'],
                       cwd=source,env=env,check=True,timeout=30)
        for pattern in ('test_project_store.py', 'test_project_share.py', 'test_project_auto.py', 'test_project_storage.py', 'test_record_trash.py',
                        'test_project_gui.py', 'test_project_auto_gui.py','test_project_storage_gui.py','test_v20_workspace_gui.py'):
            if not (source / 'tests' / pattern).is_file():
                raise ValueError('公開前の試験ファイルがありません: ' + pattern)
            subprocess.run([python, '-m', 'unittest', 'discover', '-s', 'tests', '-p', pattern, '-v'],
                           cwd=source, env=env, check=True, timeout=120)


def publish(source, python, apply=False, remote=client.REMOTE, expected_parent=None):
    with tempfile.TemporaryDirectory(prefix='cansat-publish-') as temp:
        root = Path(temp)
        manifest = snapshot(source, root)
        check_gui(root, python)
        print('GUI試験が通過しました。配布対象: ' + str(len(manifest['files'])) + 'ファイル。')
        print('配布先: ' + remote + ' / ' + client.BRANCH)
        if not apply:
            print('確認のみ。公開する場合は --apply を追加します。')
            return
        # Work exclusively inside the temporary checkout; no user Git state.
        def git(*args):
            return client.run(['git', '-C', str(root), '-c', 'core.autocrlf=false', *args]).decode().strip()
        git('init', '-b', client.BRANCH)
        existing = git('ls-remote', '--heads', remote, 'refs/heads/' + client.BRANCH)
        previous = existing.split()[0] if existing else None
        if expected_parent is not None and previous != expected_parent:
            raise ValueError('試験中に別の人がGUIを更新しました。再実行してください。')
        if previous:
            git('fetch', '--depth=1', '--no-tags', remote, 'refs/heads/' + client.BRANCH)
            fetched = git('rev-parse', 'FETCH_HEAD')
            if fetched != previous:
                raise ValueError('別の人が配布を更新しました。再実行してください。')
            # Refuse to adopt a branch used for something else.
            channel = json.loads(git('show', fetched + ':release.json'))
            if channel.get('format') != client.FORMAT:
                raise ValueError('配布先のブランチが別の用途で使われています。')
        git('add', '--force', 'release.json', 'tools/module_test_lab')
        tree = git('write-tree')
        args = ['-c', 'user.name=CanSat Lab Release', '-c', 'user.email=cansat-lab@users.noreply.github.com',
                'commit-tree', tree, '-m', 'Release CanSat Simulation GUI']
        if previous:
            args += ['-p', previous]
        revision = git(*args)
        # Verify the bytes that clients will receive, not just the work files.
        archive = client.run(['git', '-C', str(root), 'archive', '--format=tar', revision,
                              'release.json', client.APP])
        with tempfile.TemporaryDirectory(prefix='cansat-published-bytes-') as check:
            client.unpack(archive, Path(check))
        # Compare-and-swap rejects concurrent publishers; it never targets main.
        lease = '--force-with-lease=refs/heads/' + client.BRANCH + ':' + (previous or '')
        git('push', lease, remote, revision + ':refs/heads/' + client.BRANCH)
        print('公開しました: ' + revision)
        print('設定済みのPCでは、次回の cansat-lab 起動時に反映されます。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).parent/'source/tools/module_test_lab')
    parser.add_argument('--python', default=os.environ.get('CANSAT_GUI_PYTHON', str(Path.home()/'cansat_gui_venv/bin/python')))
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    publish(args.source, args.python, args.apply)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, SyntaxError, subprocess.SubprocessError):
        print('公開を停止しました。試験結果とGitHubの読み書き権限を確認してください。'
              '開発リポジトリ・実験データは変更していません。', file=sys.stderr)
        raise SystemExit(1)
