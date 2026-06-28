# utils/style.py
import logging
import os
import subprocess
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QProxyStyle, QStyle

logger = logging.getLogger(__name__)


class CustomProxyStyle(QProxyStyle):
    """Custom style for SpinBox arrows."""

    def drawPrimitive(self, element: QStyle.PrimitiveElement, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorSpinUp:
            rect = option.rect
            painter.save()
            if option.state & QStyle.StateFlag.State_MouseOver:
                painter.setBrush(QColor(74, 77, 83))
            else:
                painter.setBrush(QColor(61, 61, 64))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 3, 3)

            cx = rect.x() + rect.width() // 2
            cy = rect.y() + rect.height() // 2
            points = [
                cx - 5, cy + 2,
                cx + 5, cy + 2,
                cx, cy - 4
            ]
            painter.setBrush(QColor(239, 239, 239))
            painter.drawPolygon(points)
            painter.restore()
            return

        if element == QStyle.PrimitiveElement.PE_IndicatorSpinDown:
            rect = option.rect
            painter.save()
            if option.state & QStyle.StateFlag.State_MouseOver:
                painter.setBrush(QColor(74, 77, 83))
            else:
                painter.setBrush(QColor(61, 61, 64))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 3, 3)

            cx = rect.x() + rect.width() // 2
            cy = rect.y() + rect.height() // 2
            points = [
                cx - 5, cy - 2,
                cx + 5, cy - 2,
                cx, cy + 4
            ]
            painter.setBrush(QColor(239, 239, 239))
            painter.drawPolygon(points)
            painter.restore()
            return

        super().drawPrimitive(element, option, painter, widget)


def setup_style(app: QApplication) -> None:
    """
    Setup application style with automatic theme detection for all platforms.
    """
    is_dark = _detect_theme()

    if is_dark:
        _apply_dark_theme(app)
    else:
        _apply_light_theme(app)

    app.setStyle(CustomProxyStyle())


def _detect_theme() -> bool:
    """
    Detect system theme using Qt's style hints with fallbacks for all platforms.
    """
    # Try Qt 6.5+ styleHints().colorScheme()
    try:
        hints = QApplication.styleHints()
        if hints is not None:
            scheme = hints.colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return True
            if scheme == Qt.ColorScheme.Light:
                return False
    except AttributeError:
        pass

    # Fallback: check platform-specific settings
    return _detect_theme_fallback()


