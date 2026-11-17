"""共通デザイントークンの回帰テスト。"""

import re

from project_theme import SPACE_STYLE
from ui_design_tokens import DARK_UI_COLORS


def test_colors_are_valid_hex():
    assert all(
        re.fullmatch(r"#[0-9A-Fa-f]{6}", value)
        for value in DARK_UI_COLORS.values()
    )


def test_stylesheet_resolves_all_tokens():
    assert "${" not in SPACE_STYLE
    assert "QMainWindow" in SPACE_STYLE


def test_dark_colors_are_used():
    assert DARK_UI_COLORS["background"] in SPACE_STYLE
    assert DARK_UI_COLORS["foreground"] in SPACE_STYLE
    assert DARK_UI_COLORS["accent"] in SPACE_STYLE
