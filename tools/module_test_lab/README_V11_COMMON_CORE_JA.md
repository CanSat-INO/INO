# CanSat Module Test Lab v11 — シミュレーション共通基盤

## 目的
INOとREGULUSを将来統合するための、ROS 2非依存の**設定・出力形式の第一版**です。
既存v10の機能を変更せず、`シミュレーション共通基盤`画面を追加します。

## 機能
- 機体設定：機体名、質量、重心、車輪径、タイヤ幅、最大トルク。
- 環境設定：地形名、段差高さ、重力加速度。
- 初期状態：位置、姿勢（xyzwクォータニオン）、速度。
- v8の仮想CANシナリオ8種類を選んで実行。
- 設定JSON保存・読込、仮想CAN実行結果のJSON・CSV出力。
- 共通JSONにスキーマ名とバージョンを付与し、単位をキーに明示。
- 実行結果に元の仮想CANイベントと評価を残す。

## 重要な制限
- **機体質量、車輪径、段差、重力、初期状態はv11ではメタデータです。** 仮想CANの計算結果は変わりません。
- 位置、姿勢、速度の時系列は未計算のためJSONではnull、CSVでは空欄で出力します。ゼロと偽装しません。
- 走破性、衝突、摩擦、モーター動力学、3D描画はまだ未実装です。
- ROS 2/Gazebo、REGULUS、実機CAN、C++の実行連携は今回行いません。
- `physical_parameters_applied: false` と `source: ino.virtual_can.v8` を出力に明示します。
- v9の実験台帳への自動登録やGitHubへの自動送信も行いません。

## ファイル形式
- 設定JSON: `schema=cansat.simulation.common`, `version=1`。
- 結果JSON: `schema=cansat.simulation.run`, `version=1`。
- 姿勢: `[x,y,z,w]`（正規化クォータニオン）。座標系の実機・ROS変換規約は今後定義が必要です。
- 時刻: 仮想CAN開始からの相対秒（`time_s`）。
- CSV: `time_s, position_x_m, ... , source, target, message, event, detail`。
- JSONはUTF-8、CSVはUTF-8 BOMで保存します。

## 導入
1. Gitブランチ `feature/simulation-common-core` であることを確認し、既存の未コミット変更を整理。
2. ZIPを別ディレクトリに展開し、リポジトリルートから `python3 /path/to/install_simulation_common.py` を実行。
3. インストーラーはapp.pyをバックアップして4ファイルを追加し、新規21テストを実行。失敗時は元に戻します。
4. 既存テスト全体を実行: `cd ~/INO-module-lab/tools/module_test_lab && ~/cansat_gui_venv/bin/python -m unittest discover -s tests -v`
5. GUI: `cd ~/INO-module-lab && QT_QPA_PLATFORM=xcb ~/cansat_gui_venv/bin/python -u -X faulthandler tools/module_test_lab/app.py`

## 手動確認
1. ホームの「シミュレーション共通基盤」を開き、初期値で正常シナリオを実行。
2. JSON/CSVを出力し、時刻・イベント順序・物理量空欄・`physical_parameters_applied=false` を確認。
3. 車輪径を変えて設定JSON保存→読み込み→同じ値になることを確認。
4. 車輪径を変えても仮想CANの結果が変わらないことを確認（v11仕様）。
5. `Drive走行指令の欠落` を実行し、欠落とタイムアウトが残ることを確認。
6. 既存のv10 C++個別試験・統合実験結果が開けることを確認。
7. GUIを閉じて終了コード0、Git差分は想定5ファイルのみであることを確認。

## 今後
REGULUS側で同じ設定・結果形式を採用するためには、座標系、時刻基準、モデル識別子、物理量の定義を調整し、バージョン2などで後方互換性を設計します。既存INOのROS 2構成は維持します。
