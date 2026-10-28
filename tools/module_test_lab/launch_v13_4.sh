#!/usr/bin/env bash
# CanSat Module Test Lab v13.4: verified PySide6 + Fcitx5/Mozc WSLg launcher.
# This script modifies only this process' environment, not the user's global IME.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${CANSAT_GUI_PYTHON:-$HOME/cansat_gui_venv/bin/python}"

# Verified working on WSLg, PySide6 6.12 and Fcitx5's IBus-compatible portal.
export IBUS_USE_PORTAL=1
export QT_QPA_PLATFORM=xcb
export QT_IM_MODULE=ibus
export QT_IM_MODULES=ibus
export XMODIFIERS='@im=fcitx'

usage() {
  cat <<'HELP'
CanSat Module Test Lab v13.4
  cansat-lab             GUIを起動（必要ならFcitx5も起動）
  cansat-lab --diagnose  日本語入力とQtの状態を確認
  cansat-lab --help      このヘルプを表示
HELP
}

is_fcitx_ready() {
  command -v fcitx5-remote >/dev/null 2>&1 && fcitx5-remote --check >/dev/null 2>&1
}

diagnose() {
  echo '=== CanSat Module Test Lab v13.4 / WSLg IME ==='
  printf 'DISPLAY=%s\n' "${DISPLAY:-<unset>}"
  printf 'DBUS_SESSION_BUS_ADDRESS=%s\n' "${DBUS_SESSION_BUS_ADDRESS:-<unset>}"
  for var in IBUS_USE_PORTAL QT_QPA_PLATFORM QT_IM_MODULE QT_IM_MODULES XMODIFIERS; do
    printf '%s=%s\n' "$var" "${!var}"
  done
  printf 'Python=%s\n' "$PYTHON"
  if command -v fcitx5 >/dev/null 2>&1; then
    printf 'Fcitx5 executable=%s\n' "$(command -v fcitx5)"
  else
    echo 'Fcitx5 executable=NOT FOUND'
  fi
  if is_fcitx_ready; then
    echo 'Fcitx5 DBus=CONNECTED'
    echo "Fcitx5 state=$(fcitx5-remote 2>/dev/null || true) (0=off, 1=inactive, 2=active)"
    echo "Input method=$(fcitx5-remote -n 2>/dev/null || true)"
  else
    echo 'Fcitx5 DBus=NOT CONNECTED (cansat-lab automatically attempts to start it)'
  fi
  if [[ -f "$HOME/.config/fcitx5/profile" ]]; then
    if grep -Eiq '^Name=mozc([[:space:]]*)$' "$HOME/.config/fcitx5/profile"; then
      echo 'Mozc profile=REGISTERED'
    else
      echo 'Mozc profile=NOT FOUND'
    fi
  fi
  if [[ -x "$PYTHON" ]]; then
    "$PYTHON" - <<'PYTHON_CHECK' || true
from pathlib import Path
try:
    import PySide6
    from PySide6.QtCore import qVersion
    plugin_dir = Path(PySide6.__file__).parent / 'Qt' / 'plugins' / 'platforminputcontexts'
    print('PySide6=' + str(PySide6.__version__) + ' / Qt=' + qVersion())
    print('IBus Qt plugin=' + ('FOUND' if (plugin_dir / 'libibusplatforminputcontextplugin.so').is_file() else 'NOT FOUND'))
except Exception as exc:
    print('PySide6 diagnostic error=' + repr(exc))
PYTHON_CHECK
  else
    echo 'Python venv=NOT FOUND'
  fi
  echo '=== 診断完了 ==='
}

case "${1:-}" in
  --help|-h) usage; exit 0 ;;
  --diagnose) diagnose; exit 0 ;;
esac

if [[ ! -x "$PYTHON" ]]; then
  printf '[ERROR] GUI用Pythonが見つかりません: %s\n' "$PYTHON" >&2
  echo '必要なら CANSAT_GUI_PYTHON=/path/to/python を指定してください。' >&2
  exit 1
fi
if [[ ! -f "$HERE/app.py" ]]; then
  printf '[ERROR] CanSatアプリが見つかりません: %s/app.py\n' "$HERE" >&2
  exit 1
fi
if [[ -z "${DISPLAY:-}" ]]; then
  echo '[WARN] DISPLAYがありません。WSLg GUIを起動できない可能性があります。' >&2
fi

# After a WSL shutdown the Fcitx5 process is gone. Restart *on demand*;
# never replace an already-working instance (preserves keyboard shortcuts).
if command -v fcitx5 >/dev/null 2>&1; then
  if ! is_fcitx_ready; then
    echo '[INFO] Fcitx5を起動しています（WSLg X11モード）。' >&2
    fcitx5 -d --disable=wayland,waylandim >/dev/null 2>&1 || true
    for _ in {1..20}; do
      if is_fcitx_ready; then break; fi
      sleep 0.2
    done
    if ! is_fcitx_ready; then
      echo '[WARN] Fcitx5のDBus接続を確認できません。GUIは起動しますが日本語入力を確認してください。' >&2
      echo '       cansat-lab --diagnose' >&2
    fi
  fi
else
  echo '[WARN] Fcitx5がありません。アプリは起動しますが日本語変換できない可能性があります。' >&2
fi

exec "$PYTHON" -u -X faulthandler "$HERE/app.py" "$@"
