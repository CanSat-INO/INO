# シミュレーター配布準備

## 最初の起動

1. Windows 11ではWSL2のUbuntu 26.04を選ぶ。Ubuntu内で作業ツリーを取得する。未公開の変更を試す場合は、それらを含む作業ツリーが必要。
2. リポジトリ直下で bash scripts/setup.sh --system-only を実行する。sudoが求められたらUbuntuのパスワードを入力する。
3. bash scripts/doctor.sh --ros-only を実行する。Test Lab用の環境も必要なら bash scripts/setup.sh を使う。
4. start-module-test-lab.bat または bash tools/module_test_lab/launch_ino.sh から「仮想センサー単独（外部ROS接続）」を開く。
5. 担当プリセットを選び、起動ログでROS_DOMAIN_IDと実験フォルダーを確認する。別端末では source scripts/ros-environment.sh の後、同じROS_DOMAIN_IDと ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST を指定する。

[共通設定とトラブルシューティング](README.md) · [Main・Camera・DriveのC++接続](MODULE_BENCH.md) · [画像処理の独立ROSワークスペース](VIRTUAL_BENCH.md)

## Drive

bash scripts/verify-virtual-drive.sh で、仮想Mainから仮想CANを経由して外部C++ Driveを接続する。前後進・左右旋回を試し、Ground Truth と仮想エンコーダーの距離を別々に表示する。同じドメインで試験中の場合は別ドメインを INO_DRIVE_TEST_DOMAIN に指定する。

展開はMock Driveの論理試験。Mainから kind=deploy、release_confirmed=true、landing_confirmed=true の試験値を送る。初期状態は undeployed。deploying の後に deployed、または bench_fault:=deployment_failure で failed へ進む。機構の形状や動力の入力は変更しない。

## 地上局

