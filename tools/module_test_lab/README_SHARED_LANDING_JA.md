# Module Test Lab v4 第3段階 — Arduino / PC 共通着地判定ロジック

## この段階でできること

同じ **`CanSatLandingLogic.h`** を、Arduino側のスケッチからもPC側の検証からも利用するための土台を追加しました。既存の「C++着地判定」タブを使うため、GUIや実験記録の変更はありません。

今回のロジックは**共有方法を示すサンプル**であり、チームが実際に開発している着地判定コードではありません。実機の `.ino` はまだリポジトリ上で見つかっていません。`receiver.ino` は地上局用で、機体の着地判定コードではありません。

## 主要ファイル

- `cpp_landing/shared_landing/CanSatLandingLogic.h`：ArduinoとPC双方で使うC++クラス（センサー読取なし）
- `cpp_landing/shared_landing/host_adapter.cpp`：既存ホストAPIの `landing_reset` / `landing_step` に接続
- `tests/test_shared_landing.py`：既存試験環境に追加する6つのオフラインテスト
- `examples/run_shared_landing_demo.py`：CLIで動かすデモ

## PCで試す

1. 既存の `examples/make_demo_csv.py` でサンプルCSVを生成します。
2. GUIで **「C++着地判定」** タブを開きます。
3. **センサーCSV** に `~/cansat_module_lab_data/demo_virtual_landing.csv` を選びます。
4. **C++判定コード** に `~/INO-module-lab/tools/module_test_lab/cpp_landing/shared_landing/host_adapter.cpp` を選びます。
5. 正解時刻は空欄、許容遅延は5000msにして「C++コードを実行・評価」を押します。
6. 成功したら、必要に応じてローカル実験記録に保存できます。実機のデータとは区別してください。

想定結果：接地10.0秒／判定13.0秒／遅延3.0秒／成功。

## Arduino担当者が接続するには

`CanSatLandingLogic.h` を、Arduino IDEのスケッチと同じフォルダに**コピー**し、以下の形で判定処理を呼び出します。ここではセンサー読取を実装していないため、実際のIMU・気圧計の値を取得するコードはチームの担当者が追加します。

```cpp
#include "CanSatLandingLogic.h"

CanSatLandingLogic landing;

void setup() {
    landing.reset();
    // ここでセンサー初期化などを行う（担当者のコード）
}

void loop() {
    // 次の2つの値はセンサー取得処理から与える（単位に注意）
    double imu_z_mps2 = 9.81;     // ダミー値：実際にはIMU測定値
    double pressure_pa = 101325.0; // ダミー値：実際には気圧測定値
    bool landed = landing.update((double)millis(), imu_z_mps2, pressure_pa);
    if (landed) {
        // 着地後に必要な処理（この例には含まれない）
    }
}
```

**共有の重要点**：Arduino側とPC側が同じヘッダーを使用していることが必要です。コピー後に一方だけを書き換えると同一ロジックの検証ではなくなります。GitのコミットIDやファイルのSHA256を記録して、同一版であることを確認してください。

**仕様の注意**：このサンプルはZ方向加速度の絶対値が20m/s²以上になった時刻から3秒後に着地を検知します。気圧は受け取りますが判定には使用しません。傾斜・回転・姿勢の変化や衝撃の誤判定を十分に考慮した実用アルゴリズムではありません。`time_ms` は経過時刻で、単調増加が前提です。ESP32の`millis()`の周回やセンサーエラーの実際の扱いも担当者が設計・検証してください。

## 現段階でできないこと

- 現実の着地判定 `.ino` を自動で変換すること
- ESP32専用ライブラリやI2C/BNO055/BME280のホストエミュレーション
- 実機に書き込んで安全性・精度・安定動作まで保証すること

## 安全性・独立性

PC試験はC++を実際にコンパイルして起動します。**信頼できるローカルのコードのみを選択**してください。既存のホスト試験はサンドボックスではありません。

既存のGUI/CSV/実験データ、GitHub上の記録、ROS 2統合シミュレーターはこの段階のインストールで変更しません。
