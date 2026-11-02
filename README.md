# INO

CanSat-INO の Monorepo。

```text
INO/
├── cansat/          # 機体側ファームウェア（今後追加）
├── ground_station/  # Web地上局・共有通信定義・ESP32受信機
├── ros2_ws/         # ROS 2 / colcon ワークスペース
└── docs/            # ドキュメント用
```

## 地上局

```sh
cd ground_station
npm ci
npm run dev
```

画面: http://localhost:5173 / バックエンド: http://localhost:8080

詳細は [ground_station/README.md](ground_station/README.md) を参照。

## ROS 2

ROS 2環境で `ros2_ws/` に移動し、`colcon build` を実行する。
`src/ino_camera_sim/` にカメラシミュレーションを配置。既存の `build/`、`install/`、`log/` はローカル生成物として保持し、Git管理から除外する。

## 機体

`cansat/` は配置先のみ用意している。機体側ファームウェアは未取り込み。

## カメラシミュレーション

Windowsでは `camera-settings.bat` を開き、設定画面から起動します。
手動操作は `camera-teleop.bat`（i:前進、j/l:旋回、k:停止）。
詳しくは [ino_camera_sim](ros2_ws/src/ino_camera_sim/README.md) を参照。
単独起動とModule Test Labからの起動に対応し、本番ファームウェアは実行しません。

## Module Test Labからカメラ試験

`start-module-test-lab.bat` を開き、ホームから「Gazebo カメラ試験」を選択します。
カメラ設定・起動停止・自動評価・結果比較を操作できます。
[導入と操作](tools/module_test_lab/README_CAMERA_SIM_JA.md) を参照。
