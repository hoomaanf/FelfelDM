# ui/delegates.py
"""
Custom delegates for table rendering.
"""

import logging
from typing import Optional

from PyQt6.QtCore import Qt, QRect, QModelIndex, QSize
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QWidget

from utils.helpers import format_size

logger = logging.getLogger(__name__)


class ProgressDelegate(QStyledItemDelegate):
    """
    Custom delegate that renders a progress bar with color coding based on status.
    """

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """Paint the progress bar with color coding."""
        # Get data from the model
        progress_data = index.data(Qt.ItemDataRole.DisplayRole)
        if progress_data is None:
            # No data to paint, fallback to default
            super().paint(painter, option, index)
            return

        # Try to parse progress
        try:
            # progress_data might be like "45%" or just "45"
            if isinstance(progress_data, str) and progress_data.endswith('%'):
                progress_str = progress_data[:-1]
            else:
                progress_str = str(progress_data)

            if not progress_str:
                # Empty string
                super().paint(painter, option, index)
                return

            progress = int(float(progress_str))
        except (ValueError, TypeError):
            # Invalid progress data, fallback
            super().paint(painter, option, index)
            return

        # Get status from the same row (assuming status is in column 5)
        status_index = index.sibling(index.row(), 5)
        status = status_index.data(Qt.ItemDataRole.DisplayRole) if status_index.isValid() else ""
        status_str = str(status) if status is not None else ""

        # Determine color based on status and progress
        if "Error" in status_str:
            color = QColor(192, 57, 43)  # Red
        elif "Paused" in status_str:
            color = QColor(241, 196, 15)  # Orange
        elif progress == 100:
            color = QColor(46, 204, 113)  # Green
        elif "Downloading" in status_str or "Active" in status_str:
            if progress < 30:
                color = QColor(231, 76, 60)  # Red-orange
            elif progress < 70:
                color = QColor(241, 196, 15)  # Orange
            else:
                color = QColor(46, 204, 113)  # Green
        else:
            color = QColor(61, 174, 233)  # Blue (default)

        # Draw background
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background rectangle
        rect = option.rect
        margin = 2
        bar_rect = QRect(rect.x() + margin, rect.y() + margin,
                         rect.width() - 2 * margin, rect.height() - 2 * margin)

        # Draw background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(240, 240, 240) if option.state & QStyle.StateFlag.State_Selected else QColor(45, 45, 45))
        painter.drawRoundedRect(bar_rect, 3, 3)

        # Draw progress chunk
        if progress > 0:
            progress_width = int(bar_rect.width() * (progress / 100.0))
            if progress_width > 0:
                chunk_rect = QRect(bar_rect.x(), bar_rect.y(),
                                   progress_width, bar_rect.height())
                painter.setBrush(color)
                painter.drawRoundedRect(chunk_rect, 3, 3)

        # Draw text
        painter.setPen(Qt.GlobalColor.white if option.state & QStyle.StateFlag.State_Selected else Qt.GlobalColor.black)
        painter.drawText(bar_rect, Qt.AlignmentFlag.AlignCenter, f"{progress}%")

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        """Provide a size hint for the progress bar."""
        return QSize(100, 24)
