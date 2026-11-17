"""共通GUI寸法の回帰テスト。"""

from project_theme import SPACE_STYLE
from ui_design_tokens import DARK_UI_METRICS


def test_metrics_are_defined():
    assert DARK_UI_METRICS["button_radius"] == "7px"
    assert DARK_UI_METRICS["group_radius"] == "8px"
    assert DARK_UI_METRICS["input_radius"] == "6px"


def test_stylesheet_resolves_metrics():
    assert "${" not in SPACE_STYLE
    assert "border-radius: 7px;" in SPACE_STYLE
    assert "border-radius: 8px;" in SPACE_STYLE
    assert "border-radius: 6px;" in SPACE_STYLE


def test_button_minimum_height():
    assert "min-height: 22px;" in SPACE_STYLE
