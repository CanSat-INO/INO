# 全体構成

| 経路 | 責務 |
|---|---|
| Main ↔ Camera / Drive（CAN） | 指令、状態、Heartbeat、受付と結果。MainがCapture IDを発行する |
| Main ↔ 地上局（TWELITE） | テレメトリの受信と、承認された自動生成経路の送信 |
| Camera → 地上局（Wi-Fi） | 左右静止画と撮影メタデータ。画像はCANを経由しない |
| 地上局 → ROS 2 | 受信・保存、時刻対応、ステレオ処理、自己位置、地図、地形評価と経路計画 |
| ROS 2 → Web UI | rosbridgeを基本候補とした監視・可視化。保存と自律処理は独立 |

Minimumの判断・制御は機体側で行う。地上局は会場LANで動かす。RViz2は技術検証、Webは管制・成果表示。既存Webの受信・可視化を利用しつつ、Overview、Navigation、Terrain、Stereo Camera、Telemetry、Attitude、System Health、Mission Timeline、Data Explorerの表示要件を検討する。

記録はミッション単位。元画像・校正・テレメトリ・ROS 2記録・点群・軌跡・経路・指令結果・異常履歴に設定版とコード版を添える。保存形式と容量は担当間で決める。再生は送信経路を持たない環境で行う。

Cameraは論理1モジュール・基板1枚の予定。左右OV2640×2とESP32-S3×1による順次撮影を第一候補とする。MCU数、DVP/SCCB切替、FIFO方式、ピン・電源と露光時刻差はハード班と検証する。
