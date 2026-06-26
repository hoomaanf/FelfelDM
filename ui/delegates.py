# ui/delegates.py

from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionProgressBar, QApplication, QStyle
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette

class ProgressDelegate(QStyledItemDelegate):
    """نمایش پیشرفت به صورت نوار در جدول"""
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
                    
                    if val < 30:
                        opts.palette.setColor(QPalette.ColorRole.Highlight, QColor(231, 76, 60))
                    elif val < 70:
                        opts.palette.setColor(QPalette.ColorRole.Highlight, QColor(241, 196, 15))
                    else:
                        opts.palette.setColor(QPalette.ColorRole.Highlight, QColor(46, 204, 113))
                    
                    QApplication.style().drawControl(QStyle.ControlElement.CE_ProgressBar, opts, painter)
                    return
                except ValueError:
                    pass
        super().paint(painter, option, index)