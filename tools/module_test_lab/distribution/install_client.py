"""One-time launcher installation. Never writes the development checkout/data."""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import json
import os
import shlex
import shutil
import subprocess
import sys
import cansat_update as client


def launcher_bytes(root):
    # The literal HOME expansion works for different Ubuntu user names.
    # Keep this fixed launcher tiny: client logic is updated separately.
    return (b'#!/usr/bin/env bash\nset -euo pipefail\n'
            b'exec python3 "$HOME/.local/share/cansat-lab/cansat_bootstrap.py" "$@"\n')


def install(home, python, apply=False):
    home = Path(home).absolute()
    root = client.safe(home / '.local/share/cansat-lab')
    bindir = client.safe(home / '.local/bin')
    launcher = bindir / 'cansat-lab'
    # A pre-existing symlink is backed up as a link; its target is never written.
    if launcher.is_dir():
        raise ValueError('cansat-lab の場所がフォルダーになっています。')
    interpreter = Path(python).expanduser().absolute()
    if not interpreter.is_file():
        raise ValueError('既存のGUI用Pythonが見つかりません: ' + str(interpreter))
    subprocess.run([str(interpreter), '-c', 'from PySide6.QtWidgets import QApplication; from PySide6.QtTest import QTest'],
                   check=True, timeout=15, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if not shutil.which('git') or not shutil.which('bash'):
        raise ValueError('既存の git / bash が必要です。')
    found = shutil.which('cansat-lab')
    if found and os.path.abspath(found) != str(launcher):
        raise ValueError('別の場所の cansat-lab が優先されています: ' + found +
                         '\n先に ~/.local/bin を PATH の先頭にしてください。')
    print('起動コマンド: ' + str(launcher))
    print('GUI配布先: ' + client.REMOTE + ' / ' + client.BRANCH)
    print('GUI保存先: ' + str(root))
    print('実験データ: ' + str(home / 'cansat_module_lab_data'))
    if not apply:
        print('確認のみ。変更していません。適用する場合は --apply を追加します。')
        return
    root.mkdir(parents=True, exist_ok=True)
    with client.update_lock(root) as locked:
        if not locked:
            raise ValueError('別の更新処理が実行中です。')
        # Fail before changing the existing launcher when GitHub isn't ready.
        revision = client.fetch(root)
        old = client.state(root)
        backup = client.safe(root / 'client_backups' /
                             datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        backup.mkdir(parents=True)
        if launcher.is_symlink():
            (backup / 'launcher-link.json').write_text(json.dumps({'target':os.readlink(launcher)}))
        elif launcher.exists():
            shutil.copy2(launcher, backup / 'cansat-lab')
        for name in ('cansat_update.py', 'cansat_bootstrap.py', 'client_state.json', 'client.json', 'state.json'):
            existing = client.safe(root / name)
            if existing.exists():
                shutil.copy2(existing, backup / name)
        updater = Path(client.__file__).read_bytes()
        bootstrap = Path(__file__).parent / 'cansat_bootstrap.py'
        # Install the fixed bootstrap before staging a client version.
        client.atomic(root / 'cansat_bootstrap.py', bootstrap.read_bytes())
        digest = client.stage_client(root, updater)
        client.activate_client(root, digest)
        # Keep a legacy fallback when the versioned client is missing/corrupt.
        client.atomic(root / 'cansat_update.py', updater)
        client.atomic(root / 'client.json', (json.dumps({'python':str(interpreter)}, indent=2)+'\n').encode())
        client.save_state(root, {'current':revision, 'previous':old.get('current')
                                if old.get('current') != revision else old.get('previous')})
        bindir.mkdir(parents=True, exist_ok=True)
        if launcher.is_symlink():
            launcher.unlink()
        client.atomic(launcher, launcher_bytes(root))
        launcher.chmod(0o755)
    print('導入しました。次から cansat-lab で起動できます。')
    print('以前の起動設定のバックアップ: ' + str(backup))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=os.environ.get('CANSAT_GUI_PYTHON', str(Path.home()/'cansat_gui_venv/bin/python')))
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if os.name != 'posix':
        raise ValueError('Ubuntu内で実行してください。')
    install(Path.home(), args.python, args.apply)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print('導入を停止しました: ' + (str(exc) if not isinstance(exc, subprocess.SubprocessError)
                                     else 'GitHubへの接続またはGUI用Pythonを確認してください。'), file=sys.stderr)
        raise SystemExit(1)
