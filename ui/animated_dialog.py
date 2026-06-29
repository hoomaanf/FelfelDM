# ui/animated_dialog.py
"""
Animated dialog base class with fade-in/fade-out animations.
"""

from PyQt6.QtCore import QPropertyAnimation, QEasingCurve, Qt
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
        self._content_widget: QWidget = None

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

        # Slide animation (geometry)
        self._slide_animation = QPropertyAnimation(self._container, b"geometry")
        self._slide_animation.setDuration(self._duration)
        self._slide_animation.setEasingCurve(QEasingCurve.Type.OutBack)

    def set_content_widget(self, widget: QWidget) -> None:
        """
        Set the main content widget inside the dialog.
        Connects the widget's accepted/rejected signals to the dialog.
        """
        self._content_widget = widget
        self._container_layout.addWidget(widget)

        # Connect signals from the content widget to this dialog
        if hasattr(widget, 'accepted'):
            widget.accepted.connect(self.accept)
        if hasattr(widget, 'rejected'):
            widget.rejected.connect(self.reject)

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
        # If the dialog is already closed, just finish
        if not self.isVisible():
            super().closeEvent(event)
            return

        # Start fade-out animation
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.finished.connect(self._on_fade_out_finished)
        self._fade_animation.start()

        # Don't accept the event yet, wait for animation to finish
        event.ignore()

    def _on_fade_out_finished(self) -> None:
        """Handle fade-out completion."""
        self._fade_animation.finished.disconnect()
        # Call the base class close event to actually close the dialog
        super().closeEvent(None)

    def accept(self) -> None:
        """Accept the dialog with animation."""
        self.done(QDialog.DialogCode.Accepted)

    def reject(self) -> None:
        """Reject the dialog with animation."""
        self.done(QDialog.DialogCode.Rejected)

    def done(self, result_code: int) -> None:
        """
        Override done to trigger close animation before closing.
        """
        # Store the result code
        self._result_code = result_code

        # If already closed or not visible, just call super
        if not self.isVisible():
            super().done(result_code)
            return

        # Start fade-out animation and then close
        self._fade_animation.setStartValue(1.0)
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.finished.connect(
            lambda: self._finish_done(self._result_code)
        )
        self._fade_animation.start()

    def _finish_done(self, result_code: int) -> None:
        """Finish the done operation after animation."""
        self._fade_animation.finished.disconnect()
        super().done(result_code)

    def set_animation_duration(self, duration: int) -> None:
        """Set the animation duration in milliseconds."""
        self._duration = duration
        self._fade_animation.setDuration(duration)
        self._slide_animation.setDuration(duration)

    def exec(self) -> int:
        """
        Execute the dialog modally and return the result code.
        """
        return super().exec()
