# ui/animated_dialog.py
"""
Animated dialog base class with fade-in/fade-out animations.
Provides a modern glass-morphism style container with smooth transitions.
"""

from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, Qt, pyqtSignal
from PyQt6.QtWidgets import QDialog, QWidget, QVBoxLayout, QFrame
from PyQt6.QtGui import QCloseEvent


class AnimatedDialog(QDialog):
    """
    A base dialog class with smooth fade-in and fade-out animations.
    Uses a glass-morphism styled container for modern appearance.
    """

    def __init__(
        self,
        parent: QWidget = None,
        flags: Qt.WindowType = Qt.WindowType.Dialog,
        duration: int = 200,
    ) -> None:
        super().__init__(parent, flags)

        self._duration = duration
        self._fade_animation: QPropertyAnimation = None
        self._slide_animation: QPropertyAnimation = None
        self._is_closing = False

        # Set up the dialog
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        # Main container with glass effect
        self._container = QFrame(self)
        self._container.setObjectName("animatedDialogContainer")
        self._container.setStyleSheet("""
            QFrame#animatedDialogContainer {
                background: rgba(26, 26, 46, 0.92);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                backdrop-filter: blur(20px);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(self._container)

        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(16, 16, 16, 16)

        # Create animations
        self._setup_animations()

    def _setup_animations(self) -> None:
        """Setup fade and slide animations."""
        # Fade animation
        self._fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self._fade_animation.setDuration(self._duration)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Slide animation (scale/position)
        self._slide_animation = QPropertyAnimation(self._container, b"geometry")
        self._slide_animation.setDuration(self._duration)
        self._slide_animation.setEasingCurve(QEasingCurve.Type.OutBack)

    def set_content_widget(self, widget: QWidget) -> None:
        """Set the main content widget inside the dialog."""
        # Clear existing content
        while self._container_layout.count():
            item = self._container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._container_layout.addWidget(widget)

    def content_layout(self) -> QVBoxLayout:
        """Get the content layout for adding widgets."""
        return self._container_layout

    def set_animation_duration(self, duration: int) -> None:
        """Set the animation duration in milliseconds."""
        self._duration = duration
        self._fade_animation.setDuration(duration)
        self._slide_animation.setDuration(duration)

    def showEvent(self, event) -> None:
        """Animate show with fade-in and slide-up."""
        super().showEvent(event)

        # Reset closing flag
        self._is_closing = False

        # Set initial state
        self.setWindowOpacity(0.0)
        geo = self._container.geometry()
        self._container.setGeometry(
            geo.x(),
            geo.y() + 30,
            geo.width(),
            geo.height()
        )

        # Start animations
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.start()

        # Slide animation
        target_geo = self._container.geometry()
        target_geo.setY(target_geo.y() - 30)
        self._slide_animation.setStartValue(geo)
        self._slide_animation.setEndValue(target_geo)
        self._slide_animation.start()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle close event with animation."""
        if not self._is_closing:
            event.ignore()
            self._start_close_animation()
        else:
            super().closeEvent(event)

    def _start_close_animation(self) -> None:
        """Start the close animation."""
        self._is_closing = True
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.finished.connect(self._on_close_animation_finished)
        self._fade_animation.start()

    def _on_close_animation_finished(self) -> None:
        """Handle close animation completion."""
        self._fade_animation.finished.disconnect()
        self._is_closing = False
        super().close()

    def accept(self) -> None:
        """Accept the dialog with animation."""
        if not self._is_closing:
            self._is_closing = True
            self._fade_animation.setStartValue(1.0)
            self._fade_animation.setEndValue(0.0)
            self._fade_animation.finished.connect(self._on_accept_finished)
            self._fade_animation.start()

    def _on_accept_finished(self) -> None:
        """Handle accept animation completion."""
        self._fade_animation.finished.disconnect()
        self._is_closing = False
        super().accept()

    def reject(self) -> None:
        """Reject the dialog with animation."""
        if not self._is_closing:
            self._is_closing = True
            self._fade_animation.setStartValue(1.0)
            self._fade_animation.setEndValue(0.0)
            self._fade_animation.finished.connect(self._on_reject_finished)
            self._fade_animation.start()

    def _on_reject_finished(self) -> None:
        """Handle reject animation completion."""
        self._fade_animation.finished.disconnect()
        self._is_closing = False
        super().reject()

    def exec(self) -> int:
        """
        Execute the dialog and return the result code.
        This overrides QDialog.exec() to ensure proper behavior.
        """
        self.show()
        return super().exec()

    def exec_(self) -> int:
        """Alias for exec() for compatibility."""
        return self.exec()
