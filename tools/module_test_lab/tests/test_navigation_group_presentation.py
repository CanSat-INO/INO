"""機能カードの5分類表示を確認する。"""

import pytest

from navigation_feature_groups import (
    FEATURE_GROUPS,
    FEATURE_GROUP_COLORS,
    feature_group_presentation,
)


def test_all_groups_have_colors():
    keys = {key for key, _, _ in FEATURE_GROUPS}
    assert keys == set(FEATURE_GROUP_COLORS)


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Arduino/CSVログ解析", "センサー・データ解析"),
        ("PlatformIOコード検証", "コード・実機前検証"),
        ("異常分析", "ミッション・異常解析"),
        ("実験記録・チーム共有", "実験記録・比較"),
        ("環境診断", "システム・管理"),
        ("未登録の機能", "その他"),
    ],
)
def test_category_display(title, expected):
    label, accent, pale, hint = feature_group_presentation(title)

    assert label == expected
    assert accent.startswith("#")
    assert pale.startswith("#")
    assert hint
