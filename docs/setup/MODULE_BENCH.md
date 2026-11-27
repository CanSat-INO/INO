# 担当者別の仮想モジュール試験

正式環境は Ubuntu 26.04 / Lyrical / Jetty。依存が不足している 26.04 環境では、リポジトリ直下から bash scripts/setup.sh --system-only を実行し、必要な apt 操作に sudo パスワードを入力する。その後 bash scripts/doctor.sh --ros-only を実行する。GUI環境も未導入なら bash scripts/setup.sh を使う。

## Test Lab

「自律走行・降下・SIL」で「仮想センサー単独（外部ROS接続）」を選択し、「担当者別構成」を選び「起動」を押す。外部プログラムは下記の別端末から明示的に起動する。設定ファイルの読込では実行されない。終了は「停止」。起動ログに結果の場所が表示され、module-events.jsonl に時系列のイベントが保存される。停止後は結果一覧の「担当者別試験」を選んで保存先を開ける。

| プリセット | Main | Camera | Drive | 画像処理 | 地上局 |
|---|---|---|---|---|---|
| main | External | Mock | Mock | Disabled | Disabled |
| camera | Mock | External | Mock | Disabled | Disabled |
| drive | Mock | Mock | External | Disabled | Disabled |
| vision | Mock | Mock | Disabled | External | Disabled |
| all | Mock | Mock | Mock | Disabled | Mock |
| station | Mock | Mock | Disabled | Disabled | Mock |

## CLI と交換

第1端末で、例えば次のように起動する。

~~~bash
bash ros2_ws/src/ino_mission_sim/scripts/start-virtual.sh bench:=main drive:=true
# CameraとDriveだけ外部コードに切り替える例
bash ros2_ws/src/ino_mission_sim/scripts/start-virtual.sh bench:=all bench_set:=camera=external,drive=external drive:=true
~~~

第2端末は同じROSドメインを使用する。下記では、付属の短命なPC用C++試験アダプターをコンパイルする。独自アダプターを試す場合はコンパイル対象またはバイナリを差し替える。

~~~bash
source scripts/ros-environment.sh
export ROS_DOMAIN_ID=67 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
work="$(mktemp -d)"
g++ -std=c++17 examples/module_adapters/adapter.cpp -o "$work/adapter"
python3 examples/module_adapters/connect.py main "$work/adapter"
~~~

camera / drive を試す場合は末尾の main を該当担当名に変更する。C++サンプルは1要求ごとに起動して標準入出力で応答する。状態を保持する外部コードは、ROS 2 の String型 /bench/<担当>/input を購読し、/bench/<担当>/output にJSONで応答する常駐ノードとして接続できる。EXTERNALの担当だけがこの入口を持つ。

### 最小の操作

Mock Main では /bench/scenario へ試験指示を送る。

~~~bash
ros2 topic pub --once /bench/scenario std_msgs/msg/String '{"data": "{\"kind\": \"capture\"}"}'
ros2 topic pub -r 10 /bench/scenario std_msgs/msg/String '{"data": "{\"kind\": \"drive\", \"linear_mps\": 0.06, \"angular_radps\": 0.0}"}'
~~~

走行の試験は drive:=true が必要。指令を出す端末は1つで、Ctrl+Cで指令を止めるとゲートがゼロ速度を送る。画像処理は [仮想センサーガイド](VIRTUAL_BENCH.md) の外部ワークスペースを使う。vision の選択は外部コードを起動する設定ではない。RTAB-Mapは既存の比較用カメラ・自律走行モードから起動する。

## 暫定契約と観測

- 受信・送信を試験する論理JSONで、channel は can / twelite / wifi / ros の経路区別。物理フレーム、ビットレート、無線プロトコルは未定義。
- Main は capture に正の単調増加整数 capture_id を付与する。Mockシナリオで省略したときは仮想Mainが発番する。受付と取得完了、保持応答、仮想転送は別イベント。取得は既存サービスの同期ペアを利用し、要求時にClockを受信済みなら要求時刻以前のペアを除外する。露光開始と再送制御は未実装。snapshot_id が画像の生成時刻に対応する。
- Camera の capture_input には左右PNGのパスが入る。Camera C++サンプルは左右を開いて image_retained を返す。保持枠は8件。release_capture で論理枠を解放し、実験成果物は保持する。station の image_transfer はローカルファイル参照の通知で、実データの無線転送や既存地上局での受信確認は含まない。
- Drive の drive_request には前進速度 m/s、旋回速度 rad/s、仮想エンコーダー情報、request_id が入る。0.25秒以内の未消費IDで返された motor を速度ゲートへ渡す。左右PWMや展開・分離の実行は未実装。速度ゲートは実時間で0.35秒の期限を扱う。
- Ground Truthは独立した評価用Topic。IMU・エンコーダーにはGazebo由来の時刻を付ける。別起動の module_bench.py では --manual-sensors に、例えば {"pressure":{"value":101325,"unit":"Pa","frame":"bench","valid":true}} を含むJSONファイルを指定できる。固定入力には source=manual_fixture、stamp_ns=null が付く。gnss、magnetic_field、temperature、battery_voltage、mechanismも入力できる。物理モデルのセンサー値ではない。
- 別起動時の --fault は motor_stop または wifi_down を指定できる。Heartbeat、ACK、遅延、通信欠損などの異常注入は今後の作業。
- 既存地上局への入口はシリアル受信と既存テレメトリ形式。今回の試験イベントは /bench/events とJSONLへ出す。ローカルの読取専用地上局バックエンド接続は [配布ガイド](RELEASE_CHECKLIST.md#地上局) を参照。読取専用の確認画面は開発環境の /?view=virtual で利用する。本番通信への接続は対象外。

動作確認は Jazzy / Harmonic。Lyrical / Jetty では上記設定後、左右画像、撮影結果、走行ゲート、GUI停止と再起動を確認する。

## 担当コードの準備

Team用のシミュレーション契約は暫定JSONで、本番のCAN ID、TWELITEのフレーム、Wi-Fiの転送方式を決めるものではない。Main・Camera・Driveの本番ひな形にある NotImplemented は、本番担当が実装する。付属のC++例で確認できるのは仮想入力の受信、画像保持応答、速度指令の接続まで。論理展開の状態変化だけで物理機構の展開を確認した扱いにはしない。
