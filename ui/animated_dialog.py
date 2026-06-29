# =============================================================================
# ui/animated_dialog.py
# =============================================================================
import sys
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QWidget, QLabel, QPushButton,
    QGraphicsOpacityEffect, QFrame
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont


class AnimatedDialog(QDialog):
    """A dialog with glass-morphism and fade-in animation, with fallback for Linux."""

    def __init__(self, parent=None, title: str = "", message: str = ""):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setModal(True)

        # Detect if backdrop-filter is supported (Linux may lack support)
        self._use_glass = self._check_glass_support()
        self._setup_style()

        self._content_widget = None

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(16)

        # Title
        self.title_label = QLabel(title)
        self.title_label.setObjectName("title")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.title_label)

        # Message
        self.message_label = QLabel(message)
        self.message_label.setObjectName("message")
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setWordWrap(True)
        main_layout.addWidget(self.message_label)

        # Content area
        self.content_frame = QFrame()
        self.content_frame.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.content_frame)

        # Button row
        self.button_layout = QVBoxLayout()
        main_layout.addLayout(self.button_layout)

        # Start with fade-in animation
        self._start_animation()

    def _check_glass_support(self) -> bool:
        """Check if backdrop-filter is likely supported (not Linux with old compositors)."""
        # For simplicity, we disable glass on Linux
        if sys.platform.startswith("linux"):
            return False
        return True

    def _setup_style(self) -> None:
        if self._use_glass:
            self.setStyleSheet("""
                QDialog {
                    background: rgba(30, 30, 40, 0.7);
                    border-radius: 16px;
                    border: 1px solid rgba(255, 255, 255, 0.1);
                }
                QLabel#title {
                    font-size: 18px;
                    font-weight: bold;
                    color: #ffffff;
                }
                QLabel#message {
                    font-size: 14px;
                    color: #cccccc;
                }
                QPushButton {
                    background: rgba(255, 255, 255, 0.1);
                    color: #ffffff;
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 8px;
                    padding: 8px 20px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.2);
                }
            """)
        else:
            # Fallback: solid background with opacity
            self.setStyleSheet("""
                QDialog {
                    background: rgba(40, 40, 50, 0.9);
                    border-radius: 16px;
                    border: 1px solid #555;
                }
                QLabel#title {
                    font-size: 18px;
                    font-weight: bold;
                    color: #ffffff;
                }
                QLabel#message {
                    font-size: 14px;
                    color: #cccccc;
                }
                QPushButton {
                    background: #3a3a4a;
                    color: #ffffff;
                    border: 1px solid #5a5a6a;
                    border-radius: 8px;
                    padding: 8px 20px;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: #4a4a5a;
                }
            """)

    def _start_animation(self):
        opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(opacity)
        anim = QPropertyAnimation(opacity, b"opacity")
        anim.setDuration(300)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()

    def set_content_widget(self, widget: QWidget):
        if self._content_widget:
            self.content_layout.removeWidget(self._content_widget)
            self._content_widget.deleteLater()
            self._content_widget = None
        if widget:
            self.content_layout.addWidget(widget)
            self._content_widget = widget

    def add_button(self, text: str, callback=None):
        btn = QPushButton(text)
        if callback:
            btn.clicked.connect(callback)
        self.button_layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        return btn

    def closeEvent(self, event):
        if self._content_widget:
            self.content_layout.removeWidget(self._content_widget)
            self._content_widget.deleteLater()
            self._content_widget = None
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.processEvents()
        super().closeEvent(event)
