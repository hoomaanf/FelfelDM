# ui/delegates.py
"""
Custom delegates for table view: progress bar and status rendering.
"""

from typing import Optional

from PyQt6.QtCore import Qt, QRect, QSize
from PyQt6.QtGui import QColor, QPalette, QPainter
from PyQt6.QtWidgets import (
    QStyledItemDelegate, QStyle, QApplication, QStyleOptionProgressBar,
)

class ProgressDelegate(QStyledItemDelegate):
    """
    Delegate that renders a progress bar for the Progress column.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

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
        except (ValueError, TypeError):
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
            # Get status from the row's Status column (column 5)
            status_idx = index.sibling(index.row(), 5)
            status_text = ""
            if status_idx.isValid():
                status_text = status_idx.data(Qt.ItemDataRole.DisplayRole) or ""

            # Choose color based on status
            if "Error" in status_text:
                color = QColor(231, 76, 60)
            elif "Paused" in status_text:
                color = QColor(243, 156, 18)
            elif "Complete" in status_text:
                color = QColor(46, 204, 113)
            else:
                color = QColor(52, 152, 219)

            painter.fillRect(fill_rect, color)

        painter.setPen(palette.color(QPalette.ColorRole.Text))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{value:.1f}%")
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(100, 24)


class StatusDelegate(QStyledItemDelegate):
    """
    Delegate that renders status as colored rounded labels.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.status_colors = {
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

        painter.setPen(QColor(255, 255, 255))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, status)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(80, 24)
