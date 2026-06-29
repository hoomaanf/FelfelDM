# utils/style.py
"""
Simplified and robust styling for FelfelDM.
Uses a clean, stable stylesheet with support for dark/light themes.
"""

import subprocess
import sys
import logging
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette, QFont
from PyQt6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)


# =============================================================================
# Color Palettes
# =============================================================================

class ThemeColors:
    """Color palettes for dark and light themes."""

    # Dark theme (based on Persepolis style)
    DARK = {
        "bg_primary": "#1a1a2e",
        "bg_secondary": "#16213e",
        "bg_tertiary": "#2d2d44",
        "bg_hover": "#3d3d5c",
        "bg_active": "#4a4a6a",
        "text_primary": "#e0e0e0",
        "text_secondary": "#aaa",
        "text_disabled": "#666",
        "accent": "#e67e22",
        "accent_hover": "#f39c12",
        "accent_active": "#d35400",
        "border": "#2d2d44",
        "success": "#27ae60",
        "warning": "#f1c40f",
        "error": "#e74c3c",
    }

    # Light theme (clean and simple)
    LIGHT = {
        "bg_primary": "#f5f5f5",
        "bg_secondary": "#ffffff",
        "bg_tertiary": "#e8e8e8",
        "bg_hover": "#d5d5d5",
        "bg_active": "#c0c0c0",
        "text_primary": "#222",
        "text_secondary": "#555",
        "text_disabled": "#999",
        "accent": "#e67e22",
        "accent_hover": "#f39c12",
        "accent_active": "#d35400",
        "border": "#ccc",
        "success": "#27ae60",
        "warning": "#f1c40f",
        "error": "#e74c3c",
    }


def get_theme_colors(is_dark: bool) -> dict:
    """Return the color palette for the given theme."""
    return ThemeColors.DARK if is_dark else ThemeColors.LIGHT


# =============================================================================
# Stylesheet Builder
# =============================================================================

def build_stylesheet(is_dark: bool) -> str:
    """
    Build a clean, stable stylesheet.
    No glassmorphism or complex effects to avoid rendering issues.
    """
    c = get_theme_colors(is_dark)
    radius = "6px"

    return f"""
    /* Global */
    QWidget {{
        background-color: {c["bg_primary"]};
        color: {c["text_primary"]};
        selection-background-color: {c["accent"]};
        selection-color: white;
        font-family: "Vazir", "Segoe UI", system-ui, sans-serif;
        font-size: 13px;
    }}

    QMainWindow {{
        background-color: {c["bg_primary"]};
    }}

    /* Buttons */
    QPushButton {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {radius};
        padding: 6px 14px;
        min-height: 20px;
    }}
    QPushButton:hover {{
        background-color: {c["bg_hover"]};
        border-color: {c["accent"]};
    }}
    QPushButton:pressed {{
        background-color: {c["bg_active"]};
    }}
    QPushButton:disabled {{
        color: {c["text_disabled"]};
        background-color: {c["bg_tertiary"]};
    }}
    /* Primary accent button */
    QPushButton[primary="true"] {{
        background-color: {c["accent"]};
        color: white;
        border: none;
        font-weight: bold;
    }}
    QPushButton[primary="true"]:hover {{
        background-color: {c["accent_hover"]};
    }}
    QPushButton[primary="true"]:pressed {{
        background-color: {c["accent_active"]};
    }}

    /* Inputs */
    QLineEdit, QTextEdit, QSpinBox, QComboBox {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {radius};
        padding: 6px 10px;
        min-height: 20px;
    }}
    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border-color: {c["accent"]};
        outline: none;
    }}
    QLineEdit:disabled, QTextEdit:disabled {{
        color: {c["text_disabled"]};
        background-color: {c["bg_tertiary"]};
    }}

    /* Table */
    QTableView {{
        background-color: {c["bg_primary"]};
        alternate-background-color: {c["bg_secondary"]};
        gridline-color: {c["border"]};
        border: 1px solid {c["border"]};
        border-radius: {radius};
        padding: 4px;
    }}
    QTableView::item {{
        padding: 6px 10px;
    }}
    QTableView::item:selected {{
        background-color: {c["accent"]};
        color: white;
    }}
    QHeaderView::section {{
        background-color: {c["bg_secondary"]};
        color: {c["text_secondary"]};
        padding: 8px 12px;
        border: none;
        border-bottom: 1px solid {c["border"]};
        font-weight: bold;
        text-align: left;
    }}

    /* Progress Bar */
    QProgressBar {{
        border: none;
        border-radius: 4px;
        background-color: {c["bg_tertiary"]};
        height: 8px;
        text-align: center;
        color: {c["text_primary"]};
    }}
    QProgressBar::chunk {{
        border-radius: 4px;
        background-color: {c["accent"]};
    }}
    QProgressBar::chunk:complete {{
        background-color: {c["success"]};
    }}
    QProgressBar::chunk:error {{
        background-color: {c["error"]};
    }}
    QProgressBar::chunk:paused {{
        background-color: {c["warning"]};
    }}

    /* Toolbar */
    QToolBar {{
        background-color: {c["bg_secondary"]};
        border: none;
        border-bottom: 1px solid {c["border"]};
        padding: 4px 8px;
        spacing: 4px;
    }}
    QToolButton {{
        background-color: transparent;
        color: {c["text_primary"]};
        border: none;
        border-radius: {radius};
        padding: 4px 10px;
    }}
    QToolButton:hover {{
        background-color: {c["bg_hover"]};
    }}
    QToolButton:pressed {{
        background-color: {c["bg_active"]};
    }}
    QToolButton:checked {{
        background-color: {c["accent"]};
        color: white;
    }}

    /* Status Bar */
    QStatusBar {{
        background-color: {c["bg_secondary"]};
        color: {c["text_secondary"]};
        border-top: 1px solid {c["border"]};
        padding: 2px 8px;
    }}
    QStatusBar QLabel {{
        color: {c["text_secondary"]};
    }}

    /* Menus */
    QMenuBar {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        border-bottom: 1px solid {c["border"]};
    }}
    QMenuBar::item:selected {{
        background-color: {c["bg_hover"]};
    }}
    QMenu {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {radius};
        padding: 4px;
    }}
    QMenu::item:selected {{
        background-color: {c["accent"]};
        color: white;
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {c["border"]};
        margin: 4px 8px;
    }}

    /* Scrollbars */
    QScrollBar:vertical {{
        background-color: {c["bg_primary"]};
        width: 10px;
        border-radius: 5px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {c["bg_tertiary"]};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {c["accent"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background-color: {c["bg_primary"]};
        height: 10px;
        border-radius: 5px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {c["bg_tertiary"]};
        border-radius: 5px;
        min-width: 30px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {c["accent"]};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* Dialogs */
    QDialog {{
        background-color: {c["bg_primary"]};
    }}
    QDialog QPushButton {{
        min-width: 80px;
    }}

    /* Group Box */
    QGroupBox {{
        border: 1px solid {c["border"]};
        border-radius: {radius};
        margin-top: 10px;
        padding-top: 10px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 6px;
    }}

    /* Tabs */
    QTabWidget::pane {{
        border: 1px solid {c["border"]};
        border-radius: {radius};
        background-color: {c["bg_primary"]};
    }}
    QTabBar::tab {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        padding: 6px 16px;
        border: 1px solid {c["border"]};
        border-bottom: none;
        border-top-left-radius: {radius};
        border-top-right-radius: {radius};
    }}
    QTabBar::tab:selected {{
        background-color: {c["bg_primary"]};
        border-bottom: 1px solid {c["bg_primary"]};
    }}
    QTabBar::tab:hover {{
        background-color: {c["bg_hover"]};
    }}

    /* Tooltips */
    QToolTip {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {radius};
        padding: 4px 8px;
    }}
    """


