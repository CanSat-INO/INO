# CanSat Module Test Lab v13.2 — ホーム一覧の縦つぶれ修正

## 何を直したか

- **WSL/Qt上でカードの中身だけが縦につぶれる問題**への対策として、カード (`QPushButton`) の中に子の `QHBoxLayout` / `QLabel` を配置する実装をやめ、`NavigationTile.paintEvent()` で表示します。
- `NavigationTile.HEIGHT = 76` でカードを固定の高さとし、一覧コンテナに「行数×カード高さ＋行間＋余白」の最低高さを与えました。ウィンドウが小さいときは下方向にスクロールします。
- ボタンとしてのクリック、キーボード操作、アクセシビリティ名、カテゴリ色、ホバー表示は維持します。
- v13.1の日本語IME編集中に画面を作り直さない仕組みを継続します。**WSL側に日本語IMEがない場合は、このパッチだけでは日本語変換できません。**
- `app.py`、センサー・解析・CSV・ROS 2連携などの実験処理は一切変更しません。

## 手順

ZIPをダウンロード後、Ubuntu上で次を実行。`--repo` は実際のリポジトリに変更してください。

```bash
mkdir -p ~/cansat_v13_2_install
python3 -m zipfile -e /mnt/c/Users/＜Windowsユーザー名＞/Downloads/cansat_module_test_lab_v13_2_layout_fix_installer.zip ~/cansat_v13_2_install
python3 ~/cansat_v13_2_install/install_v13_2.py --repo ~/INO-module-lab --dry-run
python3 ~/cansat_v13_2_install/install_v13_2.py --repo ~/INO-module-lab
```

`--dry-run` ではファイルを変更しません。想定外の既存ソースの場合は安全のため停止します。適用時のバックアップは `~/cansat_v13_2_backups/` 以下に保存されます。

起動例:

```bash
cd ~/INO-module-lab
QT_QPA_PLATFORM=xcb ~/cansat_gui_venv/bin/python -u -X faulthandler tools/module_test_lab/app.py
```

## 動作確認

1. 2列の機能一覧に各76pxのカードが上下につぶれず表示されること。
2. 右側にスクロールバーが出る場合、下のカードへ移動できること。
3. カードをクリックして対応するタブへ切り替えられること。
4. 検索欄へ日本語を入力・変換できること。日本語変換自体ができない場合はWSL側のIME設定も確認すること。

自動検証:

```bash
cd ~/INO-module-lab/tools/module_test_lab
QT_QPA_PLATFORM=offscreen ~/cansat_gui_venv/bin/python -m unittest discover -s tests -p 'test_navigation_v13_*.py'
```
