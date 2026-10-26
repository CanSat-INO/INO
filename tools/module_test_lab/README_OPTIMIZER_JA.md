# Module Test Lab v7：着地検知パラメータ探索

## 目的
既存の v1〜v6 を変更せず、PC 上で動かす **パラメータ対応 C++** を最大16組の設定で比較します。
- 加速度判定閾値 (m/s²)：1〜100
- 静止判定時間 (ms)：0〜5000
- v5の8つの合成条件を各組に適用、設定に対する成功/失敗/未判定/入力エラーを表示
- 成功数 → 着地前誤検知の少なさ → 成功時の平均検知遅延の順で候補を並べる
- 各行を選択して、元のセンサーデータ・判定時刻・原因候補を確認する
- CSV出力、台帳への比較レポート保存、ダッシュボードでレポートとして確認

**注意：探索は試した格子内に限ります。サンプルの合成条件が実機環境を再現できるという保証はありません。**

## 起動

```bash
cd ~/INO-module-lab
QT_QPA_PLATFORM=xcb ~/cansat_gui_venv/bin/python -u -X faulthandler tools/module_test_lab/app.py
```

新タブ「着地パラメータ探索」を選択し、初期設定の `example_detector_tunable.cpp` を選びます。

最初の設定は閾値 `12,14,18`、静止時間 `0,300,700` で計9組です。

## 任意の C++ ファイルを試す条件
このv7の探索機能では、従来の `landing_reset()` と `landing_step(...)` に加え、次の関数が必要です。

```cpp
extern "C" void landing_configure(double impact_threshold_mps2, double stable_hold_ms);
```

- この関数内でアルゴリズムのパラメータを更新してください。
- v7テストランナーは先に `landing_configure()` を呼び、次に `landing_reset()`、最後にセンサーデータの `landing_step()` を呼びます。
- **既存の通常のC++着地判定機能（v4〜v6）はこの新APIを要求しません。**
- `.ino` をそのまま動かせる仕組みではありません。ESP32依存処理は分離してください。
- 信頼できるローカル `.cpp` だけを指定してください。実行時のサンドボックス分離はありません。

## v6レポートの表示改善
`landing_comparison_v6.csv` のような**試験の要約CSV**は時間軸を持ちません。
以前は「time_s 列がない」という技術的エラーメッセージが出ていました。
v7ではダッシュボード上で比較レポートと認識し、詳細を別タブで確認できます。

## テスト・共有

```bash
cd ~/INO-module-lab/tools/module_test_lab
~/cansat_gui_venv/bin/python -m unittest discover -s tests -v
```

GitHubへの送信は明示的な操作でのみ行います。実験台帳データはアップデート時に自動変更されません。