# =============================================================================
# Theme Application
# =============================================================================

def build_palette(is_dark: bool) -> QPalette:
    """Build a QPalette from the theme colors."""
    c = get_theme_colors(is_dark)

    def qcolor(hex_code: str) -> QColor:
        return QColor(hex_code)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, qcolor(c["bg_primary"]))
    palette.setColor(QPalette.ColorRole.WindowText, qcolor(c["text_primary"]))
    palette.setColor(QPalette.ColorRole.Base, qcolor(c["bg_secondary"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, qcolor(c["bg_tertiary"]))
    palette.setColor(QPalette.ColorRole.Text, qcolor(c["text_primary"]))
    palette.setColor(QPalette.ColorRole.Button, qcolor(c["bg_secondary"]))
    palette.setColor(QPalette.ColorRole.ButtonText, qcolor(c["text_primary"]))
    palette.setColor(QPalette.ColorRole.BrightText, qcolor(c["error"]))
    palette.setColor(QPalette.ColorRole.Highlight, qcolor(c["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, qcolor(c["bg_secondary"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, qcolor(c["text_primary"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, qcolor(c["text_disabled"]))

    return palette


def apply_theme(target, is_dark: bool) -> None:
    """
    Apply the theme to a QApplication or QWidget.
    Wrapped in try/except to prevent crashes.
    """
    try:
        palette = build_palette(is_dark)
        stylesheet = build_stylesheet(is_dark)

        if isinstance(target, QApplication):
            target.setPalette(palette)
            target.setStyleSheet(stylesheet)
            target.processEvents()
        else:
            target.setPalette(palette)
            target.setStyleSheet(stylesheet)

        logger.info("Theme applied: %s", "Dark" if is_dark else "Light")
    except Exception as e:
        logger.error("Failed to apply theme: %s", e)


def detect_theme() -> bool:
    """
    Detect system theme with fallbacks.
    Returns True for dark, False for light.
    """
    try:
        app = QApplication.instance()
        if app:
            # Try Qt 6.5+ style hints
            try:
                hints = app.styleHints()
                if hints is not None:
                    scheme = hints.colorScheme()
                    if scheme == Qt.ColorScheme.Dark:
                        return True
                    if scheme == Qt.ColorScheme.Light:
                        return False
            except AttributeError:
                pass
    except Exception:
        pass

    # Fallback: KDE
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

    # Fallback: GNOME/GTK
    try:
        result = subprocess.run(
            ['gsettings', 'get', 'org.gnome.desktop.interface', 'gtk-theme'],
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.stdout:
            theme = result.stdout.strip().lower()
            if 'dark' in theme or 'dracula' in theme:
                return True
            if 'light' in theme or 'adwaita' in theme:
                return False
    except Exception:
        pass

    # Fallback: XFCE
    try:
        result = subprocess.run(
            ['xfconf-query', '-c', 'xsettings', '-p', '/Net/ThemeName'],
            capture_output=True,
            text=True,
            timeout=1
        )
        if result.stdout and 'dark' in result.stdout.strip().lower():
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
            return value == 0  # 0 = dark
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

    # Default to dark if detection fails
    return True


# =============================================================================
# Compatibility layer (for older code)
# =============================================================================

def setup_style(app: QApplication) -> None:
    """Legacy function to set up application style."""
    is_dark = detect_theme()
    apply_theme(app, is_dark)


def apply_modern_theme(target, is_dark: bool) -> None:
    """Alias for apply_theme."""
    apply_theme(target, is_dark)
