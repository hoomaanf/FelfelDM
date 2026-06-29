# ui/animated_dialog.py
"""
Animated dialog base class with fade-in/fade-out animations.
"""

from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, Qt, pyqtSignal
from PyQt6.QtWidgets import QDialog, QWidget, QVBoxLayout, QFrame


class AnimatedDialog(QDialog):
    """
    A base dialog class with smooth fade-in and fade-out animations.
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

        # Set up the dialog
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)

        # Main container with glass effect
        self._container = QFrame(self)
        self._container.setObjectName("animatedDialogContainer")
        self._container.setStyleSheet("""
            QFrame#animatedDialogContainer {
                background: rgba(30, 30, 46, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 16px;
                backdrop-filter: blur(20px);
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(self._container)

        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(12, 12, 12, 12)

        # Create animations
        self._setup_animations()

    def _setup_animations(self) -> None:
        """Setup fade and slide animations."""
        # Fade animation
        self._fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self._fade_animation.setDuration(self._duration)
        self._fade_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Slide animation (scale)
        self._slide_animation = QPropertyAnimation(self._container, b"geometry")
        self._slide_animation.setDuration(self._duration)
        self._slide_animation.setEasingCurve(QEasingCurve.Type.OutBack)

    def set_content_widget(self, widget: QWidget) -> None:
        """Set the main content widget inside the dialog."""
        self._container_layout.addWidget(widget)

    def content_layout(self) -> QVBoxLayout:
        """Get the content layout for adding widgets."""
        return self._container_layout

    def showEvent(self, event) -> None:
        """Animate show with fade-in and slide-up."""
        super().showEvent(event)

        # Set initial state
        self.setWindowOpacity(0.0)
        geo = self._container.geometry()
        self._container.setGeometry(
            geo.x(),
            geo.y() + 20,
            geo.width(),
            geo.height()
        )

        # Start animations
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.start()

        # Slide animation
        target_geo = self._container.geometry()
        target_geo.setY(target_geo.y() - 20)
        self._slide_animation.setStartValue(geo)
        self._slide_animation.setEndValue(target_geo)
        self._slide_animation.start()

    def closeEvent(self, event) -> None:
        """Animate close with fade-out."""
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.finished.connect(self._on_fade_out_finished)
        self._fade_animation.start()

    def _on_fade_out_finished(self) -> None:
        """Handle fade-out completion."""
        self._fade_animation.finished.disconnect()
        super().closeEvent(None)

    def set_animation_duration(self, duration: int) -> None:
        """Set the animation duration in milliseconds."""
        self._duration = duration
        self._fade_animation.setDuration(duration)
        self._slide_animation.setDuration(duration)

    def exec(self) -> int:
        """Show the dialog and return the result code."""
        self.show()
        return super().exec()
