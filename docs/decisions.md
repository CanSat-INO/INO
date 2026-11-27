# 決定事項

- CanSat INØ。既存Monorepoのcansat、ros2_ws、ground_station、toolsを継続する。
- Main・Camera・Driveの接続と地上局の責務は[構成](architecture.md)、状態とモードは[ミッション](mission.md)を参照。
- MainのNVS復帰は必須。時刻・識別子、座標系、通信の合意は[interfaces](../interfaces/README.md)で管理。
- ROS 2 Lyrical Luth。ステレオVOを先に評価し、RTAB-Mapを最初のSLAM候補にする。Nav2等の既存技術を調査する。
- 既存のREGULUS・Test Lab・Webのプロトコルや設定は各コードの用途に限定し、INO採用仕様は共同レビューする。
