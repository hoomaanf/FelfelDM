# utils/style.py
"""
Style utilities for FelfelDM with automatic theme detection.
"""

import logging
import os
import subprocess
import sys
from typing import Optional

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
            points = [cx - 5, cy + 2, cx + 5, cy + 2, cx, cy - 4]
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
            points = [cx - 5, cy - 2, cx + 5, cy - 2, cx, cy + 4]
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
    Defaults to dark theme if detection fails.
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
    """
    Fallback theme detection for various desktop environments.
    Defaults to dark theme if detection fails.
    """
    # KDE
    try:
        result = subprocess.run(
            ['kreadconfig5', '--group', 'Colors:Window', '--key', 'BackgroundNormal'],
            capture_output=True,
            text=True,
            timeout=1
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
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.stdout:
            theme = result.stdout.strip().lower()
            if 'dark' in theme or 'dracula' in theme or 'adwaita-dark' in theme:
                return True
            if 'light' in theme or 'adwaita' in theme:
                return False
    except Exception:
        pass

    # XFCE
    try:
        result = subprocess.run(
            ['xfconf-query', '-c', 'xsettings', '-p', '/Net/ThemeName'],
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.stdout:
            theme = result.stdout.strip().lower()
            if 'dark' in theme:
                return True
    except Exception:
        pass

    # Cinnamon
    try:
        result = subprocess.run(
            ['gsettings', 'get', 'org.cinnamon.theme', 'name'],
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.stdout:
            theme = result.stdout.strip().lower()
            if 'dark' in theme:
                return True
    except Exception:
        pass

    # MATE
    try:
        result = subprocess.run(
            ['gsettings', 'get', 'org.mate.interface', 'gtk-theme'],
            capture_output=True,
            text=True,
            timeout=1
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
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
            value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
            return value == 0
        except Exception:
            pass

    # macOS
    if sys.platform == 'darwin':
        try:
            result = subprocess.run(
                ['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.stdout and 'Dark' in result.stdout:
                return True
        except Exception:
            pass

    # Default to dark theme
    return True


def _apply_dark_theme(app: QApplication) -> None:
    """Apply dark theme."""
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
    dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.black)
    dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
    app.setPalette(dark_palette)

    # Dark stylesheet
    app.setStyleSheet("""
        QMainWindow { background-color: #2b2b2b; }
        QWidget { background-color: #2b2b2b; color: #ffffff; }
        QTableView { background-color: #1e1e1e; alternate-background-color: #2b2b2b; gridline-color: #3a3a3a; }
        QHeaderView::section { background-color: #3a3a3a; color: #ffffff; padding: 4px; border: 1px solid #4a4a4a; }
        QTableView::item:selected { background-color: #4a6a9a; }
        QPushButton { background-color: #3a3a3a; color: #ffffff; border: 1px solid #4a4a4a; padding: 5px 10px; border-radius: 3px; }
        QPushButton:hover { background-color: #4a4a4a; }
        QPushButton:pressed { background-color: #2a2a2a; }
        QLineEdit, QTextEdit, QSpinBox, QComboBox { background-color: #1e1e1e; color: #ffffff; border: 1px solid #4a4a4a; padding: 3px; }
        QGroupBox { border: 1px solid #4a4a4a; border-radius: 5px; margin-top: 10px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        QTabWidget::pane { border: 1px solid #4a4a4a; background-color: #2b2b2b; }
        QTabBar::tab { background-color: #3a3a3a; color: #ffffff; padding: 5px 10px; }
        QTabBar::tab:selected { background-color: #4a6a9a; }
        QMenuBar { background-color: #2b2b2b; color: #ffffff; }
        QMenuBar::item:selected { background-color: #4a6a9a; }
        QMenu { background-color: #2b2b2b; color: #ffffff; }
        QMenu::item:selected { background-color: #4a6a9a; }
        QToolBar { background-color: #2b2b2b; border: none; spacing: 3px; }
        QStatusBar { background-color: #2b2b2b; color: #aaaaaa; }
        QDialog { background-color: #2b2b2b; }
        QProgressBar { border: 1px solid #4a4a4a; border-radius: 3px; text-align: center; }
        QProgressBar::chunk { background-color: #4a6a9a; }
        QScrollBar:vertical { background-color: #2b2b2b; width: 12px; }
        QScrollBar::handle:vertical { background-color: #4a4a4a; border-radius: 6px; min-height: 20px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        QScrollBar:horizontal { background-color: #2b2b2b; height: 12px; }
        QScrollBar::handle:horizontal { background-color: #4a4a4a; border-radius: 6px; min-width: 20px; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        QCheckBox { color: #ffffff; }
        QRadioButton { color: #ffffff; }
        QLabel { color: #ffffff; }
    """)


def _apply_light_theme(app: QApplication) -> None:
    """Apply light theme."""
    light_palette = QPalette()
    light_palette.setColor(QPalette.ColorRole.Window, QColor(240, 240, 240))
    light_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.black)
    light_palette.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.white)
    light_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(245, 245, 245))
    light_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    light_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.black)
    light_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.black)
    light_palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
    light_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.black)
    light_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    light_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    light_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    light_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    app.setPalette(light_palette)

    # Light stylesheet
    app.setStyleSheet("""
        QMainWindow { background-color: #f0f0f0; }
        QWidget { background-color: #f0f0f0; color: #000000; }
        QTableView { background-color: #ffffff; alternate-background-color: #f5f5f5; gridline-color: #d0d0d0; }
        QHeaderView::section { background-color: #e0e0e0; color: #000000; padding: 4px; border: 1px solid #d0d0d0; }
        QTableView::item:selected { background-color: #4a6a9a; color: #ffffff; }
        QPushButton { background-color: #e0e0e0; color: #000000; border: 1px solid #d0d0d0; padding: 5px 10px; border-radius: 3px; }
        QPushButton:hover { background-color: #d0d0d0; }
        QPushButton:pressed { background-color: #c0c0c0; }
        QLineEdit, QTextEdit, QSpinBox, QComboBox { background-color: #ffffff; color: #000000; border: 1px solid #d0d0d0; padding: 3px; }
        QGroupBox { border: 1px solid #d0d0d0; border-radius: 5px; margin-top: 10px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
        QTabWidget::pane { border: 1px solid #d0d0d0; background-color: #f0f0f0; }
        QTabBar::tab { background-color: #e0e0e0; color: #000000; padding: 5px 10px; }
        QTabBar::tab:selected { background-color: #4a6a9a; color: #ffffff; }
        QMenuBar { background-color: #f0f0f0; color: #000000; }
        QMenuBar::item:selected { background-color: #4a6a9a; color: #ffffff; }
        QMenu { background-color: #f0f0f0; color: #000000; }
        QMenu::item:selected { background-color: #4a6a9a; color: #ffffff; }
        QToolBar { background-color: #f0f0f0; border: none; spacing: 3px; }
        QStatusBar { background-color: #f0f0f0; color: #666666; }
        QDialog { background-color: #f0f0f0; }
        QProgressBar { border: 1px solid #d0d0d0; border-radius: 3px; text-align: center; }
        QProgressBar::chunk { background-color: #4a6a9a; }
        QScrollBar:vertical { background-color: #f0f0f0; width: 12px; }
        QScrollBar::handle:vertical { background-color: #d0d0d0; border-radius: 6px; min-height: 20px; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        QScrollBar:horizontal { background-color: #f0f0f0; height: 12px; }
        QScrollBar::handle:horizontal { background-color: #d0d0d0; border-radius: 6px; min-width: 20px; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
        QCheckBox { color: #000000; }
        QRadioButton { color: #000000; }
        QLabel { color: #000000; }
    """)
