# CanSat Module Test Lab v13.4 — 短いコマンドで起動・日本語入力の固定

v13.3 の正常に表示されたGUIと、ユーザーが確認済みのMozc切り替えキー（変換、無変換、半角/全角）を維持します。
**アプリ本体・実験データ・解析ロジック・Fcitx5の設定ファイルは変更しません。**

## 使い方

インストール後に新しいUbuntuターミナルを開き、以下を実行します。

```bash
cansat-lab
```

同じターミナル内で直ちに使いたいときは `source ~/.bashrc` を実行してください。
`~/.local/bin` がPATHにない場合、インストーラーは `~/.bashrc` の末尾に**PATH追加のみ**の管理ブロックを追記します。

```bash
cansat-lab --diagnose
cansat-lab --help
```

起動時に既存のFcitx5がDBus上で応答すれば再起動はしません。
WSLを終了してFcitx5が消えた場合、次の `cansat-lab` 実行時に
`fcitx5 -d --disable=wayland,waylandim` で起動を試みます。
常駐サービスの登録やUbuntu/Windows全体へのQt環境変数設定はしません。

Qtアプリ起動時に有効にする環境変数（今回成功した値）：

```bash
IBUS_USE_PORTAL=1
QT_QPA_PLATFORM=xcb
QT_IM_MODULE=ibus
QT_IM_MODULES=ibus
XMODIFIERS=@im=fcitx
```

上記はCanSatアプリのプロセスにだけ適用されます。Qtプラグインのコピーはしません。

## トラブルシューティング

- `cansat-lab: command not found`: `source ~/.bashrc` を実行、または `~/.local/bin/cansat-lab` と入力。
- 「Pythonがない」: `~/cansat_gui_venv/bin/python` の存在を確認。変更した環境では `CANSAT_GUI_PYTHON=/path/to/python cansat-lab`。
- 日本語が変換できない: `cansat-lab --diagnose` を確認。既存のFcitx5設定（Mozc登録・ショートカット）は保持。
- 短いコマンドを通さず起動したい: `bash ~/INO-module-lab/tools/module_test_lab/launch_v13_4.sh`。
- `--diagnose` は設定を表示するだけでアプリもFcitx5も起動しません。

## 変更ファイル

- 新規: `tools/module_test_lab/launch_v13_4.sh`
- 新規: `tools/module_test_lab/README_V13_4_SHORT_LAUNCH_IME_JA.md`
- 新規: `~/.local/bin/cansat-lab`
- 必要な場合のみ: `~/.bashrc` 末尾にPATH用の管理ブロック

安全のため既存同名ファイルの予期しない上書きは拒否します。変更前のファイルは
`~/cansat_v13_4_backups/` 以下にバックアップします。インストーラーは何度実行しても重複した行を追加しません。
