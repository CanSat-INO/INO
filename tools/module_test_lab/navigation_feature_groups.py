"""機能一覧の目的別大分類。元のタブ名・タブ番号は変更しない。"""

FEATURE_GROUPS = (
    ("sensor", "センサー・データ解析", "センサーや測定ログを確認"),
    ("code", "コード・実機前検証", "実コードの動作をPCで検証"),
    ("mission", "ミッション・異常解析", "状態遷移や異常条件を検証"),
    ("records", "実験記録・比較", "実験の保存、比較、結果の確認"),
    ("system", "システム・管理", "環境診断、共通基盤、使い方"),
    ("other", "その他", "未分類の機能"),
)

TITLE_GROUPS = {
    # センサー・データ解析
    "着地検知シミュレーション": "sensor",
    "センサー実験・ログ解析": "sensor",
    "着地パラメータ探索": "sensor",
    "Arduino/CSVログ解析": "sensor",

    # コード・実機前検証
    "PlatformIOコード検証": "code",
    "着地・Drive・CAM・Main ロジック検証": "code",
    "Main・CAM・Drive C++実コード検証": "code",
    "Main・CAM・Drive C++個別試験": "code",
    "C++モジュール連携": "code",
    "着地コード比較": "code",
    "C++着地判定": "code",

    # ミッション・異常解析
    "フェーズ別ミッション・仮想試験": "mission",
    "Main・CAM・Drive 仮想通信検証（v18）": "mission",
    "異常分析": "mission",
    "3モジュール・仮想CAN": "mission",
    "着地一括テスト": "mission",

    # 実験記録・比較
    "実験記録・チーム共有": "records",
    "実験管理・仮想ログ比較（v19）": "records",
    "実験記録・コード版管理（v16）": "records",
    "v12 実験管理・一括比較": "records",
    "統合実験結果": "records",
    "結果ダッシュボード": "records",

    # システム・管理
    "環境診断": "system",
    "共通基盤・全体品質チェック（v21）": "system",
    "共通基盤・実験ワークフロー（v20）": "system",
    "シミュレーション共通基盤": "system",
    "使い方・Arduinoとの接続": "system",
}


def feature_group_for(title):
    """未知の機能は誤分類せず「その他」に表示する。"""
    return TITLE_GROUPS.get(str(title), "other")


# 機能カードで使用する色（アクセント色・アイコン背景色）
FEATURE_GROUP_COLORS = {
    "sensor": ("#168B80", "#DDF7F1"),
    "code": ("#3679D8", "#E6EFFF"),
    "mission": ("#B77B2E", "#FFF0DB"),
    "records": ("#8752C8", "#F1E9FF"),
    "system": ("#367D9D", "#E3F4FC"),
    "other": ("#68788F", "#EEF1F6"),
}


def feature_group_presentation(title):
    """分類名、アクセント色、背景色、説明を返す。"""
    key = feature_group_for(title)
    group = next(
        (entry for entry in FEATURE_GROUPS if entry[0] == key),
        None
    )
    if group is None:
        raise ValueError(f"不明な分類: {key}")

    _, label, hint = group
    accent, pale = FEATURE_GROUP_COLORS[key]
    return label, accent, pale, hint
