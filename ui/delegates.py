# ui/delegates.py

from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionProgressBar, QApplication, QStyle
from PyQt6.QtCore import Qt, QRect, QRectF
from PyQt6.QtGui import QColor, QPalette, QPainter, QBrush, QPen, QPainterPath

class ProgressDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.column() == 2:
            text = index.model().data(index, Qt.ItemDataRole.DisplayRole)
            if text and "%" in text:
                try:
                    val = int(text.replace("%", ""))
                    
                    rect = option.rect.adjusted(4, 4, -4, -4)
                    
                    painter.save()
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    
                    palette = QApplication.palette()
                    window_color = palette.color(QPalette.ColorRole.Window)
                    is_dark = window_color.lightness() < 128
                    
                    if is_dark:
                        bg_color = QColor(45, 45, 48)
                        text_color = QColor(255, 255, 255)
                    else:
                        bg_color = QColor(235, 235, 238)
                        text_color = QColor(30, 30, 33)
                    
                    rect_f = QRectF(rect)
                    
                    main_path = QPainterPath()
                    main_path.addRoundedRect(rect_f, 6.0, 6.0)
                    
                    painter.setBrush(QBrush(bg_color))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawPath(main_path)
                    
                    if val > 0:
                        fill_rect = QRect(
                            rect.x(),
                            rect.y(),
                            int(rect.width() * val / 100),
                            rect.height()
                        )
                        
                        if val < 30:
                            painter.setBrush(QBrush(QColor(231, 76, 60)))
                        elif val < 70:
                            painter.setBrush(QBrush(QColor(241, 196, 15)))
                        else:
                            painter.setBrush(QBrush(QColor(46, 204, 113)))
                        
                        painter.setClipPath(main_path)
                        painter.drawRect(fill_rect)
                    
                    painter.setPen(QPen(text_color))
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{val}%")
                    
                    painter.restore()
                    return
                except ValueError:
                    pass
        super().paint(painter, option, index)