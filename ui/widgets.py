# ui/widgets.py

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QPen, QColor


class DropOverlay(QWidget):
    """Semi-transparent overlay shown while a drag hovers the main window.

    Draws a tinted background, a dashed border, and a centered hint so
    the user knows the drop is accepted. Mouse events pass through, so
    the overlay never steals input from the widgets underneath.
    """

    def __init__(self, parent=None, message: str = "Drop to add download"):
        super().__init__(parent)
        self._message = message
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_message(self, message: str) -> None:
        self._message = message
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        accent = QColor("#3b82f6")

        # Soft tint over the whole window
        painter.fillRect(self.rect(), QColor(accent.red(), accent.green(), accent.blue(), 26))

        # Dashed rounded drop zone
        pen = QPen(accent, 2, Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([6, 5])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        zone = QRectF(self.rect()).adjusted(12, 12, -12, -12)
        painter.drawRoundedRect(zone, 16, 16)

        # Centered pill with the message
        font = self.font()
        font.setPointSize(13)
        font.setBold(True)
        painter.setFont(font)
        fm = painter.fontMetrics()
        w = fm.horizontalAdvance(self._message) + 56
        h = fm.height() + 28
        pill = QRectF(0, 0, w, h)
        pill.moveCenter(QRectF(self.rect()).center())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(pill, h / 2, h / 2)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, self._message)
        painter.end()
