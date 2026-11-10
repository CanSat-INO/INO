#!/usr/bin/env bash
# CanSat Module Test Lab v13.3 WSLg launcher and IME diagnostics.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${CANSAT_GUI_PYTHON:-$HOME/cansat_gui_venv/bin/python}"
export QT_QPA_PLATFORM=xcb
export QT_IM_MODULE=fcitx
export XMODIFIERS='@im=fcitx'
export GTK_IM_MODULE=fcitx

if [[ "${1:-}" == '--diagnose' ]]; then
  echo '=== v13.3 日本語IME診断 ==='
  echo "OS: $(uname -sr)"
  echo "DISPLAY: ${DISPLAY:-<empty>}"
  echo "WAYLAND_DISPLAY: ${WAYLAND_DISPLAY:-<empty>}"
  echo "QT_QPA_PLATFORM: $QT_QPA_PLATFORM"
  echo "QT_IM_MODULE: $QT_IM_MODULE"
  echo "Python: $PYTHON"
  if command -v fcitx5 >/dev/null 2>&1; then
    echo "fcitx5: $(command -v fcitx5)"
  else
    echo 'fcitx5: NOT INSTALLED (see README for the Ubuntu package installation command)'
  fi
  if command -v fcitx5-configtool >/dev/null 2>&1; then
    echo "configtool: $(command -v fcitx5-configtool)"
  else
    echo 'configtool: NOT INSTALLED'
  fi
  if pgrep -x fcitx5 >/dev/null 2>&1; then
    echo 'fcitx5 process: RUNNING'
  else
    echo 'fcitx5 process: NOT RUNNING'
  fi
  if [[ -x "$PYTHON" ]]; then
    "$PYTHON" - <<'PYTHON_CHECK' || true
import sys
try:
    import PySide6
    from PySide6.QtCore import qVersion, QLibraryInfo
    from pathlib import Path
    print('PySide6:', PySide6.__version__, 'Qt:', qVersion())
    qt_plugins = Path(PySide6.__file__).parent / 'Qt' / 'plugins' / 'platforminputcontexts'
    print('PySide6 input plugin directory:', qt_plugins)
    print('PySide6 FCITX plugins:', [p.name for p in qt_plugins.glob('*fcitx*')])
except Exception as exc:
    print('PySide6 diagnostic error:', repr(exc))
PYTHON_CHECK
  else
    echo 'Python venv: NOT FOUND'
  fi
  echo '=== 診断完了 ==='
  exit 0
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Python環境が見つかりません: $PYTHON" >&2
  exit 1
fi
if ! command -v fcitx5 >/dev/null 2>&1; then
  echo '[警告] Fcitx5未導入です。日本語変換にはUbuntu側のIMEが必要です。' >&2
elif ! pgrep -x fcitx5 >/dev/null 2>&1; then
  echo '[INFO] fcitx5をWSLgのX11モードで起動します。'
  fcitx5 -d --disable=wayland,waylandim >/dev/null 2>&1 || echo '[警告] fcitx5起動に失敗しました。 --diagnose で確認してください。' >&2
fi

exec "$PYTHON" -u -X faulthandler "$HERE/app.py" "$@"
