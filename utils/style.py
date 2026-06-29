# utils/style.py
"""
Modern stylesheet and theme utilities for FelfelDM.
Uses a sleek, flat design with subtle shadows, glassmorphism, and smooth transitions.
"""

import sys
import subprocess
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QProxyStyle, QStyle, QWidget

# =============================================================================
# Modern Color Palettes
# =============================================================================

class ThemeColors:
    """Modern color palette with dark and light variants."""

    # Dark theme (inspired by Nord & Catppuccin with glassmorphism)
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
        "shadow": "rgba(0,0,0,0.6)",
        "glass_bg": "rgba(30, 30, 46, 0.85)",
        "glass_border": "rgba(255, 255, 255, 0.08)",
    }

    # Light theme (inspired by Catppuccin Latte)
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
        "shadow": "rgba(0,0,0,0.15)",
        "glass_bg": "rgba(239, 241, 245, 0.85)",
        "glass_border": "rgba(0, 0, 0, 0.06)",
    }


def get_theme_colors(is_dark: bool):
    """Return the appropriate color palette."""
    return ThemeColors.DARK if is_dark else ThemeColors.LIGHT


# =============================================================================
# Modern Style Sheet with Glassmorphism
# =============================================================================

def build_stylesheet(is_dark: bool) -> str:
    """
    Build a complete modern stylesheet with glassmorphism and CSS variables.

    Args:
        is_dark: True for dark theme, False for light theme

    Returns:
        A string containing the complete QSS stylesheet.
    """
    c = get_theme_colors(is_dark)
    border_radius = "12px"
    font_family = "Inter, 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif"

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
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {c["bg_primary"]},
            stop:1 {c["bg_secondary"]});
    }}

    /* ============================================================
       Glassmorphism Dialog Container
       ============================================================ */
    QFrame#animatedDialogContainer {{
        background: {c["glass_bg"]};
        border: 1px solid {c["glass_border"]};
        border-radius: 16px;
        backdrop-filter: blur(20px);
    }}

    QDialog {{
        background: transparent;
    }}

    /* ============================================================
       Buttons with gradient
       ============================================================ */
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["bg_secondary"]},
            stop:1 {c["bg_tertiary"]});
        color: {c["text_primary"]};
        border: none;
        border-radius: {border_radius};
        padding: 8px 16px;
        font-weight: 500;
        transition: all 0.2s ease;
    }}
    QPushButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["bg_hover"]},
            stop:1 {c["bg_secondary"]});
        transform: translateY(-1px);
    }}
    QPushButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["bg_active"]},
            stop:1 {c["bg_hover"]});
        transform: translateY(0px);
    }}
    QPushButton:disabled {{
        color: {c["text_disabled"]};
        background: {c["bg_tertiary"]};
    }}

    /* Primary accent button */
    QPushButton[primary="true"] {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["accent"]},
            stop:1 {c["accent_hover"]});
        color: {c["bg_primary"]};
        font-weight: 600;
    }}
    QPushButton[primary="true"]:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["accent_hover"]},
            stop:1 {c["accent"]});
    }}
    QPushButton[primary="true"]:pressed {{
        background: {c["accent_active"]};
    }}

    /* Danger button */
    QPushButton[danger="true"] {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["error"]},
            stop:1 #c0392b);
        color: {c["bg_primary"]};
    }}
    QPushButton[danger="true"]:hover {{
        opacity: 0.9;
    }}

    /* ============================================================
       Toolbar with gradient and glass effect
       ============================================================ */
    QToolBar {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["glass_bg"]},
            stop:1 {c["bg_secondary"]});
        border: none;
        border-bottom: 1px solid {c["glass_border"]};
        padding: 6px 12px;
        spacing: 6px;
        backdrop-filter: blur(10px);
    }}
    QToolBar::separator {{
        width: 1px;
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 transparent,
            stop:0.5 {c["border"]},
            stop:1 transparent);
        margin: 6px 4px;
    }}
    QToolButton {{
        background: transparent;
        border: none;
        border-radius: {border_radius};
        padding: 6px 12px;
        transition: all 0.15s ease;
    }}
    QToolButton:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["bg_hover"]},
            stop:1 {c["bg_secondary"]});
    }}
    QToolButton:pressed {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["bg_active"]},
            stop:1 {c["bg_hover"]});
    }}
    QToolButton:checked {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["accent"]},
            stop:1 {c["accent_hover"]});
        color: {c["bg_primary"]};
    }}

    /* ============================================================
       Table View with glass effect
       ============================================================ */
    QTableView {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["bg_primary"]},
            stop:1 {c["bg_secondary"]});
        alternate-background-color: {c["bg_tertiary"]};
        border: none;
        border-radius: {border_radius};
        gridline-color: {c["border"]};
        padding: 4px;
    }}
    QTableView::item {{
        padding: 8px 12px;
        border: none;
        border-radius: 6px;
        transition: all 0.15s ease;
    }}
    QTableView::item:selected {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["accent"]},
            stop:1 {c["accent_hover"]});
        color: {c["bg_primary"]};
    }}
    QTableView::item:hover:!selected {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["bg_hover"]},
            stop:1 {c["bg_secondary"]});
    }}
    QHeaderView::section {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["bg_secondary"]},
            stop:1 {c["bg_tertiary"]});
        color: {c["text_secondary"]};
        padding: 10px 14px;
        border: none;
        border-bottom: 1px solid {c["border"]};
        font-weight: 600;
        text-align: left;
    }}
    QHeaderView::section:checked {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["accent"]},
            stop:1 {c["accent_hover"]});
        color: {c["bg_primary"]};
    }}

    /* ============================================================
       Scroll Bars with glass effect
       ============================================================ */
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 0px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["bg_tertiary"]},
            stop:1 {c["bg_hover"]});
        border-radius: 4px;
        min-height: 20px;
        transition: all 0.15s ease;
    }}
    QScrollBar::handle:vertical:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["bg_hover"]},
            stop:1 {c["bg_active"]});
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    /* ============================================================
       ComboBox with glass effect
       ============================================================ */
    QComboBox {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["bg_secondary"]},
            stop:1 {c["bg_tertiary"]});
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        padding: 6px 12px;
        min-height: 24px;
        transition: all 0.15s ease;
    }}
    QComboBox:hover {{
        border-color: {c["accent"]};
        box-shadow: 0 0 0 2px {c["accent"]}40;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox::down-arrow {{
        image: url(:/icons/down-arrow.svg);
        width: 12px;
        height: 12px;
        margin-right: 4px;
    }}
    QComboBox QAbstractItemView {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["bg_secondary"]},
            stop:1 {c["bg_tertiary"]});
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        selection-background-color: {c["bg_hover"]};
        padding: 4px;
    }}

    /* ============================================================
       LineEdit & TextEdit with glass effect
       ============================================================ */
    QLineEdit, QTextEdit {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["bg_secondary"]},
            stop:1 {c["bg_tertiary"]});
        color: {c["text_primary"]};
        border: 1px solid {c["border"]};
        border-radius: {border_radius};
        padding: 8px 12px;
        transition: all 0.15s ease;
    }}
    QLineEdit:focus, QTextEdit:focus {{
        border-color: {c["accent"]};
        box-shadow: 0 0 0 2px {c["accent"]}40;
    }}
    QLineEdit:disabled, QTextEdit:disabled {{
        color: {c["text_disabled"]};
        background: {c["bg_tertiary"]};
    }}

    /* ============================================================
       Progress Bar with glow effect
       ============================================================ */
    QProgressBar {{
        border: none;
        border-radius: 6px;
        background: {c["bg_tertiary"]};
        height: 8px;
        text-align: center;
        color: {c["text_primary"]};
        font-size: 11px;
    }}
    QProgressBar::chunk {{
        border-radius: 6px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["accent"]},
            stop:1 {c["accent_hover"]});
        transition: width 0.3s ease;
    }}
    QProgressBar::chunk:complete {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["success"]},
            stop:1 #2ecc71);
    }}
    QProgressBar::chunk:error {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["error"]},
            stop:1 #c0392b);
    }}
    QProgressBar::chunk:paused {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {c["warning"]},
            stop:1 #f39c12);
    }}

    /* ============================================================
       Status Bar
       ============================================================ */
    QStatusBar {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 {c["bg_secondary"]},
            stop:1 {c["bg_tertiary"]});
        color: {c["text_secondary"]};
        padding: 4px 12px;
        border-top: 1px solid {c["border"]};
    }}
    QStatusBar QLabel {{
        color: {c["text_secondary"]};
    }}

    /* ============================================================
       ToolTips with glass effect
       ============================================================ */
    QToolTip {{
        background: {c["glass_bg"]};
        color: {c["text_primary"]};
        border: 1px solid {c["glass_border"]};
        border-radius: {border_radius};
        padding: 6px 12px;
        font-size: 12px;
        backdrop-filter: blur(10px);
    }}
    """


# =============================================================================
# Custom Proxy Style
# =============================================================================

class ModernProxyStyle(QProxyStyle):
    """Custom QProxyStyle with modern touches."""

    def drawPrimitive(self, element: QStyle.PrimitiveElement, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorSpinUp:
            rect = option.rect
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)

            is_dark = self._is_dark_theme()
            c = get_theme_colors(is_dark)

            bg = QColor(c["bg_tertiary"])
            if option.state & QStyle.StateFlag.State_MouseOver:
                bg = QColor(c["bg_hover"])
            painter.setBrush(bg)

            painter.drawRoundedRect(rect, 4, 4)

            painter.setBrush(QColor(c["text_primary"]))
            cx = rect.center().x()
            cy = rect.center().y()
            points = [cx - 4, cy + 2, cx + 4, cy + 2, cx, cy - 4]
            painter.drawPolygon(points)
            painter.restore()
            return

        if element == QStyle.PrimitiveElement.PE_IndicatorSpinDown:
            rect = option.rect
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)

            is_dark = self._is_dark_theme()
            c = get_theme_colors(is_dark)

            bg = QColor(c["bg_tertiary"])
            if option.state & QStyle.StateFlag.State_MouseOver:
                bg = QColor(c["bg_hover"])
            painter.setBrush(bg)

            painter.drawRoundedRect(rect, 4, 4)

            painter.setBrush(QColor(c["text_primary"]))
            cx = rect.center().x()
            cy = rect.center().y()
            points = [cx - 4, cy - 2, cx + 4, cy - 2, cx, cy + 4]
            painter.drawPolygon(points)
            painter.restore()
            return

        super().drawPrimitive(element, option, painter, widget)

    def _is_dark_theme(self) -> bool:
        """Detect if the current theme is dark."""
        app = QApplication.instance()
        if app:
            palette = app.palette()
            bg = palette.color(QPalette.ColorRole.Window)
            brightness = (bg.red() * 299 + bg.green() * 587 + bg.blue() * 114) / 1000
            return brightness < 128
        return True


# =============================================================================
# Theme Application
# =============================================================================

def apply_modern_theme(target, is_dark: bool) -> None:
    """
    Apply the modern theme to the application or a widget.
    If target is not QApplication, apply to QApplication.instance().
    """
    # Always apply to the main application instance
    app = QApplication.instance()
    if app is None:
        return  # No application running

    # Build palette and stylesheet
    palette = build_palette(is_dark)
    stylesheet = build_stylesheet(is_dark)

    # Apply to application
    app.setPalette(palette)
    app.setStyleSheet(stylesheet)
    app.setStyle(ModernProxyStyle())

    # If target is a widget, also apply to it (but this is usually not needed)
    if isinstance(target, QWidget) and target is not app:
        # Optionally, apply to the widget as well
        target.setPalette(palette)
        target.setStyleSheet(stylesheet)


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
