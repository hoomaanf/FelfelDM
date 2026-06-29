# utils/style.py
"""
Modern stylesheet and theme utilities for FelfelDM.
Uses a clean, flat design with minimal decorations.
"""

import sys
import subprocess
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QStyle


# =============================================================================
# Modern Color Palettes
# =============================================================================

class ThemeColors:
    """Modern color palette with dark and light variants."""

    # Dark theme
    DARK = {
        "bg_primary": "#1e1e2e",
        "bg_secondary": "#28283a",
        "bg_tertiary": "#313144",
        "bg_hover": "#3b3b52",
        "bg_active": "#45456a",
        "text_primary": "#cdd6f4",
        "text_secondary": "#a6adc8",
        "text_disabled": "#6c7086",
        "accent": "#89b4fa",
        "accent_hover": "#74c7ec",
        "accent_active": "#7f95d1",
        "border": "#45456a",
        "success": "#a6e3a1",
        "warning": "#f9e2af",
        "error": "#f38ba8",
    }

    # Light theme
    LIGHT = {
        "bg_primary": "#eff1f5",
        "bg_secondary": "#e6e9ef",
        "bg_tertiary": "#dce0e8",
        "bg_hover": "#ccd0da",
        "bg_active": "#bcc0cc",
        "text_primary": "#4c4f69",
        "text_secondary": "#6c6f85",
        "text_disabled": "#9ca0b0",
        "accent": "#7287fd",
        "accent_hover": "#5c7af0",
        "accent_active": "#4c6ad6",
        "border": "#ccd0da",
        "success": "#40a02b",
        "warning": "#df8e1d",
        "error": "#d20f39",
    }


def get_theme_colors(is_dark: bool):
    """Return the appropriate color palette."""
    return ThemeColors.DARK if is_dark else ThemeColors.LIGHT


# =============================================================================
# Style Sheet (clean and simple)
# =============================================================================

