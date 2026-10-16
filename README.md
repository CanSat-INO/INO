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

`ros2_ws/src/` にパッケージを追加してから、ROS 2環境で `colcon build` を実行する。
現在 `src/` は空。既存の `build/`、`install/`、`log/` はローカル生成物として保持し、Git管理から除外する。

## 機体

`cansat/` は配置先のみ用意している。機体側ファームウェアは未取り込み。
