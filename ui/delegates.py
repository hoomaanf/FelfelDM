# ui/delegates.py

from PyQt6.QtWidgets import (
    QStyledItemDelegate,
    QStyleOptionProgressBar,
    QApplication,
    QStyle,
)
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

                    # ===== تنظیم رنگ‌ها با کنتراست بهتر =====
                    if is_dark:
                        # حالت تاریک
                        bg_color = QColor(55, 55, 60)      # پس‌زمینه تیره
                        text_color = QColor(255, 255, 255)  # متن سفید
                        border_color = QColor(70, 70, 75)   # حاشیه تیره
                    else:
                        # حالت روشن - پس‌زمینه روشن‌تر از سطر
                        bg_color = QColor(230, 230, 235)    # پس‌زمینه روشن
                        text_color = QColor(30, 30, 33)     # متن تیره
                        border_color = QColor(200, 200, 205) # حاشیه روشن

                    rect_f = QRectF(rect)

                    # ===== رسم پس‌زمینه با حاشیه =====
                    main_path = QPainterPath()
                    main_path.addRoundedRect(rect_f, 6.0, 6.0)

                    painter.setBrush(QBrush(bg_color))
                    painter.setPen(QPen(border_color, 1))
                    painter.drawPath(main_path)

                    # ===== رسم پیشرفت =====
                    if val > 0:
                        fill_rect = QRect(
                            rect.x(),
                            rect.y(),
                            int(rect.width() * val / 100),
                            rect.height(),
                        )

                        # ===== رنگ‌های پیشرفت =====
                        if val < 30:
                            painter.setBrush(QBrush(QColor(231, 76, 60)))   # قرمز
                        elif val < 70:
                            painter.setBrush(QBrush(QColor(241, 196, 15)))  # زرد
                        else:
                            painter.setBrush(QBrush(QColor(46, 204, 113)))  # سبز

                        painter.setClipPath(main_path)
                        painter.drawRect(fill_rect)

                    # ===== رسم متن =====
                    painter.setPen(QPen(text_color))
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{val}%")

                    painter.restore()
                    return
                except ValueError:
                    pass
        super().paint(painter, option, index)