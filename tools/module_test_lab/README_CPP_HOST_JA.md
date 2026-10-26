# CanSat Module Test Lab v4 第2段階 — C++着地判定のホスト試験

## できること

- Ubuntuの `g++` で、**明示的に選択したローカルのC++着地判定関数**をコンパイルし、PC上で実行します。
- CSVの `time_ms`（または `time_s`）、`imu_z_mps2`、任意の `pressure_pa` を時系列で渡します。
- `landing_detected` 列が入力CSVに存在しても**その値は無視**し、C++コードが計算した結果に差し替えます。
- `truth_contact` 列、またはGUIで入力した接地時刻と比較して、成功・失敗・未判定を表示します。
- 生成したCSVと元CSVをローカル実験記録に添付し、既存の結果ダッシュボードから確認できます。
- コードの名前とSHA256を記録し、どのC++版で試験したか追跡できます。GitHubへの送信は今までどおり**明示的な手動操作のみ**です。

**注意**: この機能は `.ino` の直接実行ではありません。ESP32-S3の `digitalRead`, `Wire`, I2C, ESP32固有APIなどはPCでは動きません。ハードウェア依存部を切り離したC++判定処理のみ対象です。また、サンプルコードは簡易例であり、実際の着地判定アルゴリズムではありません。

## 準備

Ubuntuで `g++` がない場合:

```bash
sudo apt update
sudo apt install -y g++
```

既存の Module Test Lab v4 が `main` に反映済みであることを確認し、別の開発ブランチ `feature/cpp-landing-host-test` に切り替えてから同梱の `install_cpp_stage.py` を実行します。

## 操作方法

1. 「C++着地判定」タブを開き、「センサーCSV」を参照で選択します。
2. 「C++判定コード」は最初からサンプル `example_detector.cpp` が選択されています。
3. 正解時刻がCSVの `truth_contact` にない場合は、接地時刻をmsで入力します。
4. 「C++コードを実行・評価」を押します。
5. 結果を確認して「結果を実験記録へ保存」を押すと、結果ダッシュボードに表示できます。

サンプルCSVを生成するコマンド:

```bash
~/cansat_gui_venv/bin/python ~/INO-module-lab/tools/module_test_lab/examples/make_demo_csv.py
```

サンプル実行コマンド:

```bash
~/cansat_gui_venv/bin/python ~/INO-module-lab/tools/module_test_lab/examples/run_cpp_landing_demo.py
```

サンプルアルゴリズムは、加速度が20 m/s²以上に達した時刻を衝撃と判断し、そこから3秒経過すると着地検知を出します。正常シナリオの仮想CSVではおおむね接地10秒、検知13秒を想定します。

## 担当者のC++ロジックを接続する方法

`cpp_landing/landing_api.h` を見て、次の2つの関数を実装した `.cpp` ファイルを用意します:

```cpp
extern "C" void landing_reset();
extern "C" int landing_step(double time_ms, double imu_z_mps2, double pressure_pa);
```

- `landing_reset()` は試験開始時に一度だけ呼ばれます。
- `landing_step()` はCSVの各行について1回呼ばれます。着地未検知なら0、検知なら1を返します。
- 気圧が空欄の場合は `pressure_pa = -1.0` を渡します。
- 自動変換やArduino固有ライブラリの代替はしません。センサー読み取りコードと判定コードを分離してから接続してください。
- 計算ロジックを実装する場合は、複数回呼び出されたときに内部状態を正しく保持するようにしてください。

## 安全上の注意

- **C++はローカルPCで実際に実行されます。** 知らない人が提供した `.cpp` は選ばず、チームで確認したコードのみ実行してください。これは隔離されたサンドボックスではありません。
- GitHubから取得した実験の添付ファイルやCSV内の任意のコードを自動実行しません。
- 実験記録に元CSVが添付されます。GitHub共有前に機密情報・個人情報が含まれないか確認してください。
- 検証結果はホストでの単体試験であり、ESP32-S3の実機動作を保証しません。
- ROS 2、Gazebo、既存の地上局には変更を加えません。

## 現時点で対応していないこと

- `.ino` の直接ビルド・実行
- ESP32周辺機器ドライバのエミュレーション
- 複数センサーの完全なハードウェア再現
- GNSS/走行制御モジュールの自動検証
