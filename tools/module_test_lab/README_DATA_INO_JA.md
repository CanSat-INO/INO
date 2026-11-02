# CanSat Module Test Lab v23.3 — INO GitHubデータ保存先の変更

## 変更内容

- 新しい送信先（GitHubの `main` ブランチ）: `data/ino/records/<ID>.json`、`data/ino/attachments/<ID>/<ファイル名>`
- 従来の `experiments/records/`、`experiments/attachments/` も取得対象として維持します。
- 送信時には旧保存先と新保存先の両方で同じ実験IDを確認し、内容が異なれば停止します。
- 同じ実験が旧保存先に存在する場合、新保存先へ勝手に複製・移動しません。
- 新旧両方に同一IDの記録がある場合、同じ内容なら1件として扱い、異なる内容なら取得を停止します。
- ローカルから削除（退避）したIDは、GitHubに残っていても通常の取得では復活させません。
- `~/cansat_module_lab_data` の保存形式とパス、GUI、他のINOファイルは変更しません。

## 適用前に

GitHub側の `data/ino` は **GitHub上にまだ作成されていません**。ローカルの `data/ino/records/.gitkeep`、`data/ino/attachments/.gitkeep` は後で Git に登録してください。GitHub API経由で初めて送信する際は、リポジトリ内にフォルダがなくてもGitHub APIがファイルのパスを作成します。

このZIPを `C:\Users\user.LAPTOP-8FBLD6DP\OneDrive\Desktop\cansatino\アプデzip\` に保存してください。

```bash
ZIP="/mnt/c/Users/user.LAPTOP-8FBLD6DP/OneDrive/Desktop/cansatino/アプデzip/cansat_test_lab_ino_v23_3_data_path_patch.zip"
UPDATE_DIR="$(mktemp -d "$HOME/cansat_v23_3_update_XXXXXX")"
python3 -m zipfile -e "$ZIP" "$UPDATE_DIR"
python3 "$UPDATE_DIR/install.py" --repo "$HOME/INO-module-lab" --check
```

**チェックに成功してから、Test Labを終了し**、以下を実行します。

```bash
python3 "$UPDATE_DIR/install.py" --repo "$HOME/INO-module-lab" --apply
cd ~/INO-module-lab/tools/module_test_lab
python3 -m unittest discover -s tests -p 'test_github_sync.py' -v
cansat-lab
```

GitHub接続確認、チーム結果の取得を確認してください。**最初は「送信」を押さず**、テスト用の架空・匿名記録を用意してから送信確認します。すでに他メンバーが記録を書き込んでいる場合や、mainブランチが保護されている場合は、作業を調整してください。

## GitHubで共有するときの注意

- GUIの送信・取得は `gh api` によるGitHub Contents APIへの**手動同期**で、`git add`/`git push` とは別です。同期はデフォルトで `main` に直接書き込むため、リポジトリ側の保護設定によっては失敗します。
- リポジトリが非公開であることを毎回確認してから送信します。
- 1添付あたり900KiB以下です。大量・大容量データはOneDrive等へ保存します。
- ローカルの旧データは消しません。削除（退避）操作を明示的に行わない限り、取り込み処理で既存記録を上書きしません。
- GUI上の削除はローカルだけです。GitHub上の古い記録は削除しません。
