# 起動できないとき

まずcheck-simulation.batを開く。Ubuntuからは `bash scripts/doctor.sh`。
報告時には実行したコマンド、診断結果、Ubuntu/WSL名、試験フォルダーのlaunch.logまたはcontroller.logを添える。

| 症状 | 確認・対処 |
|---|---|
| バッチでWSLのディストリビューションが見つからない | `wsl --list --verbose`。WSL内へcloneし、`explorer.exe .`で開いたフォルダーのバッチを使う。Windowsドライブに置いた場合はcamera-simu.ps1の`-Distribution`に実際の名前を指定する。 |
| 必要なファイルがない | カメラ・ミッション機能を含むブランチを取得したか確認する。mainへ未マージならfeature/camera_simuが必要。 |
| Ubuntuバージョンで停止 | `/etc/os-release`を確認。Jazzy には Ubuntu 24.04、Lyrical には Ubuntu 26.04 を用意する。他バージョンへ強制インストールしない。 |
| ROSパッケージが見つからない | 通常setupを実行。ROS配布元の導入説明はROS2.md。社内プロキシ、GitHub、packages.ros.orgへの接続も確認。 |
| ハッシュ不一致 | 導入を停止したまま公式リリースを確認。チェックを無効化しない。 |
| .venvがない／PySide6がない | setup-simulation.batを実行。.venvは各自で作るためGitに含まれない。 |
| Qt xcb pluginが読み込めない | doctorのQt X11 librariesを確認。通常setupでlibxcb-cursor0等を導入する。 |
| 画面が出ない／cannot open display | WSL2・WSLg・DISPLAY/WAYLAND_DISPLAY・GPUドライバーを確認。WindowsネイティブのPythonから起動していないか確認する。 |
| OpenGLがllvmpipe／極端に遅い | GPUドライバーとWSLgを確認。描画負荷を下げ、試験の実時間上限を増やす。ソフトウェア描画は遅くなる。 |
| 日本語が四角になる | 通常setupのfonts-noto-cjkを導入。 |
| 日本語入力ができない | `bash scripts/setup.sh --with-ime`後、Fcitx5設定でMozcを追加。WindowsのIME切替とWSL側の入力設定は別。既存設定は自動上書きしない。 |
| rclpy/cv_bridgeのimportに失敗 | ROSはシステムPython、GUIは.venv。ROSをGUIのvenvへpip導入しない。新しいUbuntuターミナルから再確認する。 |
| 既にシミュレーションが動いている | 先のTest Lab／設定画面の停止ボタンで終了する。全ユーザーのプロセスをまとめてkillしない。 |
| 自動試験が未完了 | シミュレーション時刻と実時間は違う。ログ・撮影・SLAMの状況を確認し、上限時間を調整する。未完了を成功と扱わない。 |
| SILの.inoがビルドできない | SILはPC用.cppアダプター。Arduino SDK/ESP32 ELFのエミュレーターではない。cansat/sil/README.mdを参照。 |

## 既存環境の扱い

setupは.venvや実験データを自動削除しない。不完全な.venvがある場合は、
必要なものを退避したうえで自分で別名へ移してから再実行する。
外部へのシンボリックリンクがある.venvは変更しない。
ログとデータを残したまま確認する。mainへのpushやGitHub共有は診断では実行しない。

## クリーン環境での確認範囲

別フォルダーの作業ツリーコピーと新規.venvでの導入確認は、
そのPCに既存のROS・システム依存がある場合、それらの導入試験にはならない。
新規Windows/WSLへの完全導入、GPU・日本語入力の実操作は別環境で確認する。
