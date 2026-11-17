"""Space-themed project hub wallpaper must not replace interactive controls."""
from pathlib import Path

from PySide6.QtWidgets import QApplication
from project_hub_artwork import ARTWORK_PATH, SpaceHubBackground


def test_space_wallpaper_asset_exists():
    assert ARTWORK_PATH.is_file()
    assert ARTWORK_PATH.stat().st_size > 100_000


def test_space_wallpaper_renders_at_different_sizes():
    app = QApplication.instance() or QApplication([])
    widget = SpaceHubBackground()
    assert not widget._space_wallpaper.isNull()
    widget.show()
    app.processEvents()
    for width, height in ((1600, 900), (820, 700), (1920, 1080)):
        widget.resize(width, height)
        app.processEvents()
        image = widget.grab().toImage()
        assert image.width() == width
        assert image.height() == height
        assert not image.isNull()
    widget.close()
