# ui/splash.py

import os
from PyQt6.QtWidgets import QWidget, QLabel, QProgressBar, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QColor, QPainter, QPainterPath


class SplashScreen(QWidget):
    """Frameless splash screen.

    Deliberately a plain QWidget, not QSplashScreen: on Qt 6.12
    ``QSplashScreen.show()`` costs ~1s per instance here (verified with both
    the offscreen and real platforms, independent of window type/flags), and
    that was the single biggest chunk of startup time. A QWidget draws the
    same pixmap in paintEvent and shows in ~1ms. Public API (``update_status``
    / ``close``) is unchanged so existing callers keep working.
    """

    def __init__(self, is_dark=True):
        super().__init__()
        if is_dark:
            bg_color = QColor(30, 30, 33)
            text_color = "#efeff1"
            sub_color = "#95a5a6"
            accent_color = "#e85d4c"
        else:
            bg_color = QColor(245, 245, 248)
            text_color = "#1e1e21"
            sub_color = "#6a6a70"
            accent_color = "#e85d4c"

        self.setWindowFlags(
            Qt.WindowType.SplashScreen | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedSize(480, 280)

        # Background pixmap, painted in paintEvent().
        self._bg = QPixmap(480, 280)
        self._bg.fill(bg_color)

        from utils.helpers import get_resource_path

        icon_pixmap = None

        icon_paths = [
            get_resource_path("logo/icon512.png"),
        ]

        for path in icon_paths:
            if os.path.exists(path):
                icon_pixmap = QPixmap(path)
                if not icon_pixmap.isNull():
                    break

        if icon_pixmap and not icon_pixmap.isNull():
            icon_size = 80

            scaled = icon_pixmap.scaled(
                icon_size,
                icon_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            circular = QPixmap(icon_size, icon_size)
            circular.fill(Qt.GlobalColor.transparent)

            painter = QPainter(circular)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            path = QPainterPath()
            path.addEllipse(0, 0, icon_size, icon_size)
            painter.setClipPath(path)

            painter.drawPixmap(0, 0, scaled)
            painter.end()

            painter = QPainter(self._bg)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            x = (480 - icon_size) // 2
            y = 25
            painter.drawPixmap(x, y, circular)
            painter.end()

        self.title = QLabel(self)
        self.title.setText("FelfelDM")
        self.title.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                font-size: 28px;
                font-weight: bold;
                background: transparent;
            }}
        """)
        self.title.setGeometry(140, 115, 200, 40)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.subtitle = QLabel(self)
        self.subtitle.setText("Download Manager")
        self.subtitle.setStyleSheet(f"""
            QLabel {{
                color: {sub_color};
                font-size: 13px;
                background: transparent;
                letter-spacing: 2px;
            }}
        """)
        self.subtitle.setGeometry(140, 155, 200, 25)
        self.subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status = QLabel(self)
        self.status.setText("Loading...")
        self.status.setStyleSheet(f"""
            QLabel {{
                color: {accent_color};
                font-size: 13px;
                background: transparent;
                font-weight: 500;
            }}
        """)
        self.status.setGeometry(50, 200, 380, 25)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.progress = QProgressBar(self)
        self.progress.setGeometry(60, 235, 360, 3)
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background-color: {'#3d4045' if is_dark else '#d0d0d5'};
                border-radius: 7px;
                    min-height: 18px;

            }}
            QProgressBar::chunk {{
                background-color: #e85d4c;
                border-radius: 7px;
            }}
        """)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)

        self.dot_count = 0
        self.dot_timer = QTimer(self)
        self.dot_timer.timeout.connect(self._update_dots)
        self.dot_timer.start(300)

        self.show()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._bg)
        painter.end()

    def _update_dots(self):
        dots = "." * (self.dot_count % 4)
        current_text = self.status.text().split(".")[0]
        self.status.setText(f"{current_text}{dots}")
        self.dot_count += 1

    def update_status(self, text, progress=0):
        self.status.setText(text)
        self.progress.setValue(progress)
        QApplication.processEvents()

    def close(self):
        self.dot_timer.stop()
        super().close()