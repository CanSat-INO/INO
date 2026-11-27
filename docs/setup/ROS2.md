# ROS 2 の入れ方

通常は [初回セットアップ](README.md) の `bash scripts/setup.sh` がROSも導入する。
ここではROS導入の範囲と、手動で確認する方法を説明する。

## 対象

Ubuntu 24.04（Noble）には Jazzy / Harmonic、Ubuntu 26.04（Resolute）には Lyrical / Jetty を導入する。GUI は WSLg または Ubuntu のディスプレイ環境を使う。

## Lyrical へ移行する（WSL）

PowerShell で **別の Ubuntu 26.04 環境** を用意する。24.04 側とクローンを分けると、Jazzy に戻るときは元の環境を開くだけで済む。

~~~powershell
wsl --list --online
wsl --install -d Ubuntu-26.04
wsl -d Ubuntu-26.04
~~~

配布名は一覧の NAME 列に従う。Ubuntu 26.04 の端末で、[クローンと初回セットアップ](README.md#2-ubuntuのホーム配下へcloneubuntu) を行う。未 push の作業を試す場合は、変更を含むソースを新環境に置く。旧環境の .venv と ros2_ws の build / install / log はコピーせず、新環境で作る。

~~~bash
bash scripts/setup.sh --dry-run
bash scripts/setup.sh
bash scripts/doctor.sh --ros-only
bash tools/module_test_lab/launch_ino.sh
~~~

診断が通ったら、Test Lab でステレオ映像・SLAM、短距離自律走行、降下・開傘を順に確認する。Lyrical のシミュレーション実動は未検証。

## ROSだけを導入する

Ubuntu内のリポジトリ直下で：

```bash
bash scripts/install-ros2.sh --dry-run
bash scripts/install-ros2.sh
```

管理者PowerShellではなくUbuntu側で実行する。apt操作時にsudoパスワードを入力する。
スクリプトはUbuntuバージョン・CPUアーキテクチャを確認し、公式ROS apt配布元が
既にある場合はその設定を保持する。ない場合はUniverseを有効化し、
公式ros2-apt-sourceのdebをダウンロード・ハッシュ確認・登録する。
最後に ros-jazzy-ros-base または ros-lyrical-ros-base を導入する。シェル初期化ファイルは変更しない。

### 配布元の固定と検証

この版で確認した公式配布物：

- Release: 1.3.0
- File: ros2-apt-source_1.3.0.noble_all.deb
- SHA256: `f31d84adf5054c7d60ded0e82c0f776a77ea33af53d08f40b9ad7c94cca55296`
- File: ros2-apt-source_1.3.0.resolute_all.deb
- SHA256: `e70bc980395f4a3b366b9c5e7f8f9b4d63a4064fb115f6ff3bc52f7faa02ef69`
- [公式リリース](https://github.com/ros-infrastructure/ros-apt-source/releases/tag/1.3.0)

取得したファイルのハッシュとパッケージ名が一致するまでインストールしない。
curlで取得したスクリプトをそのままrootで実行する方式は使わない。
配布物が変更・削除された場合は値を推測して回避せず、公式リリースを確認する。
PySide6はrequirements-gui.txtで固定し、ROSパッケージは各ディストリビューションのapt更新を使う。
OS・ROS全パッケージのバイナリを固定した環境ではない。

## 導入確認

```bash
source scripts/ros-environment.sh
ros2 --help
ros2 pkg prefix rclpy
```

Gazebo・RTAB-Map・Zenoh・SILまで揃えるには通常セットアップを実行する。

```bash
bash scripts/setup.sh
bash scripts/doctor.sh
```

Gazeboパッケージ導入後の確認：

```bash
source scripts/ros-environment.sh
gz sim --versions
ros2 pkg prefix ros_gz_bridge
ros2 pkg prefix rtabmap_slam
ros2 pkg prefix rmw_zenoh_cpp
```

ROSのPythonライブラリはUbuntuのシステムPythonで動かす。
Test Labの.venvへrclpy/cv_bridgeをpipで入れない。起動スクリプトが環境を分離する。
通常のバッチ起動ではsource操作を毎回行う必要はない。

## 任意のパッケージビルド

```bash
source scripts/ros-environment.sh
cd ros2_ws
colcon build --packages-select ino_camera_sim ino_mission_sim
source install/setup.bash
```

通常利用はソース用バッチから起動できるため、このビルドは必須ではない。

## この自動化で行わないこと

WindowsへのWSL追加、Windows/GPUドライバー更新、WSL再起動、時計・サービス設定、
他のROSの削除、OS全体の自動アップグレードは行わない。
ディストリビューションの基礎更新やaptの問題は公式ガイドに従って確認する。
特に依存が解決しない場合はUbuntuの配布元・updates/backportsの有効性を確認し、
このスクリプトで既存のaptファイルを強制上書きしない。

## 公式資料

- [ROS 2 Lyrical / Ubuntu deb](https://docs.ros.org/en/lyrical/Get-Started/Installation/Ubuntu-Install-Debs.html)
- [Gazebo と ROS 2 の対応表](https://gazebosim.org/docs/jetty/ros_installation/)

- [ROS 2 Jazzy / Ubuntu deb](https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)
- [上記公式文書のソース](https://github.com/ros2/ros2_documentation/blob/jazzy/source/Installation/Ubuntu-Install-Debs.rst)
- [公式apt-source](https://github.com/ros-infrastructure/ros-apt-source)
- [Microsoft WSLg](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps)
