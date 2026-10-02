# ui/widgets.py

from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt
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

        # Tinted background
        painter.fillRect(self.rect(), QColor(61, 174, 233, 40))

        # Dashed border
        pen = QPen(QColor("#3daee9"), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        rect = self.rect().adjusted(4, 4, -4, -4)
        painter.drawRoundedRect(rect, 8, 8)

        # Centered message
        painter.setPen(QColor("#3daee9"))
        font = self.font()
        font.setPointSize(16)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            self._message,
        )
        painter.end()