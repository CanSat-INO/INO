"""Responsive layout for the landing simulation screen."""

from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QBoxLayout


class LandingLayoutController(QObject):
    """Switch layout according to actual scroll viewport width."""

    def __init__(self, scroll, layout, controls, threshold=900):
        super().__init__(scroll)
        self.scroll = scroll
        self.layout = layout
        self.controls = controls
        self.threshold = threshold
        self._adjusting = False

        # Keep the viewport reference without querying a deleted scroll.
        self._viewport = scroll.viewport()
        self._viewport.installEventFilter(self)
        self.reflow()

    def eventFilter(self, watched, event):
        if (
            watched is self._viewport
            and event.type() == QEvent.Resize
        ):
            self.reflow()

        return super().eventFilter(watched, event)

    def reflow(self):
        if self._adjusting:
            return

        width = self._viewport.width()

        direction = (
            QBoxLayout.TopToBottom
            if width < self.threshold
            else QBoxLayout.LeftToRight
        )

        if self.layout.direction() == direction:
            return

        self._adjusting = True
        try:
            # Wide screens keep the controls compact.
            # Narrow screens allow the controls to use full width.
            self.controls.setMaximumWidth(
                360 if direction == QBoxLayout.LeftToRight
                else 16777215
            )

            self.layout.setDirection(direction)
            self.layout.invalidate()

            content = self.layout.parentWidget()
            if content is not None:
                content.updateGeometry()
        finally:
            self._adjusting = False
