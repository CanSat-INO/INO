# 今後の本番コードをGazeboへ接続するためのSILアダプター

本番の制御判断ロジックはcansat/以下に置き、GPIO、I2C、カメラ取得、RTOSの処理と分離する。
PC向けの.cppアダプターが共通ロジックを呼び、仮想センサーとモーター指令を変換する。
connection_example.cppは入出力確認専用で、常に停止する。本番実装ではない。

入出力契約はros2_ws/src/ino_mission_sim/firmware/sil/sim_port.hpp。
Sensorsは時刻・高度・温度・気圧・GNSS・方位・加速度・RGB565画像パス・有効性と取得時刻。
Actuatorsは左右の正規化指令、分離指令、フェーズ。
wait()はシミュレーション時刻でセンサー更新を待つ。実時間delayやArduino SDKは使用しない。

```sh
python3 cansat/sil/build_controller.py cansat/sil/connection_example.cpp \
  --contract ros2_ws/src/ino_mission_sim/firmware/sil --output /tmp/ino-sil-example/controller
```

Test Labでは接続する.cppを明示してビルド・実行する。
元コードを自動書換えせず、ソースとバイナリのSHA256・コンパイラー・コマンドを保存する。
実機用.inoやESP32 ELFをそのままPCで実行するものではない。
センサー入出力の物理通信、RTOSタイミング、割り込み、実機性能の検証は別途必要。
