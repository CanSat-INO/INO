"""機能一覧の大分類テスト。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from navigation_feature_groups import (
    FEATURE_GROUPS,
    TITLE_GROUPS,
    feature_group_for,
)


def test_all_registered_titles_classified():
    assert len(TITLE_GROUPS) == 27
    assert "other" not in TITLE_GROUPS.values()


def test_five_primary_groups():
    keys = [item[0] for item in FEATURE_GROUPS]

    assert keys[:5] == [
        "sensor",
        "code",
        "mission",
        "records",
        "system",
    ]


def test_platformio_is_code():
    assert feature_group_for(
        "PlatformIOコード検証"
    ) == "code"


def test_diagnostics_is_system():
    assert feature_group_for(
        "環境診断"
    ) == "system"


def test_mission_is_mission():
    assert feature_group_for(
        "フェーズ別ミッション・仮想試験"
    ) == "mission"


def test_experiment_records():
    assert feature_group_for(
        "実験記録・チーム共有"
    ) == "records"


def test_sensor_log():
    assert feature_group_for(
        "センサー実験・ログ解析"
    ) == "sensor"


def test_unknown_title():
    assert feature_group_for(
        "将来追加する新機能"
    ) == "other"


def test_every_group_has_items():
    used = set(TITLE_GROUPS.values())

    assert used == {
        "sensor",
        "code",
        "mission",
        "records",
        "system",
    }