def build_stylesheet(is_dark: bool) -> str:
    """
    Build a clean, simple stylesheet without glassmorphism or gradients.

    Args:
        is_dark: True for dark theme, False for light theme

    Returns:
        A string containing the complete QSS stylesheet.
    """
    c = get_theme_colors(is_dark)
    border_radius = "8px"
    font_family = "sans-serif"

    return f"""
    /* ============================================================
       Global
       ============================================================ */
    * {{
        font-family: "{font_family}";
        font-size: 13px;
        outline: none;
    }}

    QWidget {{
        background-color: {c["bg_primary"]};
        color: {c["text_primary"]};
        selection-background-color: {c["accent"]};
        selection-color: {c["bg_primary"]};
    }}

    QMainWindow {{
        background-color: {c["bg_primary"]};
    }}

    /* ============================================================
       Buttons
       ============================================================ */
    QPushButton {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        padding: 6px 12px;
        font-weight: 500;
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
        border-color: {c["border"]};
    }}

    /* Primary accent button */
    QPushButton[primary="true"] {{
        background-color: {c["accent"]};
        color: {c["bg_primary"]};
        border: none;
        font-weight: 600;
    }}
    QPushButton[primary="true"]:hover {{
        background-color: {c["accent_hover"]};
    }}
    QPushButton[primary="true"]:pressed {{
        background-color: {c["accent_active"]};
    }}

    /* Danger button */
    QPushButton[danger="true"] {{
        background-color: {c["error"]};
        color: {c["bg_primary"]};
        border: none;
    }}
    QPushButton[danger="true"]:hover {{
        background-color: #c0392b;
    }}

    /* ============================================================
       Toolbar
       ============================================================ */
    QToolBar {{
        background-color: {c["bg_secondary"]};
        border: none;
        border-bottom: 1px solid {c["border"]};
        padding: 4px 8px;
        spacing: 4px;
    }}
    QToolBar::separator {{
        width: 1px;
        background-color: {c["border"]};
        margin: 4px 6px;
    }}
    QToolButton {{
        background: transparent;
        border: none;
        border-radius: {border_radius};
        padding: 4px 8px;
    }}
    QToolButton:hover {{
        background-color: {c["bg_hover"]};
    }}
    QToolButton:pressed {{
        background-color: {c["bg_active"]};
    }}
    QToolButton:checked {{
        background-color: {c["accent"]};
        color: {c["bg_primary"]};
    }}

    /* ============================================================
       Menu Bar
       ============================================================ */
    QMenuBar {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        border-bottom: 1px solid {c["border"]};
        padding: 2px 8px;
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 4px 10px;
        border-radius: {border_radius};
    }}
    QMenuBar::item:selected {{
        background-color: {c["bg_hover"]};
    }}
    QMenuBar::item:pressed {{
        background-color: {c["accent"]};
        color: {c["bg_primary"]};
    }}

    QMenu {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        padding: 4px 0;
    }}
    QMenu::item {{
        padding: 6px 30px 6px 18px;
        border-radius: 4px;
        margin: 2px 4px;
    }}
    QMenu::item:selected {{
        background-color: {c["bg_hover"]};
    }}
    QMenu::separator {{
        height: 1px;
        background-color: {c["border"]};
        margin: 4px 8px;
    }}

    /* ============================================================
       Table View (Downloads)
       ============================================================ */
    QTableView {{
        background-color: {c["bg_primary"]};
        alternate-background-color: {c["bg_secondary"]};
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        gridline-color: {c["border"]};
        padding: 2px;
    }}
    QTableView::item {{
        padding: 6px 8px;
        border: none;
        border-radius: 4px;
    }}
    QTableView::item:selected {{
        background-color: {c["accent"]};
        color: {c["bg_primary"]};
    }}
    QTableView::item:hover:!selected {{
        background-color: {c["bg_hover"]};
    }}
    QHeaderView::section {{
        background-color: {c["bg_secondary"]};
        color: {c["text_secondary"]};
        padding: 6px 10px;
        border: none;
        border-bottom: 1px solid {c["border"]};
        font-weight: 600;
        text-align: left;
    }}
    QHeaderView::section:checked {{
        background-color: {c["accent"]};
        color: {c["bg_primary"]};
    }}

    /* ============================================================
       Scroll Bars
       ============================================================ */
    QScrollBar:vertical {{
        background-color: {c["bg_primary"]};
        width: 10px;
        margin: 0px;
        border-radius: 5px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {c["bg_tertiary"]};
        border-radius: 5px;
        min-height: 20px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {c["bg_hover"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background-color: {c["bg_primary"]};
        height: 10px;
        margin: 0px;
        border-radius: 5px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {c["bg_tertiary"]};
        border-radius: 5px;
        min-width: 20px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {c["bg_hover"]};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* ============================================================
       ComboBox
       ============================================================ */
    QComboBox {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        padding: 4px 10px;
        min-height: 24px;
    }}
    QComboBox:hover {{
        border-color: {c["accent"]};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 20px;
    }}
    QComboBox::down-arrow {{
        image: url(:/icons/down-arrow.svg);
        width: 10px;
        height: 10px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        selection-background-color: {c["bg_hover"]};
        padding: 4px;
    }}

    /* ============================================================
       LineEdit & TextEdit
       ============================================================ */
    QLineEdit, QTextEdit {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        padding: 6px 10px;
    }}
    QLineEdit:focus, QTextEdit:focus {{
        border-color: {c["accent"]};
    }}
    QLineEdit:disabled, QTextEdit:disabled {{
        color: {c["text_disabled"]};
        background-color: {c["bg_tertiary"]};
    }}

    /* ============================================================
       SpinBox
       ============================================================ */
    QSpinBox {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        padding: 4px 8px;
    }}
    QSpinBox:focus {{
        border-color: {c["accent"]};
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        background-color: {c["bg_tertiary"]};
        border: none;
        border-radius: 3px;
        width: 16px;
        margin: 1px;
    }}
    QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
        background-color: {c["bg_hover"]};
    }}

    /* ============================================================
       CheckBox & RadioButton
       ============================================================ */
    QCheckBox {{
        spacing: 8px;
        color: {c["text_primary"]};
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 2px solid {c["border"]};
        background: {c["bg_secondary"]};
    }}
    QCheckBox::indicator:checked {{
        background: {c["accent"]};
        border-color: {c["accent"]};
    }}
    QCheckBox::indicator:unchecked:hover {{
        border-color: {c["accent"]};
    }}

    QRadioButton {{
        spacing: 8px;
        color: {c["text_primary"]};
    }}
    QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 8px;
        border: 2px solid {c["border"]};
        background: {c["bg_secondary"]};
    }}
    QRadioButton::indicator:checked {{
        background: {c["accent"]};
        border-color: {c["accent"]};
    }}

    /* ============================================================
       GroupBox
       ============================================================ */
    QGroupBox {{
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        margin-top: 14px;
        padding-top: 6px;
        background-color: {c["bg_primary"]};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 8px;
        color: {c["text_secondary"]};
        font-weight: 600;
    }}

    /* ============================================================
       TabWidget
       ============================================================ */
    QTabWidget::pane {{
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        background-color: {c["bg_primary"]};
        padding: 4px;
    }}
    QTabBar::tab {{
        background-color: {c["bg_secondary"]};
        color: {c["text_secondary"]};
        padding: 6px 14px;
        margin-right: 2px;
        border-top-left-radius: {border_radius};
        border-top-right-radius: {border_radius};
    }}
    QTabBar::tab:selected {{
        background-color: {c["accent"]};
        color: {c["bg_primary"]};
    }}
    QTabBar::tab:hover:!selected {{
        background-color: {c["bg_hover"]};
        color: {c["text_primary"]};
    }}

    /* ============================================================
       Progress Bar
       ============================================================ */
    QProgressBar {{
        border: none;
        border-radius: 4px;
        background-color: {c["bg_tertiary"]};
        height: 6px;
        text-align: center;
        color: {c["text_primary"]};
        font-size: 11px;
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

    /* ============================================================
       Status Bar
       ============================================================ */
    QStatusBar {{
        background-color: {c["bg_secondary"]};
        color: {c["text_secondary"]};
        padding: 2px 10px;
        border-top: 1px solid {c["border"]};
    }}
    QStatusBar QLabel {{
        color: {c["text_secondary"]};
    }}

    /* ============================================================
       ToolTips
       ============================================================ */
    QToolTip {{
        background-color: {c["bg_secondary"]};
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        padding: 4px 8px;
        font-size: 12px;
    }}

    /* ============================================================
       Splitters
       ============================================================ */
    QSplitter::handle {{
        background-color: {c["border"]};
        margin: 2px;
    }}
    QSplitter::handle:hover {{
        background-color: {c["accent"]};
    }}

    /* ============================================================
       ListWidget
       ============================================================ */
    QListWidget {{
        background-color: {c["bg_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        padding: 4px;
    }}
    QListWidget::item {{
        padding: 4px 8px;
        border-radius: 4px;
    }}
    QListWidget::item:selected {{
        background-color: {c["accent"]};
        color: {c["bg_primary"]};
    }}
    QListWidget::item:hover:!selected {{
        background-color: {c["bg_hover"]};
    }}
    """


