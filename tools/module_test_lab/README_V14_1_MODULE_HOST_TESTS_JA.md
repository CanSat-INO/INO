# v14.1 モジュール別C++判断ロジックの取り込み

本機能は **着地判定 / Drive / CAM / Main** の判断関数だけを、PCのg++で検証します。
`.ino`やESP32-S3のボード全体をビルド・動作確認する機能ではありません。
実機センサー、GPIO、PWM、CAN/無線、モーター、パラシュート機構、カメラの画像処理は評価対象外です。

## 最初のテスト

1. `cansat-lab` を実行する。
2. ホーム画面の「着地・Drive・CAM・Main ロジック検証」を開く。
3. ドロップダウンで「着地判定」を選び、サンプルのままにする。
4. 信頼できるC++のみ実行することを理解したらチェックを付ける。
5. 「モジュール試験を実行」→ **8/8 PASS** となることを確認。
6. Drive / CAM / Main も順番に選び、それぞれ **8/8 PASS** を確認。
7. 必要なら「結果をCSV/JSON保存」。実験台帳へ勝手には保存しません。

## 実コードを取り込む方法

1. Arduino IDE の `.ino` や `.cpp` から、**純粋な判断計算**だけをArduino非依存のヘッダーへ抽出する（担当プログラマーと相談）。実際の判定条件を変えない。
2. `v14_1_examples/landing_adapter.cpp` などを参考に、ご自身の `.cpp` アダプターを作る。信頼できるものだけを選ぶ。
3. ホスト用アダプターから **実機側と同じ判断関数**を呼ぶ。仮のサンプル関数を使ったままでは本番検証にならない。
4. アダプターと同じ場所に、共通ヘッダーを置く。アダプターには `#include "v14_1_contract.hpp"` を使用できる。
5. 期待値を担当者と確認し、モジュールごとの試験CSVを準備する。
6. GUIのC++アダプターと試験ケースCSVに自分のパスを指定して実行する。
7. `FAIL` が出たらそのケースの入力と期待値を見直す。合格したらCSV/JSONを保存し、コードとCSVのSHA256を共有する。

## ホストC++の関数契約（固定）

- `extern "C" int cansat_landing(double accel_mps2, double gyro_dps, int stable_ms);`
- `extern "C" int cansat_drive(int landed, int command, int obstacle, int emergency_stop);`
- `extern "C" int cansat_cam(int visible, double red_ratio, double x_offset);`
- `extern "C" int cansat_main(int landed, int gnss_fix, int target_visible, int fault);`

戻り値（どのように対応付けるかは本番コードの担当者と決定する）:

| モジュール | 戻り値の例 |
|---|---|
| 着地 | `0`: 未着地、`1`: 着地 |
| Drive | `0`: 停止、`1`: 前進、`2`: 左旋回、`3`: 右旋回 |
| CAM | `0`: 探索、`1`: 左、`2`: 右、`3`: 接近、`4`: 到達 |
| Main | `0`: 着地待ち、`1`: GNSS待ち、`2`: GPS誘導、`3`: CAM誘導、`4`: 安全停止 |

上表は **検証ソフト内の仮の共通契約** です。本番のCANコマンドや状態コードではありません。必要ならチーム仕様に合わせて正式契約として変更してください。

## CSV列名

- 着地: `case_id,accel_mps2,gyro_dps,stable_ms,expected`
- Drive: `case_id,landed,command,obstacle,emergency_stop,expected`
- CAM: `case_id,visible,red_ratio,x_offset,expected`
- Main: `case_id,landed,gnss_fix,target_visible,fault,expected`

`.csv`はUTF-8（BOM可）。重複IDは禁止。最大500件。ヘッダー名と順序は固定。
数値は定義範囲内（GUI説明・`v14_1_logic_runner.py`で確認）。

## 重要な制約

- 任意C++コードのコンパイルと実行は **サンドボックス化されません**。信頼できない第三者のコードは選ばないでください。
- 実機の着地判定や車輪の動作が正しいこと、実機の安全性は証明できません。
- 例の数値（加速度15m/s²など）はデモ用の仮の閾値であり、設計基準ではありません。
- カメラは「すでに検出した結果」だけを入力します。画像そのものの処理は含まれません。
- `v14`従来のC++検証ページと実験台帳はそのまま残ります。
- Fcitx5/Mozcや `cansat-lab` の起動方式は更新しません。

## ターミナルからの動作テスト

```bash
cd ~/INO-module-lab/tools/module_test_lab
python3 -m unittest discover -s tests -p 'test_v14_1_logic_runner.py' -v
```
