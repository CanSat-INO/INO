# CanSat Module Test Lab v4 — Arduino/外部CSVログ解析（第1段階）

現行の **v3を残したまま**、着地検知CSVログを解析するタブを追加します。
ROS 2・Gazebo・ESP32-S3の実機環境には変更を加えません。

## 実装したこと

1. Arduino担当者や外部試験が出力した **UTF-8 CSV** を選択して読み込む。
2. CSVの `landing_detected` が初めて `0` から `1` になった時刻を取得。
3. `truth_contact` 列、または画面で指定した真の接地時刻と比較。
4. **早期誤判定／許容遅延超過／検知なし／未判定** を区別する。
5. `imu_z_mps2` と `pressure_pa` を既存のグラフ部品で可視化する。
6. 試験条件と判定結果、元CSVを既存の実験台帳に添付して保存。
7. 保存した記録を既存のダッシュボードで閲覧し、既存の手動GitHub共有で送信。

**注意：.ino を直接コンパイル・実行する機能ではありません。** CSVが実機由来であるかは、ユーザーが選ぶ「データの種類」に従って区別します。現時点では `.ino` のアルゴリズム検証自体は別途行う必要があります。

## 初回起動と動作確認

開発ブランチでインストール後、Ubuntuで以下を実行します。

```bash
cd ~/INO-module-lab
QT_QPA_PLATFORM=xcb ~/cansat_gui_venv/bin/python tools/module_test_lab/app.py
```

「Arduino/CSVログ解析」タブが増えています。

テスト用のサンプルを作成する場合:

```bash
cd ~/INO-module-lab
~/cansat_gui_venv/bin/python tools/module_test_lab/examples/make_demo_csv.py
```

生成された `~/cansat_module_lab_data/demo_virtual_landing.csv` をタブから読み込み、「CSVを解析」を押します。初期設定の許容遅延（5秒）なら成功と評価される**仮想サンプル**です。これを実機ログと誤認しないよう、サンプルでは「外部シミュレーション」を選択してください。

## CSVフォーマット

```csv
time_ms,imu_z_mps2,pressure_pa,landing_detected,truth_contact
0,9.81,101000,0,0
1000,9.79,101012,0,0
2000,30.0,101024,0,1
3000,9.80,101024,1,1
```

- `time_ms` 必須（`time_s`でも可）。時刻は **0以上・昇順・重複なし**。
- `landing_detected` 必須。0/1またはtrue/false。
- `imu_z_mps2`, `pressure_pa` 任意。片方でもあればグラフ表示に利用。
- `truth_contact` 任意。接地している時刻の行から1。物理的な正解時刻が不明な場合は列を省き、GUIで入力するか「未判定」のまま保存。
- データはUTF-8、先頭BOM可。GitHub共有の既存上限に合わせて **900 KiBまで**。
- フラグが最初から1の場合、検知瞬間は不明なので「未判定」。
- 接地時刻が未指定なら、単に検知時刻があっても**正解とは判定しません**。
- 検知されなかった場合、正解時刻＋許容遅延まで記録されていないと**未判定**。

## 実験記録への登録

CSVの解析後に「結果を実験記録に保存」をクリックすると、既存の `records.json` に1件追加し、元CSVを添付します。保存後「結果ダッシュボード」で確認できます。

GitHubへ勝手にアップロードしません。**実験記録・チーム共有**タブで、アップロードする行を選んでから手動送信してください。

## 次の段階（未実装）

- Arduinoの判定・制御ロジックを、実機依存部分と分離したC++コードとしてホストPCで実行する仕組み
- Arduinoのシリアルログのリアルタイム受信
- GNSS誘導や走行制御などのモジュール向け検証アダプター

## 既存環境への影響

既存の `app.py` のタブ登録・インポート部分に最小限の変更を加えます。`dashboard.py`、`dashboard_data.py`、`records.py`、`github_sync.py` は上書きしません。
新機能はローカルCSVのみ読み込み、外部プログラムの実行やGitHubへの自動送信は行いません。
