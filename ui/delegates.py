# Requires: PyQt6>=6.4.0
"""Custom delegates for progress bar and status rendering with system palette."""

from typing import Dict

from PyQt6.QtWidgets import QStyledItemDelegate
from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QColor, QPalette, QPainter


class ProgressDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option, index) -> None:
        progress_data = index.data(Qt.ItemDataRole.DisplayRole)
        if progress_data is None:
            super().paint(painter, option, index)
            return

        try:
            if isinstance(progress_data, str) and progress_data.endswith("%"):
                value = float(progress_data[:-1])
            else:
                value = float(progress_data)
        except Exception:
            value = 0

        rect = option.rect
        rect.setLeft(rect.left() + 2)
        rect.setRight(rect.right() - 2)
        rect.setTop(rect.top() + 2)
        rect.setBottom(rect.bottom() - 2)

        painter.save()
        palette = option.palette

        bg_color = palette.color(QPalette.ColorRole.Window)
        painter.fillRect(rect, bg_color)

        if value > 0:
            fill_rect = QRect(rect)
            fill_width = int((value / 100) * rect.width())
            fill_rect.setWidth(fill_width)

            highlight = palette.color(QPalette.ColorRole.Highlight)
            color = QColor(highlight)
            color = color.darker(120) if color.lightness() > 128 else color.lighter(120)
            painter.fillRect(fill_rect, color)

        painter.setPen(palette.color(QPalette.ColorRole.Text))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{value:.1f}%")
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(100, 24)


class StatusDelegate(QStyledItemDelegate):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.status_colors: Dict[str, QColor] = {
            "Downloading": QColor(46, 204, 113),
            "Waiting": QColor(241, 196, 15),
            "Paused": QColor(52, 73, 94),
            "Error": QColor(231, 76, 60),
            "Complete": QColor(46, 204, 113),
            "Removed": QColor(149, 165, 166),
        }

    def paint(self, painter: QPainter, option, index) -> None:
        status = index.data(Qt.ItemDataRole.DisplayRole)
        if not status:
            super().paint(painter, option, index)
            return

        color = self.status_colors.get(status, QColor(149, 165, 166))
        rect = option.rect
        rect.setLeft(rect.left() + 4)
        rect.setRight(rect.right() - 4)
        rect.setTop(rect.top() + 2)
        rect.setBottom(rect.bottom() - 2)

        painter.save()
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 4, 4)

        text_color = QColor(255, 255, 255) if color.lightness() < 128 else QColor(0, 0, 0)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, status)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(80, 24)
