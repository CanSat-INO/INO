# CanSat Module Test Lab v2 — GitHub同期ガイド

## 前提

- 共有先: 非公開 GitHub リポジトリ `CanSat-INO/INO` の `main` ブランチ
- Ubuntu / WSL2 で `gh auth login --hostname github.com --git-protocol https --web` が完了していること
- `gh auth status` と `gh api repos/CanSat-INO/INO --jq .full_name` でアクセスを確認可能
- 現在の `tools/module_test_lab` は ROS 2統合シミュレーターとは独立
- インストール直後はデータをGitHubに**一切送信しない**。ユーザーが送信操作を選んだ時だけ送る

## 使用手順

1. `~/cansat_gui_venv/bin/python ~/INO-module-lab/tools/module_test_lab/app.py` で起動
2. 「実験記録・チーム共有」で「接続確認」→成功か確認
3. 実験結果を「参考アルゴリズムで実行→保存」または「実機・外部試験を登録」で作成
4. 送信する実験の**行を選択**して「選択結果をGitHubに送信」
5. 送信する添付ログを含めて秘密情報がないか確認し、送信に同意
6. 別の担当者は同じアプリで「チーム結果をGitHubから取得」を押し、記録を台帳に統合

## GitHub上の格納先

```text
INO/
  experiments/
    records/
      <32文字の実験ID>.json
    attachments/
      <同じ実験ID>/
        sensor_log.csv
```

1件の実験につきJSONファイル1つ。各JSONは既存の `records.json` と互換のデータ形式です。ログファイルを先に保存してからJSONを作成するので、他メンバーが未完了の実験記録を取得しにくい設計です（途中で通信が失敗すると、ログだけ残ることはあります）。

## 制限・注意

- 同じ実験IDがGitHub上に存在する場合、内容が同じならスキップ、違う場合は**絶対に上書きしません**。
- 「取得」はローカル台帳にない記録のみを追加します。同じIDで内容が異なる場合はローカルも上書きしません。
- GitHub Contents APIの都合で、添付ログは**1ファイル900KB以下**に制限。大きなCSVや動画はクラウドストレージ等で共有し、実験記録にリンクや保管先を記入してください。
- `experiments/records` に1,000件以上のJSONがある場合、現在の一覧APIで全件取得できません。将来ページ対応へ拡張します。
- 実験者名やログに含まれる個人情報、認証情報などを事前に必ず確認してください。
- 実機制御用のArduinoコードを読み込んで実行する機能ではありません。
- GitHub Projects、Issues、既存のROS 2統合シミュレーターは変更しません。
- ネットワークへの送受信はバックグラウンドのスレッドで実行し、完了時に通知します。通信途中にGUIを強制終了すると、ログだけアップロードされた状態が残る場合があります。再度送信を実行すると既存の同一ファイルは再利用します。
- GitHubの権限やブランチ保護によって `main` への直接アップロードが禁止されている場合があります。その場合は失敗を通知します。ブランチ保護を解除する必要はありません。
- データは引き続き `~/cansat_module_lab_data/records.json` と `attachments/` に保存されます。**この保存先を消さないでください。**

## 開発・自動テスト

```bash
cd ~/INO-module-lab/tools/module_test_lab
python3 -m unittest discover -s tests -v
```

`test_github_sync.py` はローカルの擬似GitHubを使うオフライン試験なので、GitHubに勝手な実験データを送信しません。
