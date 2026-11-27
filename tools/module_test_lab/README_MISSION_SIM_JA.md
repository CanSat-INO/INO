# Test Lab 自律走行・降下・SIL

INO直下の `start-module-test-lab.bat` を開き、機能一覧から
**自律走行・降下・SIL** を選ぶ。最初に「初期設定を読込」を押す。

## 試験モード

- **地上自律走行**: 停止して左右撮影→地形認識→経路計画→短距離走行を繰り返す。
  Gazeboの接触駆動履帯、仮想IMU/エンコーダ、RTAB-Mapを使う。
  制御はROSノード。実機ファームウェアが自律走行しているという意味ではない。
- **降下・開傘**: 質点モデルで自由落下、風、段階的開傘、着地までを試す。
  初期条件は30m・東向き6m/sの比較用設定で、INO実機仕様ではない。
  布の変形、衝撃破損、実機サーボ機構の再現ではない。
- **降下＋ユーザーC++ SIL**: `cansat/` の制御判断を呼ぶPC用.cppアダプターを明示して
  ビルド・実行する。着地終了を外すと着地後もコントローラーの判断を継続する。
  本番コードは今後追加するため、現時点で本番ロジックの試験済みを意味しない。

高度、東向き風、開傘所要時間、地上ゴール・速度を画面で変更できる。
その他のカメラ・障害物・風向・突風・開傘条件はJSON/YAML読込で指定する。
元の既定設定を上書きせず、実行ごとに設定を保存する。
地上走行は `config/ground_navigation.yaml`、降下は `config/firmware/descent.yaml` が既定。
試験上限は実時間の分数。PC負荷でシミュレーション時刻の進み方は変わる。

「停止」またはTest Lab終了確認の「はい」で、起動した試験だけを停止する。
カメラ試験とこの試験を両方起動した場合は、両方の停止を待って終了する。
Gazebo/RViz画面なしでもGPUの画像描画環境は必要。

## 結果

`ros2_ws/src/ino_mission_sim/logs/<実行ID>/` に設定、起動ログ、result.json、
軌跡・センサー・制御ログを保存する。地上走行には写真・地図・経路レポート、
降下にはdescent.csv、着地速度、開傘率、流下距離を含む。
結果一覧からフォルダーを開くか比較CSVを保存できる。

降下の「着地」はゴール到達を意味しない。
参照コード、停止するだけの接続例、ユーザーのSILアダプターは結果で区別する。
SILでは.cppと参照ヘッダー、ビルド後バイナリのSHA256を保存する。

## 今後の本番コード

`cansat/sil/README.md` を参照。
制御判断をArduino/ESP-IDFやセンサーの実入出力から分離し、
PC向けアダプターが同じ判断処理を呼ぶ方式。
Arduino .ino / ESP32 ELF / RTOS / I2C / GPIOをそのままエミュレートしない。
GUIは1つのアダプター.cppを指定する。複数.cppや追加includeは
`tools/run_mission.py --controller-source <file>` の繰り返し・`--include` で指定できる。
付属connection_example.cppは常に停止する入出力確認用であり、本番コードではない。

## 初回準備

Ubuntu側で、リポジトリ直下から必要な場合のみ実行する。

```sh
bash scripts/setup.sh
```

カメラ側と同じROS 2・Gazebo・RTAB-Map（Jazzy/Harmonic または Lyrical/Jetty）に加えて
rmw_zenoh_cppとg++を使用する。Test LabのvenvにROSをpip導入する必要はない。

## 単独起動

```sh
bash ros2_ws/src/ino_mission_sim/scripts/start-ground.sh
bash ros2_ws/src/ino_mission_sim/scripts/start-mission.sh
```

いずれも `--config`、`--out`、`--headless`、`--wall-timeout` を指定できる。
ユーザーSILのビルドにはソースチェックアウトを使う。
legacy_2025は比較用の保存コードで、`--reference-profile` 明示時だけ使用する。
元のcansat_simuフォルダーは参照しない。

## 今回の確認範囲

- Test Lab経由の30m降下・東向き6m/s条件で、開傘開始→開傘完了→着地を確認。
  これは仮定した質点モデルの結果であり、実機の降下性能を保証しない。
- ユーザーC++アダプターの接続経路は、付属の停止専用接続例でビルドとセンサー受信を確認。
  本番コードは未作成のため未検証。別の単体試験では入力に応じた左右指令とヘッダー追跡も確認。
- 自律走行は障害物を外した短いゴール（0.35m先、許容0.1m）で到達を確認。
  停止撮影5回、走行中の撮影0件、SLAM地図・経路・接触駆動を確認。
  標準3.6mコース全体、坂・段差・カメラによるゴール確認はこの移植先では未実行。
- GUI経路はoffscreen描画で確認。通常ウィンドウの手動操作は別途必要。

仮想GNSSの原点・目標座標はシミュレーターの比較条件。
本番コード接続時は、座標系・単位・取得時刻・有効性・実機のモーター方向を
アダプター側で明示して合わせる。

初回導入の最新手順は [クローンから起動](../../docs/setup/README.md)、
[ROS導入](../../docs/setup/ROS2.md)、[診断](../../docs/setup/TROUBLESHOOTING.md) を参照。
