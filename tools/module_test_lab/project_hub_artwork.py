"""Non-interactive ProjectHub wallpaper behind the existing, real Qt controls.

The PNG contains only the space illustration, never mock UI controls. The
project list, buttons, dialogs, selection state, and launch logic stay native.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QWidget


ARTWORK_PATH = Path(__file__).resolve().with_name('project_hub_space_background.png')


class SpaceHubBackground(QWidget):
    """Draw a cover-scaled illustration; child widgets remain interactive."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._space_wallpaper = QPixmap(str(ARTWORK_PATH))
        self.setAutoFillBackground(False)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        if self._space_wallpaper.isNull():
            painter.fillRect(self.rect(), QColor('#07101D'))
            painter.end()
            return

        image = self._space_wallpaper
        widget_width = max(1, self.width())
        widget_height = max(1, self.height())
        target_ratio = widget_width / widget_height
        image_ratio = image.width() / image.height()

        # Cover the window instead of stretching it. The illustration has no
        # baked-in buttons or text, so small/resized windows remain usable.
        if target_ratio > image_ratio:
            crop_h = image.width() / target_ratio
            source = QRectF(0, (image.height() - crop_h) / 2, image.width(), crop_h)
        else:
            crop_w = image.height() * target_ratio
            source = QRectF((image.width() - crop_w) / 2, 0, crop_w, image.height())

        painter.drawPixmap(QRectF(self.rect()), image, source)
        painter.end()
