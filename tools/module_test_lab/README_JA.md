# 現在のリポジトリからの起動

INO直下の `start-module-test-lab.bat` を開く。
初回セットアップとカメラ試験は [Gazebo カメラ試験](README_CAMERA_SIM_JA.md) を参照。
ROS 2はカメラ試験の起動時に使用し、既存の着地・仮想CAN試験には不要。

以下は既存機能の説明です。旧ZIP配布時の導入先ではなく、このリポジトリ内のコードを使用してください。

# CanSat Module Test Lab v2 — 個別実験とチーム記録集約

**既存の `~/cansat_ws`（ROS 2統合シミュレーター）は変更しません。**

ESP32-S3 / Arduino IDE の担当者が作った実験結果を整理し、各メンバーの結果を共有ZIPまたはGitHubで持ち寄って集約するための独立した試験アプリです。

## GitHub同期（v2で追加）

GitHub CLIで認証済みのアカウントを使い、GUIの「実験記録・チーム共有」タブに以下を追加しました。

- **接続確認**: `CanSat-INO/INO` の `main` にアクセスできるか確認する。
- **選択結果をGitHubに送信**: 行を選択して実験記録と添付ログを送信。送信前に確認画面を表示する。
- **チーム結果をGitHubから取得**: ほかの担当者が送信した記録をローカル台帳に取り込む。

実験1件につき `experiments/records/<ID>.json` をGitHubに作り、添付ログは `experiments/attachments/<ID>/<ファイル名>` に保存します。添付は1個900KB以下の制限があります（それ以上の動画・ログは別ストレージで共有）。同一IDで内容が異なる場合は**上書きせず停止または競合として報告**します。

- **GitHub Projectsへの自動登録や実際のArduino `.ino` の動作試験はまだ未実装です。**
- GitHubへの書き込みはボタンを押した時だけで、ブランチ `main` に実験**データ**を直接追加します。リポジトリの権限・ブランチ保護設定により書き込みが拒否される場合があります。
- 既存の `~/cansat_module_lab_data` は引き続き使い、ZIP共有とCSV出力も残します。

詳しくは `README_GITHUB_SYNC.md` を参照してください。

## この版でできること

1. 仮想IMU・BME280の**5種類のシナリオ**で、着地判定の**参考Pythonアルゴリズム**を試す。
2. 接地時刻・判定時刻・遅延を確認し、仮想センサーのCSVも保存する。
3. チームメンバーがArduino IDEで試した**実機試験**や**ほかのシミュレーター**の結果を、コード版・実験者・期待値・結果・ログとともに登録する。
4. 試験結果を**ZIPで共有**し、集約担当者が**取り込む**。実験IDが同じなら重複登録せず、同じIDで内容が異なる場合は上書きせず衝突件数を表示する。
5. 集約データを**CSVで一括出力**する。

> **重要**: この版で動く着地判定は「参考アルゴリズム」です。Arduino IDEの `.ino` をそのまま動かすものではありません。また、実機モジュールの動作を保証するものではありません。

## インストール（Windows の WSL2 / Ubuntu-restore-test）

先に、今まで使ってきた `~/cansat_gui_venv` に PySide6 が入っていることを確認してください。

```powershell
wsl -d Ubuntu-restore-test -u cansat --cd ~
```

ZIPをWindowsの**ダウンロード**に保存してから、Ubuntuで実行:

```bash
mkdir -p ~/cansat_module_lab
python3 -m zipfile -e /mnt/c/Users/*/Downloads/cansat_module_test_lab_v1.zip ~/cansat_module_lab
```

ZIP内にはフォルダではなく直接 `app.py`, `landing_sim.py`, `records.py` が入っています。

起動:

```bash
~/cansat_gui_venv/bin/python ~/cansat_module_lab/app.py
```

ROS 2 の起動や `colcon build` は不要です。

## チーム内の共有の仕方

- 開発担当者: Arduinoプログラムを試験 → 実験記録タブで記録＋ログ添付 → 記録行を選択 → **「選択結果を共有ZIPに出力」** → チームへ送付。
- 集約担当者: **「共有ZIPを取り込む」** → チームメンバーのZIPを順次取り込み → **「CSVで全結果を出力」**。
- ZIP共有は手動です。v2はGitHubの送信・取得ボタンで手動同期できますが、リアルタイム同期ではありません。

データは `~/cansat_module_lab_data` に保存され、プログラムのZIPを更新しても残ります。バックアップ時はこのフォルダも保管してください。

## Arduino担当者と決めておくログ仕様（推奨）

`time_ms,imu_z_mps2,pressure_pa,landing_detected`

1行ごとに時刻（ms）、加速度Z（m/s²）、気圧（Pa）、判定結果（0/1）を記録すると、次のバージョンで自動比較につなげやすくなります。実際のArduinoのコードをPCで動かすには、判定ロジックの共通化（C++を独立モジュールへ）や、ESP32実機とのシリアル通信アダプターが別途必要です。

## 自動テスト

```bash
cd ~/cansat_module_lab
python3 -m unittest discover -s tests -v
```

## 補足

- 設計書にあるメインESP32-S3・カメラ・ドライブのモジュール分割方針を想定しています。
- 分離/展開/駆動/通信の**記録カテゴリ**は用意しましたが、それぞれのシミュレーション物理モデルはまだ追加していません。
- 添付ログの上限は1ファイルあたり10MBです。
- 共有ZIPを取り込むときには保存済みのIDとの重複を判定します。内容が異なる同一IDは安全のため上書きしません。
