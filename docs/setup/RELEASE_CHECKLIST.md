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

ブラウザーで [仮想地上局](http://localhost:5173/?view=virtual) を開く。選択したフォルダーの module-events.jsonl から仮想センサー、テレメトリ、ミッション・モジュール状態、左右PNG、Capture ID、取得時刻と異常を表示する。状態は業務イベントが届いたときに表示する。APIとViteの開発用プロキシは同じPCで起動する。バックエンドはループバック限定の読取専用で、シリアルを開かない。点群・地図・本番通信形式の連携は対象外。イベントが4秒間更新されない場合は停止または更新待ちと表示する。再起動で結果フォルダーが変わる場合は、バックエンド起動時に指定したローカルのシンボリックリンクを次のフォルダーへ向けるか、そのフォルダーを指定してバックエンドを起動し直す。

## 録画データを使う

Liveセッションと同じROS_DOMAIN_IDを指定してセンサーだけを記録する。

~~~bash
bash scripts/sensor-bag.sh record /tmp/ino-sample
~~~

Ctrl+Cで記録を終了してLive試験を停止する。再生用の別端末では source scripts/ros-environment.sh を実行し、次の購読を先に開始する。

~~~bash
export ROS_DOMAIN_ID=76
source scripts/sim-environment.sh
ino_sim_wait
python3 examples/virtual_client/probe.py --replay --ros-args -p use_sim_time:=true
~~~

再生端末で bash scripts/sensor-bag.sh play /tmp/ino-sample を実行する。Playerは一時停止から始まる。購読端末と同じROS環境・ROS_DOMAIN_ID・RMWで、三つ目の端末から以下を実行する。

~~~bash
source scripts/ros-environment.sh
export ROS_DOMAIN_ID=76
source scripts/sim-environment.sh
ino_sim_wait
ros2 topic info /raw/left/image -v
ros2 service call /rosbag2_player/resume rosbag2_interfaces/srv/Resume '{}'
~~~

PublisherとSubscriberが1件ずつ見え、Reliableで適合していることを確認してから再開する。購読サンプルは左右画像と同時刻の左右CameraInfoが3組揃ったら件数を表示する。再生側が許可するのはセンサー・TF・Clockのみ。Gazeboを停止し、録画本体はGit外で共有する。

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

配布判定は B。Ubuntu 26.04 のこのWSL環境でループバックZenohを検証した。別PCでのセットアップ、時刻補正の発生源、負荷時のDriveの予期しないゼロ遷移が未解決のため A 判定は保留。Fast DDSの不通だけを配布条件にはしない。

- SLAMなしで、別colconワークスペースのサンプルが左右画像・CameraInfo・IMU・エンコーダー相当・TF・Clockを購読し、撮影に成功。JettyのWSLgウィンドウ生成とカメラのソフトウェア描画も確認。
- 外部MainとCameraのC++例に交換し、Capture ID 1の撮影・左右PNG保持・仮想転送通知を確認。Driveは既存の検証スクリプトで測定。
- 55.1 MiBのMCAPを記録後、Gazeboを終了して別ドメインで再生。左右画像各3件、CameraInfo左2件・右3件、IMU 22件、Clock 210件を外部ノードで受け、左右同時刻の3組を確認。制御Topicは再生対象外。
- Jettyの一時停止でClockが停止し、走行指令が失効した。再開後も新規指令まで停止を維持し、リセット時はClockの巻き戻りと停止を確認。
- Test LabのWSLg実ウィンドウで担当別試験の起動・停止を2回確認。地上局はWindows Edgeのヘッドレス実ブラウザーで、テストデータの状態・Capture ID時刻・異常・左右PNG描画を確認。今回、Jettyの実セッション2回をEdgeで確認し、仮想テレメトリ・センサー・展開状態、左右PNG、Capture IDと取得時刻、重複IDエラー、更新停止表示と別セッションへの再接続まで確認した。

## 班員向けの起動手順

リポジトリをLinuxのホーム配下へ取得し、初回は bash scripts/setup.sh と bash scripts/doctor.sh を実行する。sudo認証は依存導入時だけ必要。Test Labは bash tools/module_test_lab/launch_ino.sh を開き、「仮想センサー単独（外部ROS接続）」で担当プリセットを選ぶ。CLIでは bash ros2_ws/src/ino_mission_sim/scripts/start-virtual.sh bench:=all を使用する。

Lyricalで推奨する仮想ベンチのRMWはZenoh。仮想ベンチまたはバッグ再生を起動すると、そのコマンドがループバック限定ルーターを起動し、TCP待受を確認してから子プロセスを開始する。終了時は所有するルーターと子プロセスだけを止める。同じドメイン・ポートでの重複起動は拒否する。地上航法・降下など既存ランチャーの専用構成とは別。JazzyのRMW既定値は変更していない。

別端末ではシミュレーターと同じドメインで次を実行する。録画はライブと同じドメイン、再生とその購読側は既定の76を使う。既定の仮想ベンチは67。

~~~bash
export ROS_DOMAIN_ID=67
source scripts/sim-environment.sh
ino_sim_wait
ros2 topic list --no-daemon
~~~

TCP準備確認の後も、実際のTopic疎通は ros2 topic info /raw/left/image -v で確認する。ログはランチャーの起動ログと、ユーザーランタイム領域の ino-sim/domain-67/router.log にある。既存ルーターを使う場合は ZENOH_SESSION_CONFIG_URI を指定できる。別RMWを試す場合は全端末で同じ RMW_IMPLEMENTATION を明示する。Fast DDSはこのWSL環境のGazeboなしの最小別プロセス試験で受信がタイムアウトした。静的ループバックピアとUDP指定でも解消せず、OS・ネットワークの設定は変更していない。

## 時刻とステレオ整合性

Ubuntu 26.04.1で rmw_zenoh_cpp 0.10.6、zenoh-c 1.8.0 を確認。Jetty走行や一時停止試験のルーター・参加プロセスで、次の警告を観測した。

~~~
zenoh::net::routing::dispatcher::pubsub: Error treating timestamp for received Data (incoming timestamp from e0eb6efcf7008a1b15a1adc185e5f015 exceeding delta 500ms is rejected: 2026-11-27T10:31:48.577376206Z vs. now: 2026-11-27T10:31:47.020223979Z). Replace timestamp: Some(7712797080297598290/e0eb6efcf7008a1b15a1adc185e5f015)
~~~

Zenohのルーティング層がHLCの通信メタデータを付け替えた記録。ROSメッセージ内のheader.stampやGazeboの /clock とは区別する。WSL内では実時間と単調時計の関係が約1.69秒戻る瞬間を観測した。別の単発Windows–WSL測定ではWSL採時値はWindowsの呼出し前後の区間内にあった。時計補正の発生源やスリープ・復帰との因果関係、VO/SLAMやIMU融合精度への影響は未特定。ログを抑制していない。異常が続くセッションでは画像・IMU・TFの時刻と保存結果を確認し、検証結果を混ぜずに新規セッションで再計測する。

実測MCAPでは、画像・CameraInfoは各200 ms、IMUは20 msの中央値。画像の取得時刻（シミュレーション時刻）とbagの受信時刻（実時間）は異なる。左右画像と左右CameraInfoが同一時刻の29組では、最寄りIMUとの時刻差は最大0 ms。旧probeは左右画像3組とCameraInfo各1件以上で終了できたため、出力件数の一致を保証していなかった。今回のprobeは同じタイムスタンプ・解像度・各側のフレーム名と有効な焦点距離を持つ4点セットを3組確認する。再生の再試験では画像左右各4件、CameraInfo左右各3件のうち、時刻が一致する3組を確認した。再生の画像とCameraInfoはReliableで合わせ、購読Discoveryを確認してから再開する。

## Simulation Time基準のDrive計測

bash scripts/verify-virtual-drive.sh は各操作で /clock が2秒進むまで指令を送る。0.10 m/sまたは0.35 rad/sで、実測Simulation Time、Wall Time、RTF、Ground Truth、エンコーダー相当、旋回角、操作中の予期しないゼロ遷移を metrics.log に保存する。走行ゲートの0.35秒期限は実時間の単調時計のまま。これにより描画負荷と安全期限を分けて観測できる。

### 同一指令条件での比較

両環境で完走した2試行ずつを比較した。絶対距離の単位はm、旋回角はrad。

| 指標 | Jazzy / Harmonic 2試行 | Lyrical / Jetty + Zenoh 2試行 |
|---|---:|---:|
| 前進 Ground Truth | 0.1973 / 0.0609 | 0.1976 / 0.1976 |
| 前進 エンコーダー相当 | 0.1950 / 0.0616 | 0.2000 / 0.2000 |
| 後退 Ground Truth | 0.1981 / 0.1967 | 0.1987 / 0.1971 |
| 後退 エンコーダー相当 | 0.1944 / 0.1960 | 0.1936 / 0.1958 |
| 左旋回 | +0.6586 / +0.6606 | +0.6533 / +0.6579 |
| 右旋回 | −0.6619 / −0.6618 | −0.6544 / −0.6532 |
| 全操作の実測Simulation Time | 2.002–2.018 s | 2.000–2.010 s |
| 全操作のWall Time / RTF | 5.01–8.57 s / 0.234–0.403 | 5.94–11.91 s / 0.169–0.337 |

表の4試行は操作中のゼロ遷移0回、停止確認を含めると各6回。別の並行負荷下のLyrical再試行では、前進2回・後退6回の予期しないゼロ遷移を検出した。期限の延長はしていない。開始時の接続・指令処理遅延も実測区間に含まれるため、前進のばらつきを物理エンジン固有差とは判定しない。

## コミットの分割案

1. セットアップ・環境対応。scripts の共通ROS環境、セットアップ、doctor、requirements、Windows入口と既存カメラ側の起動変更を一緒に含める。doctorが参照するミッション・SILのファイルは第2コミットと同時に実行可能になるため、各コミット単体でdoctorを通すには第1・第2を統合する。
2. 仮想センサー・モジュール・Test Lab。ros2_ws のカメラ・ミッション連携、cansat/sil、tools/module_test_lab、外部サンプルと関連試験を含める。
3. 配布。ground_station のシミュレーションAPIとビュー、scripts の記録再生とDrive試験、docs/setup の担当別手順。記録再生の外部probeに依存する変更もここに含める。

mainの取り込みは既存のマージコミットに含まれる。ローカル環境設定、シークレット、ビルド生成物、ログ、MCAP、バックアップをステージング対象から外す。旧機体のArduino原本は再配布権限を確認できるまでローカルの参照用とする。通常の仮想試験とソース提供済みのC++接続例には不要。

## 配布用PR説明文案

CanSat INØのソフト班が実機なしで担当コードを試せる仮想開発環境を追加します。ステレオ・IMU・TF・Clockの配信、Main/Camera/Driveの担当別差し替え、C++と外部ROSノードの接続、地上局バックエンド向けのローカル試験API、制御Topicを含まないセンサー記録再生を含みます。

Jazzy / Harmonicの検証では外部Drive C++から前進・後退・左右旋回し、指令途絶・重複時の停止と新規指令での復帰を確認しました。正式対象はUbuntu 26.04 / Lyrical / Jettyです。Jazzyではセンサーだけを別ドメインに再生し、左右画像の同時刻ペアを外部ノードで確認済みです。地上局は開発用の読取専用画面から確認できます。Lyrical / JettyではループバックZenohを使って仮想センサーと外部接続を確認しました。このWSL環境でのFast DDSの別プロセス疎通は未解決です。
