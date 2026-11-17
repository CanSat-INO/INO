"""ProjectHubカードのサイズ指定を検証する。"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QListWidgetItem,
    QStyleOptionViewItem,
)

from project_hub_card_delegate import ProjectCardDelegate


def test_card_respects_item_size_hint():
    app = QApplication.instance() or QApplication([])

    widget = QListWidget()
    delegate = ProjectCardDelegate(widget)
    widget.setItemDelegate(delegate)

    item = QListWidgetItem("INO\n2026")
    widget.addItem(item)

    item.setSizeHint(QSize(388, 92))

    index = widget.model().index(0, 0)
    actual = delegate.sizeHint(
        QStyleOptionViewItem(), index
    )

    assert actual.width() == 388
    assert actual.height() == 92

    widget.close()