地上局開発プリセットを起動して、仮想Mainから撮影を要求する。[撮影要求の例](MODULE_BENCH.md#最小の操作)

Node.js環境があるWSL内で、地上局ディレクトリーから以下を実行する。

~~~bash
npm ci
INO_VIRTUAL_UI=1 INO_VIRTUAL_RUN_DIR=/absolute/path/to/testlab/run npm run dev
~~~

ブラウザーで [仮想地上局](http://localhost:5173/?view=virtual) を開く。選択したフォルダーの module-events.jsonl から仮想センサー、テレメトリ、ミッション・モジュール状態、左右PNG、Capture ID、取得時刻と異常を表示する。状態は業務イベントが届いたときに表示する。APIとViteの開発用プロキシは同じPCで起動する。バックエンドはループバック限定の読取専用で、シリアルを開かない。点群・地図・本番通信形式の連携は対象外。

## 録画データを使う

Liveセッションと同じROS_DOMAIN_IDを指定してセンサーだけを記録する。

~~~bash
bash scripts/sensor-bag.sh record /tmp/ino-sample
~~~

Ctrl+Cで記録を終了してLive試験を停止する。再生用の別端末では source scripts/ros-environment.sh を実行し、次の購読を先に開始する。

~~~bash
export ROS_DOMAIN_ID=76 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
python3 examples/virtual_client/probe.py --replay --ros-args -p use_sim_time:=true
~~~

再生端末で bash scripts/sensor-bag.sh play /tmp/ino-sample を実行する。Playerは一時停止から始まる。購読端末と同じROS環境・ROS_DOMAIN_ID・RMWで、三つ目の端末から以下を実行する。

~~~bash
source scripts/ros-environment.sh
export ROS_DOMAIN_ID=76 ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST
ros2 topic info /raw/left/image -v
ros2 service call /rosbag2_player/resume rosbag2_interfaces/srv/Resume '{}'
~~~

PublisherとSubscriberが1件ずつ見え、Reliableで適合していることを確認してから再開する。購読サンプルは左右の同時刻ペアが3組揃ったら件数を表示する。再生側が許可するのはセンサー・TF・Clockのみ。Gazeboを停止し、録画本体はGit外で共有する。

## 異常条件と証跡

- bench_fault:=camera_right_missing で保持枠へ入れる前に片側欠損を検出する。wifi_down で保持と仮想転送を分けて確認する。
- Cameraの保持枠は8件。Capture IDは正の単調増加整数。重複・逆順の要求は実行しない。
- 0.35秒の速度ゲートは単調増加する実時間を使う。複数発行元を検出すると、保持した指令も失効する。
- 生成された effective YAML、イベントJSONL、撮影PNG、Capture ID、起動ログ、MCAPは実験フォルダーと一緒に保管する。environment.txt にGitコミット、ROS_DISTRO、Gazebo版、起動引数が保存される。作業ツリーに未コミット変更がある場合は別途その差分を残す。

## 配布前の検証状況

Ubuntu 26.04.1 / Lyrical / Jetty 10.5.0 で doctor が通り、ROSパッケージ3件のcolconビルド、機体C++ひな形のCTest 3件、pytest 398件を確認。18件のスキップは別配布ZIPのインストーラー試験。

このWSL環境ではFast DDSのLOCALHOSTでGazeboを介さないROS 2別プロセス間通信もタイムアウトした。シミュレーターの起動だけで合格とせず、別ワークスペースの購読まで試す。検証では次節のループバック限定Zenohを使用した。

| Drive計測 | Jazzy / Harmonic | Lyrical / Jetty + Zenoh |
|---|---:|---:|
| 前進 Ground Truth / encoder | 0.2295 / 0.2262 m | 0.0666 / 0.0650 m |
| 後退 Ground Truth / encoder | 0.2297 / 0.2274 m | 0.1995 / 0.1992 m |
| 左旋回 Ground Truth | +0.8680 rad | +0.4585 rad |
| 右旋回 Ground Truth | −0.9311 rad | −0.6819 rad |

両試験とも指令途絶・複数発行元・重複解消後の古い指令拒否・新規指令での復帰を確認。各区間は壁時計で計測するため、負荷とシミュレーション時刻の進み方も距離に影響する。この測定だけで物理エンジン差を定量化できない。Lyrical試験ではZenohが500 msを超える時刻差を報告し、内部の時刻を置き換えるログも観測した。WSLの時刻やDDS設定は変更していない。

## 正式環境の実動結果

配布判定は B。Ubuntu 26.04 のこのWSL環境では、以下をループバックZenoh使用条件で確認した。標準Fast DDSの別プロセス疎通と時刻差の原因は未解決。

- SLAMなしで、別colconワークスペースのサンプルが左右画像・CameraInfo・IMU・エンコーダー相当・TF・Clockを購読し、撮影に成功。JettyのWSLgウィンドウ生成とカメラのソフトウェア描画も確認。
- 外部MainとCameraのC++例に交換し、Capture ID 1の撮影・左右PNG保持・仮想転送通知を確認。Driveは既存の検証スクリプトで測定。
- 55.1 MiBのMCAPを記録後、Gazeboを終了して別ドメインで再生。左右画像各3件、CameraInfo左2件・右3件、IMU 22件、Clock 210件を外部ノードで受け、左右同時刻の3組を確認。制御Topicは再生対象外。
- Jettyの一時停止でClockが停止し、走行指令が失効した。再開後も新規指令まで停止を維持し、リセット時はClockの巻き戻りと停止を確認。
- Test LabのWSLg実ウィンドウで担当別試験の起動・停止を2回確認。地上局はWindows Edgeのヘッドレス実ブラウザーで、テストデータの状態・Capture ID時刻・異常・左右PNG描画を確認。Lyricalのライブセッションから地上局までの通し試験は未実施。

## LyricalでFast DDSの別プロセスが見えない場合

同じWSL内の端末で以下を実行し、ループバックだけで待ち受けるルーターを起動する。ポート17688が使用中なら両設定のポート番号を同時に変更する。

~~~bash
source scripts/ros-environment.sh
cfg="$(mktemp -d)"
defaults="$(ros2 pkg prefix --share rmw_zenoh_cpp)/config"
sed 's@tcp/localhost:7447@tcp/127.0.0.1:17688@g' "$defaults/DEFAULT_RMW_ZENOH_SESSION_CONFIG.json5" > "$cfg/session.json5"
sed 's@tcp/\[::\]:7447@tcp/127.0.0.1:17688@g' "$defaults/DEFAULT_RMW_ZENOH_ROUTER_CONFIG.json5" > "$cfg/router.json5"
printf '%s\n' "$cfg/session.json5"
ZENOH_ROUTER_CONFIG_URI="$cfg/router.json5" "$(ros2 pkg prefix rmw_zenoh_cpp)/lib/rmw_zenoh_cpp/rmw_zenohd"
~~~

別端末では、表示されたセッション設定のパスを使う。Test Lab、外部ノード、Drive検証、録画・再生はすべて同じ設定を読み込んだ端末から起動する。録画と再生の隔離ドメインは従来どおり分ける。

~~~bash
source scripts/ros-environment.sh
export RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_SESSION_CONFIG_URI=/tmp/作成されたフォルダー/session.json5
bash scripts/verify-virtual-drive.sh
~~~


## コミットの分割案

1. セットアップ・環境対応。scripts の共通ROS環境、セットアップ、doctor、requirements、Windows入口と既存カメラ側の起動変更を一緒に含める。doctorが参照するミッション・SILのファイルは第2コミットと同時に実行可能になるため、各コミット単体でdoctorを通すには第1・第2を統合する。
2. 仮想センサー・モジュール・Test Lab。ros2_ws のカメラ・ミッション連携、cansat/sil、tools/module_test_lab、外部サンプルと関連試験を含める。
3. 配布。ground_station のシミュレーションAPIとビュー、scripts の記録再生とDrive試験、docs/setup の担当別手順。記録再生の外部probeに依存する変更もここに含める。

mainの取り込みは既存のマージコミットに含まれる。ローカル環境設定、シークレット、ビルド生成物、ログ、MCAP、バックアップをステージング対象から外す。旧機体のArduino原本は再配布権限を確認できるまでローカルの参照用とする。通常の仮想試験とソース提供済みのC++接続例には不要。

## 配布用PR説明文案

CanSat INØのソフト班が実機なしで担当コードを試せる仮想開発環境を追加します。ステレオ・IMU・TF・Clockの配信、Main/Camera/Driveの担当別差し替え、C++と外部ROSノードの接続、地上局バックエンド向けのローカル試験API、制御Topicを含まないセンサー記録再生を含みます。

Jazzy / Harmonicの検証では外部Drive C++から前進・後退・左右旋回し、指令途絶・重複時の停止と新規指令での復帰を確認しました。正式対象はUbuntu 26.04 / Lyrical / Jettyです。Jazzyではセンサーだけを別ドメインに再生し、左右画像の同時刻ペアを外部ノードで確認済みです。地上局は開発用の読取専用画面から確認できます。Lyrical / JettyではループバックZenohを使って仮想センサーと外部接続を確認しました。このWSL環境でのFast DDSの別プロセス疎通は未解決です。
