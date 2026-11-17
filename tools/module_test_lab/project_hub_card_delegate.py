"""ProjectHub用のカード描画。データと操作処理は変更しない。"""

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyle


class ProjectCardDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        # ProjectHub側で指定されたカード幅を優先する。
        hint = index.data(Qt.SizeHintRole)
        if isinstance(hint, QSize) and hint.isValid():
            return hint
        return QSize(320, 92)

    def paint(self, painter, option, index):
        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        background = (
            "#20445F" if selected
            else "#19364E" if hovered
            else "#13283E"
        )

        border = "#7BDFF4" if selected else "#365A75"

        lines = str(index.data(Qt.DisplayRole) or "").splitlines()
        title = lines[0] if lines else "名称未設定"
        description = lines[1] if len(lines) > 1 else ""

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        rect = option.rect.adjusted(4, 4, -4, -4)

        painter.setPen(QPen(QColor(border), 1.5))
        painter.setBrush(QColor(background))
        painter.drawRoundedRect(rect, 9, 9)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#7BDFF4"))
        painter.drawRoundedRect(
            QRect(rect.left() + 2, rect.top() + 12, 4,
                  max(4, rect.height() - 24)),
            2, 2
        )

        x = rect.left() + 20
        width = max(10, rect.width() - 34)

        font = painter.font()
        font.setPointSize(12)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#F1F8FE"))

        title_text = painter.fontMetrics().elidedText(
            title, Qt.ElideRight, width
        )

        painter.drawText(
            QRect(x, rect.top() + 10, width, 26),
            Qt.AlignLeft | Qt.AlignVCenter,
            title_text
        )

        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#B2CBDE"))

        description_text = painter.fontMetrics().elidedText(
            description, Qt.ElideRight, width
        )

        painter.drawText(
            QRect(x, rect.top() + 42, width, 22),
            Qt.AlignLeft | Qt.AlignVCenter,
            description_text
        )

        painter.restore()
