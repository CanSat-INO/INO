#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$HOME/.local/share/cansat-lab"
LAUNCHER="$HOME/.local/bin/cansat-lab"
VENV="$ROOT/bootstrap-venv"
MARKER="$ROOT/.fresh-install-pending"

MODE="${1:---check}"

if [[ "$MODE" != "--check" && "$MODE" != "--apply" && "$MODE" != "--resume" ]]; then
    echo "使い方: bash install_fresh.sh [--check|--apply|--resume]"
    exit 2
fi

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: このインストーラーはLinux用です" >&2
    exit 1
fi

if [[ "$(id -u)" == "0" ]]; then
    echo "ERROR: sudoで実行しないでください" >&2
    exit 1
fi

for cmd in python3 git bash; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "ERROR: $cmd がありません" >&2
        exit 1
    fi
done

echo "===== CanSat Simulation 初回セットアップ ====="
echo "Python: $(python3 --version)"
echo "GUI環境: $VENV"
echo "起動コマンド: $LAUNCHER"
echo "実験データ: $HOME/cansat_module_lab_data"

EXISTING=0

for path in \
    "$LAUNCHER" \
    "$ROOT/state.json" \
    "$ROOT/client_state.json" \
    "$ROOT/cansat_update.py" \
    "$VENV"
do
    if [[ -e "$path" || -L "$path" ]]; then
        echo "既存の構成を検出: $path"
        EXISTING=1
    fi
done

if [[ "$MODE" == "--check" ]]; then
    echo "PASS: 確認モード（変更なし）"
    if [[ "$EXISTING" == "1" ]]; then
        echo "このPCでは新規インストールを行いません"
    fi
    exit 0
fi

if [[ "$MODE" == "--resume" ]]; then
    for path in "$HOME" "$HOME/.local" "$HOME/.local/share" "$ROOT" "$VENV" "$MARKER"; do
        if [[ -L "$path" ]]; then
            echo "ERROR: リンク先は再開できません: $path" >&2
            exit 1
        fi
    done

    if [[ ! -d "$ROOT" || ! -f "$MARKER" ||
          ! -x "$VENV/bin/python" ||
          -e "$LAUNCHER" || -L "$LAUNCHER" ]]; then
        echo "ERROR: 安全に再開できる未完了状態ではありません" >&2
        exit 1
    fi

    if [[ "$(cat "$MARKER")" != "CanSatFreshInstallPending:v1" ||
          "$(stat -c %u "$ROOT")" != "$(id -u)" ]]; then
        echo "ERROR: 未完了マーカーまたは所有者が不正です" >&2
        exit 1
    fi

    echo "===== Python環境を再確認 ====="
    "$VENV/bin/python" -m pip check
    env QT_QPA_PLATFORM=offscreen "$VENV/bin/python" -c         'from PySide6.QtWidgets import QApplication; app=QApplication([])'

    echo "===== 更新クライアントの登録を再開 ====="
    "$VENV/bin/python" "$HERE/install_client.py"         --python "$VENV/bin/python" --apply

    rm -- "$MARKER"
    echo "PASS: インストール再開成功"
    exit 0
fi

if [[ "$EXISTING" == "1" ]]; then
    echo "ERROR: 既存環境を保護するため停止しました" >&2
    exit 1
fi

# 既存データやリンク先の誤操作を防ぐ
for path in "$HOME" "$HOME/.local" "$HOME/.local/share" "$ROOT"; do
    if [[ -L "$path" ]]; then
        echo "ERROR: 保存先にシンボリックリンクがあります: $path" >&2
        exit 1
    fi
done

if [[ -e "$ROOT" || -L "$ROOT" ]]; then
    echo "ERROR: 既存の保存先があるため新規導入を停止しました" >&2
    exit 1
fi

mkdir -p "$HOME/.local/share"
mkdir "$ROOT"
(umask 077; printf '%s\n' "CanSatFreshInstallPending:v1" > "$MARKER")

REGISTRATION_STARTED=0

cleanup_install() {
    local status=$?

    if (( status == 0 )); then
        return
    fi

    if (( REGISTRATION_STARTED == 0 )); then
        # 今回新規作成した仮想環境だけを後片付け
        if [[ -d "$ROOT" && ! -L "$ROOT" &&
              -d "$VENV" && ! -L "$VENV" ]]; then
            if ! rm -rf -- "$VENV"; then
                echo "ERROR: 仮想環境の削除に失敗しました" >&2
            fi
        fi

        if [[ -f "$MARKER" && ! -L "$MARKER" &&
              "$(cat "$MARKER")" == "CanSatFreshInstallPending:v1" ]]; then
            rm -- "$MARKER"
        fi

        if rmdir -- "$ROOT" 2>/dev/null; then
            echo "INFO: 未完成の環境を削除しました。再実行可能です" >&2
        else
            echo "INFO: 保存先にファイルが残っています。手動確認が必要です" >&2
        fi
    else
        echo "ERROR: 更新クライアント登録中に失敗しました" >&2
        echo "設定を保護するため自動削除していません" >&2
    fi
}

trap cleanup_install EXIT

echo "===== Python環境を作成 ====="
python3 -m venv "$VENV"

echo "===== PySide6をインストール ====="
"$VENV/bin/python" -m pip install \
    --isolated \
    --disable-pip-version-check \
    --no-input \
    --only-binary=:all: \
    "PySide6==6.12.0"

"$VENV/bin/python" -m pip check

env QT_QPA_PLATFORM=offscreen \
    "$VENV/bin/python" -c \
    'from PySide6.QtWidgets import QApplication; app=QApplication([]); print("PASS: GUI環境")'

echo "===== 自動更新クライアントを登録 ====="
REGISTRATION_STARTED=1
"$VENV/bin/python" "$HERE/install_client.py" \
    --python "$VENV/bin/python" \
    --apply

rm -- "$MARKER"

echo "PASS: CanSat Simulation 初回セットアップ完了"
echo "起動: $LAUNCHER"
