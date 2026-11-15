"""Stable stdlib entrypoint for versioned CanSat GUI update clients.

No network, package installation, or GUI changes happen here.  The bootstrap
is installed once and reads only data under ~/.local/share/cansat-lab.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

SHA256 = re.compile(r'^[0-9a-f]{64}$')


def safe(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('更新先にシンボリックリンクがあります。')
    return path


def atomic(path, raw):
    path = safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.new-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_state(root):
    p = safe(root / 'client_state.json')
    if not p.exists():
        return {'current': None, 'previous': None}
    obj = json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(obj, dict) or obj.get('schema') != 1:
        raise ValueError('更新クライアントの履歴が不正です。')
    for name in ('current', 'previous'):
        value = obj.get(name)
        if value is not None and (not isinstance(value, str) or not SHA256.fullmatch(value)):
            raise ValueError('更新クライアントのIDが不正です。')
    return obj


def save_state(root, obj):
    atomic(root / 'client_state.json', (json.dumps(obj, indent=2) + '\n').encode())


def version_path(root, digest):
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise ValueError('更新クライアントのIDが不正です。')
    return safe(root / 'clients' / digest / 'cansat_update.py')


def valid_client(root, digest):
    script = version_path(root, digest)
    if not script.is_file():
        return None
    raw = script.read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        return None
    try:
        compile(raw, str(script), 'exec')
    except (SyntaxError, UnicodeError, ValueError):
        return None
    return script


def choose(root):
    info = read_state(root)
    for name in ('current', 'previous'):
        digest = info.get(name)
        if digest:
            script = valid_client(root, digest)
            if script:
                if name == 'previous':
                    print('更新クライアントの現行版を検証できず、前の版を使用します。', file=sys.stderr)
                return script
    # Preserve the legacy client as a last resort for pre-v2 installations.
    legacy = safe(root / 'cansat_update.py')
    if legacy.is_file():
        compile(legacy.read_bytes(), str(legacy), 'exec')
        return legacy
    raise ValueError('使用可能な更新クライアントがありません。')


def rollback(root):
    root.mkdir(parents=True, exist_ok=True)
    with open(safe(root / 'update.lock'), 'a') as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('別の更新処理が実行中です。') from None
        info = read_state(root)
        current, previous = info.get('current'), info.get('previous')
        if not previous or valid_client(root, previous) is None:
            raise ValueError('復元できる前の更新クライアントがありません。')
        save_state(root, {'schema': 1, 'current': previous, 'previous': current})
        # Do not immediately reactivate the broken client by startup update.
        atomic(root / 'paused', b'updates paused\n')
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def main(argv=None):
    root = safe(Path.home() / '.local/share/cansat-lab')
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ['--client-status']:
        info = read_state(root)
        print('更新クライアント: ' + str(choose(root)))
        print('現行ID: ' + str(info.get('current')))
        print('前のID: ' + str(info.get('previous')))
        return 0
    if args == ['--client-rollback']:
        rollback(root)
        print('前の更新クライアントへ戻しました。起動時更新は停止中です。')
        return 0
    script = choose(root)
    # A subprocess avoids replacing the bootstrap and makes failures visible.
    return subprocess.call([sys.executable, str(script), *args])


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, SyntaxError, json.JSONDecodeError) as exc:
        print('CanSat updater: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
