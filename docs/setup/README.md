# クローンからTest Lab・Gazeboを起動する

Windows では WSL2 + WSLg、Linux では GUI 付き Ubuntu を使用する。
通常利用はWindowsのバッチで行う。初回だけUbuntuの準備とsudoパスワード入力が必要。
| Ubuntu | ROS 2 | Gazebo | 確認状況 |
|---|---|---|---|
| 24.04 | Jazzy | Harmonic | amd64 で実動確認済み |
| 26.04 | Lyrical | Jetty | セットアップ対応。Gazebo 実動は未検証 |

ROS 2 と Gazebo は Ubuntu のバージョンに応じて自動選択する。
ARM64はセットアップ対象だが未検証。WindowsネイティブだけでGazeboを動かす構成ではない。

## 1. WSL・Ubuntuを準備（Windows）

未導入なら、管理者PowerShellで実行する。

```powershell
wsl --install -d Ubuntu-24.04
```

Windowsから再起動を求められた場合は再起動し、Ubuntuを開いてLinuxユーザー名・
パスワードを設定する。このパスワードは後のsudoで使う。
既存のUbuntu 24.04がある場合はそのまま利用できる。
Lyrical に移行する場合は [Ubuntu 26.04 を別の WSL 環境に用意する手順](ROS2.md#lyrical-へ移行する-wsl) を参照。

```powershell
wsl --list --verbose
wsl -d Ubuntu-24.04
```

ディストリビューション名がUbuntuなら最後の行は `wsl -d Ubuntu`。
VERSION列が2であることを確認する。WSL1やUbuntu22.04をそのまま使用しない。
WSLg/GPUに問題がある場合はMicrosoftの[GUIアプリ手順](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps)を参照。
WSL更新や再起動は作業を保存してから手動で行う。スクリプトは再起動しない。

## 2. Ubuntuのホーム配下へclone（Ubuntu）

ここからはUbuntuのターミナルで実行する。

```bash
sudo apt update
sudo apt install -y git

git clone --branch feature/camera_simu https://github.com/CanSat-INO/INO.git ~/INO
cd ~/INO
```

現時点の配布対象はfeature/camera_simu。変更をpushした後に利用できる。
mainへ取り込み済みの場合は `--branch feature/camera_simu` を外せる。
`/home/<ユーザー名>/INO` のようなLinux側へ置く。`/mnt/c/...` よりLinux側を推奨する。
ユーザー名やホームディレクトリーの名前は各自の環境に合わせる。
GitHubのアクセス権が必要な場合は各自のアカウントで認証する。

## 3. 初回セットアップ

```bash
bash scripts/setup.sh
```

または `explorer.exe .` でこのフォルダーを開き、**setup-simulation.bat** をダブルクリックする。
バッチは配置先のWSLディストリビューションとパスを自動判定する。

この処理は次を行う。

- Ubuntu 24.04 または 26.04 を確認し、対応する ROS 2 を選択する。
- 既存のROS配布元を保持し、未登録なら公式ros2-apt-sourceをSHA256検証して登録する。
- ROS 2、Gazebo/SLAM、C++、Qt/日本語表示のシステム依存をaptで導入する。
- clone直下の.venvへ、検証済みPySide6 6.12.0一式を導入する。
- インストール後に読み取り専用の環境診断を実行する。

インターネット接続、空き容量、sudo権限が必要。初回は大きなダウンロードが発生する。
Windows機能・GPUドライバー・時計・サービス再起動・.bashrcは自動変更しない。
スクリプト全体をsudoで起動しない。必要なapt操作だけがsudoを使う。
既存.venvを自動削除せず、外部環境へのシンボリックリンクも変更しない。

## 4. 普段の起動

**start-module-test-lab.bat** を開く。

- 「Gazebo カメラ試験」: カメラ条件・撮影・SLAM・比較。
- 「自律走行・降下・SIL」: 停止撮影の地上走行、放出・開傘、ユーザーC++アダプター。
- それぞれ「初期設定を読込」→条件変更→「起動」。
- 終了確認の「はい」で、起動したGazebo試験の停止を待って終了する。

Ubuntuから直接起動する場合：

```bash
bash tools/module_test_lab/launch_ino.sh
```

カメラだけの設定画面はcamera-settings.bat、手動操作はcamera-teleop.bat。
ソース用ランチャーには通常colcon buildは不要。GUI環境・ログはcloneに含めず、既定の比較設定はソースに含む。
実行ごとの設定コピー・生成物は各自の実験データとして扱う。本番ファームウェアは今後追加する。

## 5. 確認と更新

**check-simulation.bat** または次のコマンドで診断する。

```bash
bash scripts/doctor.sh
bash scripts/doctor.sh --json
```

FAILは不足依存などの修正対象、WARNはGUI表示環境や任意の日本語入力などの確認事項。
診断はシミュレーションを起動せず、ROS/GazeboやQtのライブラリを調べる。
実際の画像描画・走行・実機動作の成功保証ではない。

更新は、ローカル変更を確認してから `git pull`。
依存定義が変わった場合はsetup-simulation.batを再実行できる。
実験記録は `~/cansat_module_lab_data`、Gazeboログは各パッケージのlogsに保存される。
Gitのpull/pushで自動共有するものではない。

## オプション

```bash
bash scripts/setup.sh --dry-run                 # 何も変更せず計画を表示
bash scripts/setup.sh --lab-only                # GUI・Python/CSV試験のみ（ROS導入なし）
bash scripts/setup.sh --skip-system-packages    # システム依存が既に揃っている場合
bash scripts/setup.sh --with-ime                # 任意のFcitx5/Mozcツールも導入
bash scripts/setup.sh --dev                     # pytest等の開発用依存も導入
```

--lab-onlyではGazeboやC++ビルドの依存は揃わない。必要なら通常セットアップを使う。
日本語の文字表示は標準で対応する。日本語変換は別途Mozcの入力設定が必要な場合がある。
--with-imeも既存の入力設定を上書きしない。Fcitx5設定画面でMozcを追加する。

## 関連資料

- [ROS 2の導入・手動確認](ROS2.md)
- [トラブルシューティング](TROUBLESHOOTING.md)
- [カメラ試験](../../tools/module_test_lab/README_CAMERA_SIM_JA.md)
- [自律走行・降下・SIL](../../tools/module_test_lab/README_MISSION_SIM_JA.md)

完全に未設定のWindows/Ubuntuからの導入は別環境での確認が必要。
検証範囲はこのフォルダーの資料と各試験ガイドに記す。

## この版で確認したこと

- Ubuntu以外・別バージョンの拒否、既存ROS配布元の保持、SHA256不一致の拒否。
- dry-runがファイルを作らず、外部venvへのリンクを変更しないこと。
- スペースを含む別フォルダーの作業ツリーコピーと、そこに作った新規venvで
  GUI依存導入・環境診断・通常X11のQt初期化が成功。
- 公式ROS apt-source配布物の実ダウンロードと固定SHA256の一致。

この検証は既存ROS環境を利用した。ホストに不足していたlibxcb-cursor0は
検証用の一時領域だけに展開し、ホストのapt導入は行っていない。
そのため、未設定のOSへのROS初回導入や、別PCのGPU動作まで確認したものではない。

Windows PowerShellからも、スペースを含むWSL側コピーの診断を呼び出し、
ディストリビューションとパスの自動解決が成功することを確認した。
ホストへのQtライブラリ導入がまだの場合、実際の診断はその不足をFAILとして表示する。

外部ROS 2コードで仮想入力を試す場合は [仮想センサー接続ガイド](VIRTUAL_BENCH.md) を参照。

班内配布と担当別検証の入口は [配布チェックリスト](RELEASE_CHECKLIST.md) を参照。
