# 仮想センサーで担当コードを試す

正式環境は Ubuntu 26.04 / ROS 2 Lyrical Luth / Gazebo Jetty。最初に [初回セットアップ](README.md) を行う。

## Test Lab

start-module-test-lab.bat を開き、「自律走行・降下・SIL」から「仮想センサー単独（外部ROS接続）」を選ぶ。「初期設定を読込」で既定の地上ワールドを選択し、「起動」を押す。設定ファイルを開く操作で外部プログラムは起動しない。外部コードは別端末で起動する。起動ログに結果フォルダーが表示される。停止して再起動すると新しい結果フォルダーを作る。車体・障害物は地上用設定ファイルで変更できる。

## CLI と外部ワークスペース

リポジトリ直下の端末で起動する。RTAB-Map、経路計画、自律走行ノードは起動しない。

~~~bash
bash ros2_ws/src/ino_mission_sim/scripts/start-virtual.sh
# 走行試験を行うセッションのみ
bash ros2_ws/src/ino_mission_sim/scripts/start-virtual.sh drive:=true
~~~

別の Ubuntu 端末で examples/virtual_client を独立したワークスペースにコピーする。シミュレーター側のワークスペースをビルドする必要はない。

~~~bash
source scripts/ros-environment.sh
mkdir -p ~/ino-virtual-client-ws/src
cp -r examples/virtual_client ~/ino-virtual-client-ws/src/
cd ~/ino-virtual-client-ws
colcon build
source install/setup.bash
export ROS_DOMAIN_ID=67 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 run ino_virtual_client probe --ros-args -p use_sim_time:=true
~~~

走行を有効化したセッションでは probe の後に --drive を指定する。制御端末は一つに絞り、停止時にゼロ速度を送る。走行ゲートはDDSで検出した指令元が1つの場合だけ、直近0.35秒以内の指令を転送する。それ以外はゼロ速度を送る。仮想環境専用の仕組みで、実機の安全制御には使わない。既定では走行ブリッジは無効。

## 暫定インターフェース

| Topic / Service | 内容 |
|---|---|
| /raw/{left,right}/image | 左右のGazebo画像 |
| /raw/{left,right}/camera_info | 左右のカメラキャリブレーション |
| /ground/imu | Gazebo IMU |
| /ground/encoder_odom | 履帯速度から得る仮想エンコーダー相当 |
| /odom、/tf、/tf_static | IMU・履帯による推定姿勢とカメラ固定TF |
| /clock | シミュレーション時刻 |
| /ground_truth/odom | 採点・比較用の真値。推定側は購読しない |
| /virtual/capture | std_srvs/Trigger。直近の同期ペアを保存し、Capture IDと保存先を返す |
| /cmd_vel | geometry_msgs/Twist。drive:=true のセッションでGazeboへ転送 |

撮影要求は直近の新鮮な同期フレームを保存する。露光開始をトリガーする機材の模擬は未実装。結果には左右PNG、CameraInfoのROSシリアライズデータ、時刻JSONを保存する。camera_fps、imu_hz、disable（カンマ区切りのブリッジ名）、topics（YAML形式のリマップ）、config（既存地上設定ファイル）を起動引数で指定できる。画像購読にはセンサー向けQoSを使用する。QoS・生成元の切替、GNSS・地磁気・気圧・機構状態は未実装。

## 記録・再生

[配布手順の記録・再生](RELEASE_CHECKLIST.md#録画データを使う) を参照。センサー専用の許可リストで記録・再生する。Playerを一時停止で起動し、左右画像のSubscriberが見えてから再開する。

## 担当別の入口

- 画像処理は外部ワークスペースで左右画像、CameraInfo、IMU、推定オドメトリ、TF、Clockを使える。視差・点群・地図などの生成ノードは各担当が実装する。
- Cameraは外部ROSから同期画像とCapture IDを取得できる。機体側C++ひな形へのアダプターと仮想通信は今後の作業。
- DriveはCLIで走行ブリッジを有効にしたセッションで、外部ROSから仮想機体へ指令できる。機体側C++の接続と機構動作は今後の作業。
- Mainは既存の降下SIL接続例で仮想入力を試せる。Mainひな形、Camera/Drive応答、CAN・TWELITEを束ねる交換機構は今後の作業。
- 地上局の仮想テレメトリ・Wi-Fi画像への接続は今後の作業。

既存の地上自律走行とカメラ試験は、RTAB-Mapを使う比較用の入口として利用できる。

## 正式環境での確認

Ubuntu 26.04 でこの作業ツリーを開き、bash scripts/setup.sh と bash scripts/doctor.sh --ros-only を実行する。JettyのバージョンとROSの依存を診断してから、上の別ワークスペース手順を実行する。センサー受信、撮影結果、drive:=true での走行、GUIからの停止と再起動、隔離ドメインでの再生を順に確認する。公式対象のUbuntu 26.04では、セットアップ後に doctor のROS診断が通ることを確認する。Jazzyでの受信実績と正式環境の進捗は [配布チェックリスト](RELEASE_CHECKLIST.md) に記載する。

担当別に仮想モジュールと外部コードを切り替える場合は [担当者別試験](MODULE_BENCH.md) を参照。

## センサーの限界

履帯オドメトリは仮想エンコーダー相当の推定値。簡易な接触・摩擦モデルのため、実機のすべりや走破性の評価には別途実機試験が必要。Ground Truthは評価用の /ground_truth/odom に分離し、担当コードへの標準入力や自己位置推定の代用にしない。
