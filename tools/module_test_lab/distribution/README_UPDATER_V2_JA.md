# CanSat Simulation 自動更新 v2（開発ブランチ用）

## 目的と境界

- 既存の `cansat-lab-stable`、`release.json` の `client_protocol: 1`、SHA-256検証とGUIのロールバック機能を維持します。
- 一度だけ v2 インストーラーで更新したPCは、固定ランチャーからバージョン別の更新クライアントを起動します。検証済みのGUIリリースにv2対応更新クライアントが含まれていると、次回起動用として自動的に切り替わります。
- `$HOME`に基づいて起動するので、Ubuntuユーザー名`cansat`以外でも動作します。
- Pythonパッケージの自動更新、ROS 2/Gazebo本体の自動インストール、GitHubのPR承認/配布自動化は **この段階では未実装** です。OS環境を勝手に変更しません。

## レイアウト

```text
~/.local/bin/cansat-lab                      # 固定ランチャー
~/.local/share/cansat-lab/
  cansat_bootstrap.py                        # 固定ブートストラップ（手動移行時のみ設置）
  cansat_update.py                           # 旧更新クライアントのフォールバック用
  client_state.json                          # クライアント版のcurrent/previous
  clients/<sha256>/cansat_update.py          # ハッシュ検証済みの版
  client.json                                # Pythonの実行パス
  state.json                                 # GUIのcurrent/previous
  releases/<git-sha>/                        # SHA-256検証済みGUI
  client_backups/                            # 既存設定・ランチャーを保管
```

## テスト

`cd tools/module_test_lab && python3 -m unittest discover -s tests -p 'test_updater_v2.py' -v`

GUI全体は既存テストも実行します。開発版で検証し、別PC試験が終わるまで stable に送信しません。

## 旧方式からの一度だけの移行（将来の班員向け）

GitHubのリリース配布ファイルに含まれた `distribution` からインストーラーを実行します。実際に導入する前に `--apply` を外して、配布元とPython環境を確認します。従来どおり `install_client.py` が既存のランチャー・更新設定をバックアップします。

```bash
cd path/to/tools/module_test_lab/distribution
python3 install_client.py
python3 install_client.py --apply
cansat-lab --client-status
```

既に導入済みのPCでv2を試す場合も、必ずバックアップと隔離したHOMEでのテストを先に行います。

## 運用

- `cansat-lab --client-status`: 現在のクライアント版と保存場所を確認
- `cansat-lab --client-rollback`: 前の更新クライアントへ戻し、起動時更新を停止
- `cansat-lab --update-rollback`: 既存のGUIロールバック（従来通り）
- `cansat-lab --update-resume`: 起動時の更新を再開

更新クライアントの更新は「既存のGUIリリースで内容検証済み」の場合に限ります。ただしSHA-256は配布の破損検出であり、配布を承認した人物の検証の代わりにはなりません。安定版ブランチの保護と、レビュー済み変更だけを配布する運用が必要です。
