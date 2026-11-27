# CanSat INØ

CanSat-INO の Monorepo。

```text
INO/
├── cansat/          # 機体側ファームウェア
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

`ros2_ws/src/` にパッケージを追加してから、ROS 2環境で `colcon build` を実行する。
現在は `ino_bringup` のひな形がある。既存の `build/`、`install/`、`log/` はローカル生成物として保持し、Git管理から除外する。

## 機体

機体の構成と入口は [cansat/README.md](cansat/README.md) を参照。


## 開発を始める

ROS 2 の開発環境は Ubuntu 26.04 / WSL2 を基本とする。対象に応じて CMake と C++、PlatformIO Core、ROS 2 Lyrical Luth と colcon、Node.js 22.12 以上を用意する。

```sh
cmake -S cansat/development -B /tmp/ino-dev-build
cmake --build /tmp/ino-dev-build
ctest --test-dir /tmp/ino-dev-build --output-on-failure
pio run -d cansat/main
pio run -d cansat/regulus_rtos
source /opt/ros/lyrical/setup.bash
cd ros2_ws
colcon build --packages-select ino_bringup
source install/setup.bash
ros2 launch ino_bringup development.launch.py
```

[担当と最初の作業](docs/requirements.md) · [全体構成](docs/architecture.md) · [ミッション](docs/mission.md) · [共通仕様](interfaces/README.md) · [開発方針](docs/development_policy.md) · [ロードマップ](docs/development_roadmap.md) · [試験](docs/testing_policy.md) · [決定事項](docs/decisions.md) · [未確定事項](docs/open_questions.md) · [Test Lab](tools/module_test_lab/README_JA.md)

[v1.3レビューと担当別の入口](docs/v1.3_review.md) · [要求・試験IDの追跡](docs/test_traceability.md)
