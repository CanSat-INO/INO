# CanSat Module Test Lab v1 — 個別実験とチーム記録集約

**既存の `~/cansat_ws`（ROS 2統合シミュレーター）は変更しません。**

ESP32-S3 / Arduino IDE の担当者が作った実験結果を整理し、各メンバーの結果を共有ZIPで持ち寄って集約するための独立した試験アプリです。

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
- この方法は手動共有です。クラウドに自動同期したり、リアルタイム共同編集する機能はありません。

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
