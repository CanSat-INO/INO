# INO Mission Simulation

自律走行、降下・開傘、ネイティブC++のSIL接続を扱う独立パッケージ。
カメラ幾何・CAD・平行化処理はino_camera_simから共有する。

- 地上走行: 停止撮影、ステレオ地形認識、経路再計画、接触駆動の履帯モデル。
- 降下: 質点モデルの風・自由落下・段階的開傘。布、実機衝撃や破損は未再現。
- SIL: センサー値とRGB565画像ファイルをPC用C++へ渡す。ESP32バイナリの実行ではない。
- legacy_2025は比較専用の参照コード。INO本番コードとして扱わない。

ROS 2・Gazebo・RTAB-Map（Jazzy/Harmonic または Lyrical/Jetty） / rmw_zenoh_cpp / g++ が必要。
通信は地上走行domain65・router17645、降下/SIL domain66・router17643。
logsとビルド生成物はGit管理しない。元のcansat_simuは不要。
