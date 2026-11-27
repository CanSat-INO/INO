# ROS 2 Lyrical Luth

Ubuntu 26.04を基本に、WindowsではWSL2可。パッケージと担当間で合意した依存だけを追加する。初回は実機と切り離して、既知の左右画像・校正を使い、OpenCV/camera_calibration、image_proc/stereo_image_procの入力と結果を確認する。TF・VOはtf2とRTAB-Map、センサー融合はrobot_localization、記録と可視化はrosbag2/RViz2を候補とする。

| 領域 | 置き場所 |
|---|---|
| 受信・ROSメッセージ変換、左右同期・CameraInfo | src配下の担当パッケージ |
| 視差・点群・VO・SLAM・TF、地図保存 | 既存パッケージをつなぐlaunch/config |
| 地形評価・経路計画 | 地図の形式を決めた段階で担当パッケージ |
| 記録・再生 | 入出力決定後にrosbag2設定。ライブ送信と隔離 |

Stop and Goの不等間隔入力、画質、重複率、VO失敗を評価する。Topic・QoS・採用依存はTBD。パッケージ追加後はルートREADMEのビルド手順を使う。

LyricalはUbuntu 26.04の別環境で検証する。既存Jazzyを参照環境として使えるようにして、Lyricalの試験記録にOS・ROS_DISTRO・RMW・依存の版を記載する。stereo_image_proc、RTAB-Map、Nav2、robot_localization、rosbridge_suiteごとにAPT候補・インストール・起動を別々に記録する。現状はLyricalで未検証。
