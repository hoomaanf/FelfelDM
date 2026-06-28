# ui/delegates.py
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QStyle, QStyleOptionProgressBar, QStyledItemDelegate


class ProgressDelegate(QStyledItemDelegate):
    """
    Progress bar delegate with color based on status and progress.
    """

    def paint(self, painter, option, index):
        if index.column() == 2:
            text = index.model().data(index, Qt.ItemDataRole.DisplayRole)
            if text and "%" in text:
                try:
                    val = int(text.replace("%", ""))
                    opts = QStyleOptionProgressBar()
                    opts.rect = option.rect.adjusted(4, 4, -4, -4)
                    opts.minimum = 0
                    opts.maximum = 100
                    opts.progress = val
                    opts.text = text
                    opts.textVisible = True

                    # Get status for color
                    status_idx = index.sibling(index.row(), 5)
                    status = ""
                    if status_idx.isValid():
                        status = status_idx.model().data(status_idx, Qt.ItemDataRole.DisplayRole) or ""

                    # Color based on status and progress
                    if "Error" in status:
                        color = QColor(192, 57, 43)   # Red
                    elif "Paused" in status:
                        color = QColor(241, 196, 15)  # Orange
                    elif val == 100:
                        color = QColor(46, 204, 113)  # Green
                    elif "Downloading" in status or "Active" in status:
                        if val < 30:
                            color = QColor(231, 76, 60)   # Red-orange
                        elif val < 70:
                            color = QColor(241, 196, 15)  # Orange
                        else:
                            color = QColor(46, 204, 113)  # Green
                    else:
                        color = QColor(61, 174, 233)      # Blue (default)

                    opts.palette.setColor(QPalette.ColorRole.Highlight, color)
                    QApplication.style().drawControl(QStyle.ControlElement.CE_ProgressBar, opts, painter)
                    return
                except ValueError:
                    pass
        super().paint(painter, option, index)
