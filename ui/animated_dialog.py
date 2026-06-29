# =============================================================================
# ui/animated_dialog.py
# =============================================================================
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QWidget, QLabel, QPushButton,
    QGraphicsOpacityEffect, QFrame
)
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup
from PyQt6.QtGui import QFont


class AnimatedDialog(QDialog):
    """A dialog with glass-morphism and fade-in animation, with proper cleanup."""

    def __init__(self, parent=None, title: str = "", message: str = ""):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setModal(True)
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

        self._content_widget = None
        self._anim_group = None

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

        # Content area (for custom widgets)
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

    def _start_animation(self):
        """Apply fade-in animation."""
        opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(opacity)
        anim = QPropertyAnimation(opacity, b"opacity")
        anim.setDuration(300)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start()

    def set_content_widget(self, widget: QWidget):
        """Set a custom content widget, properly deleting previous one."""
        if self._content_widget:
            # Remove and delete old widget
            self.content_layout.removeWidget(self._content_widget)
            self._content_widget.deleteLater()
            self._content_widget = None

        if widget:
            self.content_layout.addWidget(widget)
            self._content_widget = widget

    def add_button(self, text: str, callback=None):
        """Add a button to the dialog."""
        btn = QPushButton(text)
        if callback:
            btn.clicked.connect(callback)
        self.button_layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        return btn

    def closeEvent(self, event):
        """Ensure all child widgets are properly deleted on close."""
        if self._content_widget:
            self.content_layout.removeWidget(self._content_widget)
            self._content_widget.deleteLater()
            self._content_widget = None

        # Process pending events to ensure deletion
        from PyQt6.QtCore import QCoreApplication
        QCoreApplication.processEvents()

        super().closeEvent(event)
