# CanSat Module Test Lab v13.3: ホーム表示・日本語入力対応

## 変更点
- ホームカードをQPushButtonのカスタム描画からQFrame+QLabelの通常レイアウトに変更。Qt/X11/QSSで文字がクリップされる問題を回避。
- 一覧の各行に最低88pxを確保し、8行以上はスクロール可能にする。
- キーボード（Enter/Space）、マウス、検索・カテゴリ絞り込み、既存タブ遷移を維持。
- v13.1の検索中IME合成保護を継続。
- WSLg用のlaunch_v13_3.sh、診断機能を追加。データ・実験ロジック・解析には変更なし。

## 適用
(1) 既存アプリを終了する。
(2) ZIPをダウンロードフォルダから `~/cansat_v13_3_install` に展開。
(3) dry-runしてからインストールする。

    python3 ~/cansat_v13_3_install/install_v13_3.py --repo ~/INO-module-lab --dry-run
    python3 ~/cansat_v13_3_install/install_v13_3.py --repo ~/INO-module-lab

(4) 起動:

    bash ~/INO-module-lab/tools/module_test_lab/launch_v13_3.sh

## まだ日本語に切り替えできないとき (WSL Ubuntu)
※ Qtだけ直してもWindows標準IMEはWSLgのLinuxアプリにそのまま伝わりません。

1. Ubuntu側にFcitx5/MozcとQt6のfrontendを入れる:

    sudo apt update
    sudo apt install -y fcitx5-mozc fcitx5-config-qt fcitx5-frontend-qt6

2. Fcitx5の設定UIを起動し「Mozc」を現在の入力メソッドへ追加:

    fcitx5-configtool

3. アプリをlaunch_v13_3.shから起動し、検索欄でCtrl+Spaceを試す。Fcitx5設定のショートカットが異なればそちらを使用。

4. それでも変換できない場合:

    bash ~/INO-module-lab/tools/module_test_lab/launch_v13_3.sh --diagnose

診断出力を共有してください。PyPI導入のPySide6はOSのQt6 IMEプラグインを自動で読み込まないことがあります。
Qt6のABIが不一致だとプラグインを手動コピーするとGUIが起動しなくなる恐れがあるため、本パッチはコピーしません。

※ 代替策：Windowsで日本語を入力してコピーし、WSLアプリにCtrl+Vで貼り付け。

## 制約
- Ubuntuの設定はインストーラーから変更しません（sudo実行や.profile自動編集なし）。
- Qt GUIレンダリングは利用者のWSLg環境で最終確認が必要です。
- 既存のv13〜v13.2に対応。独自改造がある場合は上書きを拒否します。