def _detect_theme_fallback() -> bool:
    """Fallback theme detection for various desktop environments."""
    # KDE
    try:
        result = subprocess.run(
            ['kreadconfig5', '--group', 'Colors:Window', '--key', 'BackgroundNormal'],
            capture_output=True, text=True, timeout=1
        )
        if result.stdout:
            color = result.stdout.strip()
            if color.startswith('#'):
                r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
                brightness = (r * 299 + g * 587 + b * 114) / 1000
                return brightness < 128
    except Exception:
        pass

    # GNOME/GTK
    try:
        result = subprocess.run(
            ['gsettings', 'get', 'org.gnome.desktop.interface', 'gtk-theme'],
            capture_output=True, text=True, timeout=1
        )
        if result.stdout:
            theme = result.stdout.strip().lower()
            if 'dark' in theme or 'dracula' in theme or 'adwaita-dark' in theme:
                return True
    except Exception:
        pass

    # XFCE
    try:
        result = subprocess.run(
            ['xfconf-query', '-c', 'xsettings', '-p', '/Net/ThemeName'],
            capture_output=True, text=True, timeout=1
        )
        if result.stdout:
            theme = result.stdout.strip().lower()
            if 'dark' in theme:
                return True
    except Exception:
        pass

    # Windows
    if sys.platform == 'win32':
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
            value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
            return value == 0
        except Exception:
            pass

    # macOS
    if sys.platform == 'darwin':
        try:
            result = subprocess.run(
                ['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                capture_output=True, text=True, timeout=1
            )
            if 'Dark' in result.stdout:
                return True
        except Exception:
            pass

    # Default to dark theme if detection fails
    return True


def _apply_dark_theme(app: QApplication) -> None:
    """Apply dark theme colors."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(43, 43, 46))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(239, 239, 239))
    palette.setColor(QPalette.ColorRole.Base, QColor(30, 30, 33))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(43, 43, 46))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(43, 43, 46))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(239, 239, 239))
    palette.setColor(QPalette.ColorRole.Text, QColor(239, 239, 239))
    palette.setColor(QPalette.ColorRole.Button, QColor(61, 61, 64))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(239, 239, 239))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(61, 174, 233))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    app.setStyleSheet("""
        QToolTip { background-color: #2d2d30; color: #efefef; border: 1px solid #3d4045; }
        QMenu { background-color: #2d2d30; color: #efefef; border: 1px solid #3d4045; }
        QMenu::item:selected { background-color: #3daee9; color: white; }
        QScrollBar:vertical { background: #2d2d30; width: 12px; }
        QScrollBar::handle:vertical { background: #3d4045; border-radius: 6px; }
        QScrollBar::handle:vertical:hover { background: #4a4d53; }
        QScrollBar:horizontal { background: #2d2d30; height: 12px; }
        QScrollBar::handle:horizontal { background: #3d4045; border-radius: 6px; }
        QScrollBar::handle:horizontal:hover { background: #4a4d53; }
        QHeaderView::section { background-color: #2d2d30; color: #efefef; padding: 6px; border: none; }
        QTableWidget { gridline-color: #3d4045; }
        QLineEdit, QTextEdit, QSpinBox, QComboBox {
            background-color: #1e1e20; color: #efefef;
            border: 1px solid #3d4045; border-radius: 4px; padding: 4px;
        }
        QGroupBox { color: #efefef; border: 1px solid #3d4045; border-radius: 6px; margin-top: 10px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        QPushButton { background-color: #3d4045; color: #efefef; border: none; border-radius: 4px; padding: 6px 12px; }
        QPushButton:hover { background-color: #4a4d53; }
        QPushButton:pressed { background-color: #2d2d30; }
        QDialog { background-color: #2d2d30; }
        QLabel { color: #efefef; }
        QTabWidget::pane { background-color: #2d2d30; border: 1px solid #3d4045; }
        QTabBar::tab { background-color: #3d4045; color: #efefef; padding: 6px 12px; }
        QTabBar::tab:selected { background-color: #4a4d53; }
        QTabBar::tab:hover { background-color: #4a4d53; }
    """)


def _apply_light_theme(app: QApplication) -> None:
    """Apply light theme colors."""
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.Base, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(240, 240, 240))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.Button, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(61, 174, 233))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)

    app.setStyleSheet("""
        QToolTip { background-color: #f0f0f0; color: #000000; border: 1px solid #cccccc; }
        QMenu { background-color: #f0f0f0; color: #000000; border: 1px solid #cccccc; }
        QMenu::item:selected { background-color: #3daee9; color: white; }
        QScrollBar:vertical { background: #f0f0f0; width: 12px; }
        QScrollBar::handle:vertical { background: #cccccc; border-radius: 6px; }
        QScrollBar::handle:vertical:hover { background: #aaaaaa; }
        QScrollBar:horizontal { background: #f0f0f0; height: 12px; }
        QScrollBar::handle:horizontal { background: #cccccc; border-radius: 6px; }
        QScrollBar::handle:horizontal:hover { background: #aaaaaa; }
        QHeaderView::section { background-color: #f0f0f0; color: #000000; padding: 6px; border: none; }
        QTableWidget { gridline-color: #cccccc; }
        QLineEdit, QTextEdit, QSpinBox, QComboBox {
            background-color: #ffffff; color: #000000;
            border: 1px solid #cccccc; border-radius: 4px; padding: 4px;
        }
        QGroupBox { color: #000000; border: 1px solid #cccccc; border-radius: 6px; margin-top: 10px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        QPushButton { background-color: #e0e0e0; color: #000000; border: none; border-radius: 4px; padding: 6px 12px; }
        QPushButton:hover { background-color: #d0d0d0; }
        QPushButton:pressed { background-color: #c0c0c0; }
        QDialog { background-color: #f0f0f0; }
        QLabel { color: #000000; }
        QTabWidget::pane { background-color: #f0f0f0; border: 1px solid #cccccc; }
        QTabBar::tab { background-color: #e0e0e0; color: #000000; padding: 6px 12px; }
        QTabBar::tab:selected { background-color: #d0d0d0; }
        QTabBar::tab:hover { background-color: #d0d0d0; }
    """)
