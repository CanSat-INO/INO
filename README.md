# CanSat INØ

機体コード、地上局、Test Lab、ROS 2/GazeboのシミュレーションをまとめたMonorepo。

## 初めて使う人へ

**[クローンから起動までのREADME](docs/setup/README.md)** を参照。
正式な開発環境は Ubuntu 26.04 / WSL2（Lyrical / Jetty）です。シミュレーションは Ubuntu 24.04（Jazzy / Harmonic）でもセットアップできます。Windows では WSL2 + WSLg を使用します。Ubuntu 26.04上でcolconのビルドを検証し、Jettyでの通し試験は環境診断通過後に行います。正式配布の判定と担当別の開始手順は [配布チェックリスト](docs/setup/RELEASE_CHECKLIST.md) を参照してください。

Ubuntu内でcloneし、このフォルダーで初回だけ実行する。

```bash
bash scripts/setup.sh
```

ROSの配布元・Gazebo/SLAM依存・固定版GUI用.venvを準備する。
Windowsでは **setup-simulation.bat** でも同じ処理を実行できる。
WSL自体の導入は先に必要。詳しくは[ROS 2の導入README](docs/setup/ROS2.md)。

普段は **start-module-test-lab.bat** を開く。
環境確認は **check-simulation.bat**、起動の問題は[トラブルシューティング](docs/setup/TROUBLESHOOTING.md)。

## できること

| 入口・画面 | 内容 |
|---|---|
| Test Labの既存メニュー | 着地・C++判断・仮想CAN・CSV解析・実験記録共有 |
| Gazebo カメラ試験 | ステレオ配置・撮影方式・RTAB-Map・条件比較 |
| 自律走行・降下・SIL | 停止撮影の自律走行、風と段階的開傘、PC用C++接続 |
| camera-settings.bat | カメラ用の独立した設定・起動画面 |
| camera-teleop.bat | カメラ試験の手動走行（i:前進、j/l:旋回、k:停止） |

機体側の開発入口は [cansat/README.md](cansat/README.md) を参照。SIL接続例はPC上で制御コードの入出力を確認するためのものです。

## 構成

```text
INO/
├── cansat/          # 機体側開発とPC用SILアダプター
├── ground_station/  # Web地上局・受信機
├── ros2_ws/src/
│   ├── ino_bringup/
│   ├── ino_camera_sim/
│   └── ino_mission_sim/
├── tools/module_test_lab/
├── scripts/         # 初回セットアップ・診断
└── docs/setup/      # clone・ROS導入・問題解決
```

.venv、node_modules、ビルド生成物、ログは各自で生成しGitに含めない。
通常起動にcolcon buildは不要。開発時のビルド手順は[ROS README](docs/setup/ROS2.md)を参照。

## 地上局

地上局はNode.js/npmを使う別の起動入口。ROS用setupでは導入しない。

```bash
cd ground_station
npm ci
npm run dev
```

[地上局README](ground_station/README.md)を参照。WSLのcheckoutはWSL側のnpmで扱う。

## 詳細

- [カメラ試験](tools/module_test_lab/README_CAMERA_SIM_JA.md)
- [自律走行・降下・SIL](tools/module_test_lab/README_MISSION_SIM_JA.md)
- [今後の本番コード接続](cansat/sil/README.md)

## 開発・テスト

```bash
bash scripts/setup.sh --dev
.venv/bin/python -m pytest
```

ROS依存のシミュレーション単体試験は、各パッケージREADMEのコマンドで実行する。
通常のpytestはROSをGUIのvenvへ混ぜず、Test Labとセットアップを対象にする。
完全に新しいOS/GPU環境での導入は別途確認が必要。

## 機体・ROS 2の開発を始める


ROS 2 の開発環境は Ubuntu 26.04 / WSL2 を基本とする。対象に応じて CMake と C++、PlatformIO Core、ROS 2 Lyrical Luth と colcon、Node.js 22.12 以上を用意する。

```sh
cmake -S cansat/development -B /tmp/ino-dev-build
cmake --build /tmp/ino-dev-build
ctest --test-dir /tmp/ino-dev-build --output-on-failure
pio run -d cansat/main
pio run -d cansat/camera
pio run -d cansat/drive
pio run -d cansat/regulus_rtos
source /opt/ros/lyrical/setup.bash
cd ros2_ws
colcon build --packages-select ino_bringup
source install/setup.bash
ros2 launch ino_bringup development.launch.py
```

[担当と最初の作業](docs/requirements.md) · [全体構成](docs/architecture.md) · [ミッション](docs/mission.md) · [共通仕様](interfaces/README.md) · [開発方針](docs/development_policy.md) · [ロードマップ](docs/development_roadmap.md) · [試験](docs/testing_policy.md) · [決定事項](docs/decisions.md) · [未確定事項](docs/open_questions.md) · [Test Lab](tools/module_test_lab/README_JA.md)

[v1.3レビューと担当別の入口](docs/v1.3_review.md) · [要求・試験IDの追跡](docs/test_traceability.md)
