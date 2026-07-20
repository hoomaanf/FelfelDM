# ui/splash.py

import os
from PyQt6.QtWidgets import QSplashScreen, QLabel, QProgressBar, QApplication
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QColor, QPainter, QPainterPath


class SplashScreen(QSplashScreen):
    def __init__(self, is_dark=True):
        if is_dark:
            bg_color = QColor(30, 30, 33)
            bg_style = "#1e1e20"
            text_color = "#efeff1"
            sub_color = "#95a5a6"
            accent_color = "#3daee9"
        else:
            bg_color = QColor(245, 245, 248)
            bg_style = "#f5f5f8"
            text_color = "#1e1e21"
            sub_color = "#6a6a70"
            accent_color = "#3daee9"

        pixmap = QPixmap(480, 280)
        pixmap.fill(bg_color)

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

            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            x = (480 - icon_size) // 2
            y = 25
            painter.drawPixmap(x, y, circular)
            painter.end()

        super().__init__(pixmap)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )

        self.setStyleSheet(f"""
            QSplashScreen {{
                background-color: {bg_style};
                border-radius: 16px;
            }}
        """)

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
                border-radius: 2px;
                height: 3px;
            }}
            QProgressBar::chunk {{
                background-color: #3daee9;
                border-radius: 2px;
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
