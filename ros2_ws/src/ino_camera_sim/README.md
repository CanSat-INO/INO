# INO カメラシミュレーション

ROS 2・Gazebo・RTAB-Map（Jazzy/Harmonic または Lyrical/Jetty） を使うステレオカメラ試験です。
本番ファームウェアとは独立して動きます。Module Test Labの「Gazebo カメラ試験」からも起動・評価できます。

## 普段の起動（Windows）

1. リポジトリ直下の **camera-settings.bat** を開く。
2. カメラ配置・撮影方式・草地などを設定し、「起動」を押す。
3. GazeboとRVizで画像・地図を確認する。
4. 動かす場合は **camera-teleop.bat** を開く。i=前進、j/l=旋回、k=停止。
5. 設定画面の「停止」を押して終了する。設定画面を閉じる場合も停止処理が走る。

- **start-camera-sim.bat**：現在の設定で連続撮影を直接起動。終了はCtrl+C。
- **compare-camera-designs.bat**：短い条件比較を実行し、画像・軌跡・結果を保存。
- ランチャーは配置場所からパスを解決する。元のcansat_simuは不要。
- 既定のWSLディストリビューションはUbuntu。変更時はcamera-simu.ps1のDistributionを指定する。

## 初回の準備

Ubuntu 24.04 または 26.04 / WSLg / 描画可能なOpenGL環境を使用する。
Ubuntuのターミナルでリポジトリ直下から以下を実行する。
sudoによるシステムパッケージ導入なので、必要な場合だけ実行する。

```sh
bash ros2_ws/src/ino_camera_sim/scripts/setup.sh
```

ROS用PythonはUbuntuのシステムPythonを使う。Test Labのvenvへの導入は不要。

## Ubuntuから起動

```sh
bash ros2_ws/src/ino_camera_sim/scripts/settings.sh
# GUIを出さずにGazeboサーバーを実行する場合（画像描画環境は必要）
bash ros2_ws/src/ino_camera_sim/scripts/start.sh gui:=false rviz:=false
```

上記はcolconビルドなしで動く。ROSパッケージとして使う場合：

```sh
cd ros2_ws
source "/opt/ros/$(lsb_release -rs | sed -e 's/^24\.04$/jazzy/' -e 's/^26\.04$/lyrical/')/setup.bash"
colcon build --packages-select ino_camera_sim
source install/setup.bash
export ROS_DOMAIN_ID=64 GZ_PARTITION=ino_camera_64 GZ_IP=127.0.0.1
ros2 launch ino_camera_sim stereo.launch.py
```

インストール版にはビルド時点の設定がコピーされる。普段はリポジトリ直下のバッチを使う。

## 設定と結果

`config/design.yaml`：カメラ位置・姿勢・左右間隔・画角・解像度・撮影間隔・
JPEG品質・欠落確率・合成地面・機体形状・比較試験の走行条件。

撮影方式はcontinuous（連続）、stop（停止後同時）、sequential（停止後順次）。
順次撮影では左右の実フレームの時刻差を保持する。
初期値とCADは移植元の比較条件であり、INO実機の確定仕様ではない。
CAD外形を視野遮蔽に使用するが、接触形状は簡略化している。

`logs/<実行ごとのフォルダー>/` に設定・生成ワールド・地図DB・状況を保存する。
比較試験はresult.json、CSV、左右画像、軌跡、レポートも保存する。
ログとDBはGit管理から除外する。

既定はROS_DOMAIN_ID=64 / GZ_PARTITION=ino_camera_64。
移植元の既定値42と分離し、監視プロセスは自分が起動した子プロセスだけを停止する。

## ROSインターフェース

- `/raw/{left,right}/{image,camera_info}`：Gazeboからの画像・内部パラメータ
- `/stereo/{left,right}/{image,camera_info}`：平行化した画像・内部パラメータ
- `/capture/rgbd_image`：撮影条件で選択したRTAB-Map入力ペア
- `/capture/status`：撮影タイミング・待ち行列の状況
- `/clock`、`/cmd_vel`、`/odom`、`/cloud_map`、`/tf`：時刻・操作・SLAM出力
- `/ground_truth/odom`：評価専用。SLAMへの位置入力には使用しない

## 検証コマンド

```sh
source "/opt/ros/$(lsb_release -rs | sed -e 's/^24\.04$/jazzy/' -e 's/^26\.04$/lyrical/')/setup.bash"
cd ros2_ws/src/ino_camera_sim/tools
python3 -m unittest test_geometry test_capture_timing -v
# 実際のGazebo画像・撮影ペア・SLAM出力を確認し、自分のセッションを停止
python3 check_pipeline.py --timeout 90
```

## 対象範囲

カメラ描画、平行化、撮影制御、ステレオSLAM、RViz、条件比較を移植した。
自律走行、降下・開傘、ESP32実行は含まない。Module Test Labとは設定・プロセス・結果で接続する。
実機レンズの歪み・露光・履帯走破性の校正は行っていない。
STEP原本・過去ログ・DB・旧baselineは取り込んでいない。

## この移植での確認結果

- colconビルドとインストール側のros2 launch認識が成功。
- カメラ幾何・撮影タイミングの6テストが成功。設定画面の初期化も確認。
- 既定の草地・CAD条件で、左右640x480画像、内部パラメータ、撮影ペア、
  SLAMの有効オドメトリ・点群を実際に受信。
- lab条件の約8cm走行で連続撮影123ペア、順次撮影10ペアを保存。
  順次撮影の走行中撮影は0件、左右時刻差は約0.1秒。
- 終了後に所有セッションの実行プロセスが残っていないことを確認。

短距離の動作確認であり、全設定・実機性能・長距離追跡の保証ではない。
Windowsバッチは構文・パス解決を確認済み。Gazebo/RVizの通常GUIを
人が操作する一連の確認は別途必要。

Test Labでの操作は [カメラ試験ガイド](../../../tools/module_test_lab/README_CAMERA_SIM_JA.md) を参照。