# =============================================================================
# Theme Application
# =============================================================================

def apply_modern_theme(target, is_dark: bool) -> None:
    """
    Apply the modern theme to the application.

    Args:
        target: QApplication instance
        is_dark: True for dark theme, False for light theme
    """
    app = QApplication.instance()
    if app is None:
        return

    # Build palette and stylesheet
    palette = build_palette(is_dark)
    stylesheet = build_stylesheet(is_dark)

    # Apply to application
    app.setPalette(palette)
    app.setStyleSheet(stylesheet)


def build_palette(is_dark: bool) -> QPalette:
    """Build a QPalette with modern colors."""
    c = get_theme_colors(is_dark)

    def qcolor(hex_code):
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
    palette.setColor(QPalette.ColorRole.HighlightedText, qcolor(c["bg_primary"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, qcolor(c["bg_secondary"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, qcolor(c["text_primary"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, qcolor(c["text_disabled"]))

    return palette


def detect_theme() -> bool:
    """Detect system theme with fallbacks. Defaults to dark if detection fails."""
    app = QApplication.instance()
    if not app:
        return True

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

    return _detect_theme_fallback()


def _detect_theme_fallback() -> bool:
    """Fallback theme detection for various desktop environments."""
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
                capture_output=True,
                text=True,
                timeout=1
            )
            if result.stdout and 'Dark' in result.stdout:
                return True
        except Exception:
            pass

    return True


# Backward compatibility
def setup_style(app: QApplication) -> None:
    """Legacy function - use apply_modern_theme instead."""
    is_dark = detect_theme()
    apply_modern_theme(app, is_dark)


def apply_theme(target, is_dark: bool) -> None:
    """Alias for apply_modern_theme."""
    apply_modern_theme(target, is_dark)
