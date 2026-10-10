import os
import subprocess
from PyQt6.QtWidgets import QApplication, QProxyStyle, QStyle, QStyleFactory
from PyQt6.QtCore import Qt, QPoint, QObject, QEvent
from PyQt6.QtGui import QPalette, QColor, QBrush, QIcon, QBitmap, QPainter
from PyQt6.QtWidgets import QWidget


# ═══════════════════════════════════════════════════════════════════
# Design tokens
#   One place to tweak the whole look. Every colour used by the
#   stylesheet, the palette and the custom-painted widgets comes from here.
# ═══════════════════════════════════════════════════════════════════
DARK = {
    "bg": "#141116",
    "surface": "#1b171c",
    "surface2": "#221e24",
    "raised": "#2c262e",
    "raised_hover": "#362f39",
    "raised_pressed": "#262028",
    "input": "#1e1a20",
    "border": "#342e36",
    "border_soft": "#2a242c",
    "border_strong": "#453c48",
    "text": "#f0e8ea",
    "muted": "#a8989e",
    "faint": "#6e6268",
    "accent": "#e85d4c",
    "accent_hover": "#f07060",
    "accent_pressed": "#d14a3a",
    "accent_text": "#f5a099",
    "accent_soft": "rgba(232, 93, 76, 36)",
    "on_accent": "#1a0e0c",
    "success": "#4caf7a",
    "success_hover": "#5ec08b",
    "success_text": "#7dd4a4",
    "success_soft": "rgba(76, 175, 122, 32)",
    "warning": "#e0a04a",
    "warning_soft": "rgba(224, 160, 74, 32)",
    "danger": "#e85d4c",
    "danger_soft": "rgba(232, 93, 76, 28)",
    "purple": "#c47a9a",
    "hover": "rgba(255, 255, 255, 10)",
    "hover_strong": "rgba(255, 255, 255, 18)",
    "scroll": "rgba(255, 255, 255, 36)",
    "scroll_hover": "rgba(255, 255, 255, 64)",
}


LIGHT = {
    "bg": "#f7f4f3",
    "surface": "#ffffff",
    "surface2": "#f3eeed",
    "raised": "#ffffff",
    "raised_hover": "#f3eeed",
    "raised_pressed": "#ebe4e2",
    "input": "#ffffff",
    "border": "#e8e0de",
    "border_soft": "#f0eae8",
    "border_strong": "#d4c8c5",
    "text": "#1f1816",
    "muted": "#6b5e5a",
    "faint": "#9a8c88",
    "accent": "#c43c2c",
    "accent_hover": "#d44a3a",
    "accent_pressed": "#a83224",
    "accent_text": "#b83628",
    "accent_soft": "rgba(196, 60, 44, 12)",
    "on_accent": "#ffffff",
    "success": "#1f7a4d",
    "success_hover": "#268a58",
    "success_text": "#1a6b43",
    "success_soft": "rgba(31, 122, 77, 16)",
    "warning": "#9a6b12",
    "warning_soft": "rgba(154, 107, 18, 16)",
    "danger": "#c43c2c",
    "danger_soft": "rgba(196, 60, 44, 14)",
    "purple": "#9a5080",
    "hover": "rgba(31, 24, 22, 6)",
    "hover_strong": "rgba(31, 24, 22, 11)",
    "scroll": "rgba(31, 24, 22, 28)",
    "scroll_hover": "rgba(31, 24, 22, 48)",
}


def is_dark_palette() -> bool:
    """True when the *currently applied* application palette is dark."""
    app = QApplication.instance()
    if app is None:
        return True
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def theme_color(name: str) -> QColor:
    """Return a design-token colour for the active theme (hex tokens only)."""
    tokens = DARK if is_dark_palette() else LIGHT
    return QColor(tokens[name])


class _PopupShaper(QObject):
    """Clips combo-box popups to a rounded shape.

    Qt's popup container can't be styled, so on desktops without a compositor
    (where a translucent window shows up as a black/square box) we shape the
    window itself with a rounded mask.
    """

    RADIUS = 10

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Show, QEvent.Type.Resize) and isinstance(obj, QWidget):
            w, h = obj.width(), obj.height()
            if w > 0 and h > 0:
                mask = QBitmap(w, h)
                mask.fill(Qt.GlobalColor.color0)
                painter = QPainter(mask)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(Qt.GlobalColor.color1)
                painter.drawRoundedRect(0, 0, w, h, self.RADIUS, self.RADIUS)
                painter.end()
                obj.setMask(mask)
        return False


class CustomProxyStyle(QProxyStyle):
    """Custom style for SpinBox arrows (follows the active palette)."""

    def __init__(self, *args):
        super().__init__(*args)
        self._popup_shaper = _PopupShaper(self)

    def polish(self, obj):
        if isinstance(obj, QPalette):
            return super().polish(obj)
        super().polish(obj)
        if hasattr(obj, "inherits") and obj.inherits("QComboBoxPrivateContainer"):
            # Transparent, shadow-less popup window + rounded mask (see _PopupShaper)
            obj.setWindowFlags(
                Qt.WindowType.Popup
                | Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.NoDropShadowWindowHint
            )
            obj.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            obj.installEventFilter(self._popup_shaper)

    def _draw_spin_arrow(self, option, painter, widget, up: bool):
        pal = widget.palette() if widget is not None else QApplication.palette()
        base = pal.color(QPalette.ColorRole.Button)
        dark = pal.color(QPalette.ColorRole.Window).lightness() < 128
        if option.state & QStyle.StateFlag.State_MouseOver:
            bg = base.lighter(118) if dark else base.darker(106)
        else:
            bg = base
        arrow = pal.color(QPalette.ColorRole.ButtonText)

        rect = option.rect
        painter.save()
        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 4, 4)
        cx = rect.x() + rect.width() // 2
        cy = rect.y() + rect.height() // 2
        if up:
            points = [QPoint(cx - 4, cy + 2), QPoint(cx + 4, cy + 2), QPoint(cx, cy - 3)]
        else:
            points = [QPoint(cx - 4, cy - 2), QPoint(cx + 4, cy - 2), QPoint(cx, cy + 3)]
        painter.setBrush(QBrush(arrow))
        painter.drawPolygon(points)
        painter.restore()

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorSpinUp:
            self._draw_spin_arrow(option, painter, widget, up=True)
            return
        if element == QStyle.PrimitiveElement.PE_IndicatorSpinDown:
            self._draw_spin_arrow(option, painter, widget, up=False)
            return
        super().drawPrimitive(element, option, painter, widget)


def detect_system_theme():
    """Detect system theme (dark/light) with multiple methods"""

    # 1. Check QT_QPA_PLATFORMTHEME
    platform_theme = os.environ.get("QT_QPA_PLATFORMTHEME", "")

    # 2. Check KDE using kreadconfig5 (most reliable for KDE)
    try:
        result = subprocess.run(
            ["kreadconfig5", "--group", "Colors:Window", "--key", "BackgroundNormal"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.stdout:
            color = result.stdout.strip()
            if color.startswith("#"):
                r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
                brightness = (r * 299 + g * 587 + b * 114) / 1000
                is_dark = brightness < 128
                print(f"✓ KDE detected: {'Dark' if is_dark else 'Light'}")
                return is_dark
    except:
        pass

    # 3. Check KDE using config file
    try:
        import configparser

        config = configparser.ConfigParser()
        config_path = os.path.expanduser("~/.config/kdeglobals")
        if os.path.exists(config_path):
            config.read(config_path)
            if config.has_section("Colors:Window"):
                bg = config.get("Colors:Window", "BackgroundNormal", fallback="")
                if bg.startswith("#"):
                    r, g, b = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
                    brightness = (r * 299 + g * 587 + b * 114) / 1000
                    is_dark = brightness < 128
                    print(f"✓ KDE config detected: {'Dark' if is_dark else 'Light'}")
                    return is_dark
    except:
        pass

    # 4. Check GNOME using gsettings (color-scheme) - most reliable for GNOME
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.stdout:
            scheme = result.stdout.strip().strip("'")
            is_dark = "dark" in scheme.lower()
            if scheme and scheme != "":
                print(
                    f"✓ GNOME color-scheme detected: {'Dark' if is_dark else 'Light'}"
                )
                return is_dark
    except:
        pass

    # 5. Check GNOME using gsettings (gtk-theme)
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.stdout:
            theme_name = result.stdout.strip().strip("'")
            is_dark = any(
                x in theme_name.lower() for x in ["dark", "night", "black", "-dark"]
            )
            print(
                f"✓ GNOME theme detected: {theme_name} → {'Dark' if is_dark else 'Light'}"
            )
            return is_dark
    except:
        pass

    # 6. Check GTK settings.ini
    try:
        gtk_config = os.path.expanduser("~/.config/gtk-3.0/settings.ini")
        if os.path.exists(gtk_config):
            with open(gtk_config, "r") as f:
                for line in f:
                    if "gtk-application-prefer-dark-theme" in line:
                        is_dark = "1" in line or "true" in line.lower()
                        print(
                            f"✓ GTK settings detected: {'Dark' if is_dark else 'Light'}"
                        )
                        return is_dark
                    if "gtk-theme-name" in line:
                        theme_name = line.split("=")[1].strip()
                        is_dark = any(
                            x in theme_name.lower()
                            for x in ["dark", "night", "black", "-dark"]
                        )
                        print(
                            f"✓ GTK theme detected: {theme_name} → {'Dark' if is_dark else 'Light'}"
                        )
                        return is_dark
    except:
        pass

    # 7. Check XDG_CURRENT_DESKTOP
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "kde" in desktop or "plasma" in desktop:
        print("✓ KDE desktop detected, defaulting to dark")
        return True
    elif "gnome" in desktop or "unity" in desktop:
        try:
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
                capture_output=True,
                text=True,
                timeout=1,
            )
            if result.stdout:
                theme = result.stdout.strip().strip("'")
                if "-dark" in theme or "-Dark" in theme:
                    return True
        except:
            pass
        return False

    # 8. Fallback: check terminal background
    try:
        result = subprocess.run(
            [
                "dconf",
                "read",
                "/org/gnome/terminal/legacy/profiles:/default/background-color",
            ],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.stdout:
            color = result.stdout.strip().strip("'")
            if color.startswith("#"):
                r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
                brightness = (r * 299 + g * 587 + b * 114) / 1000
                is_dark = brightness < 128
                print(
                    f"✓ Terminal background detected: {'Dark' if is_dark else 'Light'}"
                )
                return is_dark
    except:
        pass

    # 9. Check if Papirus-Dark is set as icon theme
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "icon-theme"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.stdout:
            icon_theme = result.stdout.strip().strip("'")
            is_dark = "dark" in icon_theme.lower()
            print(
                f"✓ Icon theme detected: {icon_theme} → {'Dark' if is_dark else 'Light'}"
            )
            return is_dark
    except:
        pass

    # 10. Ultimate fallback
    if platform_theme in ["kde", "gtk3"]:
        print(f"✓ Platform theme is {platform_theme}, defaulting to dark")
        return True

    print("⚠ No theme detected, defaulting to dark")
    return True


# ═══════════════════════════════════════════════════════════════════
# Stylesheet (single template, tokens are substituted as @name@)
# ═══════════════════════════════════════════════════════════════════

QSS_TEMPLATE = """
QMainWindow, QDialog { background-color: @bg@; }
QLabel { background: transparent; }

QToolTip {
    background-color: @surface2@;
    color: @text@;
    border: 1px solid @border_strong@;
    border-radius: 6px;
    padding: 5px 9px;
}

/* ===== Sidebar ===== */
QWidget#sidebar {
    background-color: @surface@;
    border-right: 1px solid @border@;
}
QLabel#section_title {
    color: @muted@;
    font-size: 11px;
    font-weight: 700;
    padding: 2px 6px;
}

/* ===== Toolbar ===== */
QWidget#toolbar {
    background-color: @bg@;
    border-bottom: 1px solid @border@;
}
QWidget#toolbar QPushButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0 12px;
    min-height: 34px;
    color: @text@;
    font-weight: 500;
}
QWidget#toolbar QPushButton:hover { background-color: @hover@; }
QWidget#toolbar QPushButton:pressed { background-color: @hover_strong@; }
QWidget#toolbar QPushButton:disabled { color: @faint@; }
QWidget#toolbar QPushButton:checked {
    background-color: @accent_soft@;
    color: @accent_text@;
}
QWidget#toolbar QPushButton[variant="primary"] {
    background-color: @accent@;
    border-color: @accent@;
    color: @on_accent@;
    font-weight: 600;
    padding: 0 16px;
}
QWidget#toolbar QPushButton[variant="primary"]:hover {
    background-color: @accent_hover@;
    border-color: @accent_hover@;
}
QWidget#toolbar QPushButton[variant="primary"]:pressed {
    background-color: @accent_pressed@;
    border-color: @accent_pressed@;
}
QWidget#toolbar QPushButton[variant="ghost-danger"]:hover:enabled {
    background-color: @danger_soft@;
    color: @danger@;
}
QWidget#toolbar QPushButton[iconOnly="true"] {
    padding: 0;
    min-width: 34px;
    max-width: 34px;
}
QFrame#toolbar_divider {
    background-color: @border@;
    min-width: 1px;
    max-width: 1px;
    border: none;
}

/* ===== Splitter ===== */
QSplitter::handle { background-color: @border@; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical { height: 1px; }

/* ===== Table ===== */
QTableView {
    background-color: @bg@;
    alternate-background-color: transparent;
    border: none;
    gridline-color: transparent;
    color: @text@;
    selection-background-color: @accent_soft@;
    selection-color: @text@;
    outline: 0;
}
QTableView::item {
    padding: 0 6px;
    border-bottom: 1px solid @border_soft@;
}
QTableView::item:hover { background-color: @hover@; }
QTableView::item:selected { background-color: @accent_soft@; color: @text@; }
QTableCornerButton::section { background-color: @bg@; border: none; }
QHeaderView { background-color: @bg@; }
QHeaderView::section {
    background-color: @bg@;
    color: @muted@;
    padding: 10px 8px;
    border: none;
    border-bottom: 1px solid @border@;
    font-size: 12px;
    font-weight: 600;
}
QHeaderView::section:hover { color: @text@; background-color: @hover@; }

QLabel#empty_state {
    color: @muted@;
    font-size: 14px;
    background: transparent;
}

/* ===== Lists / trees ===== */
QListWidget, QListView {
    background-color: transparent;
    border: none;
    color: @text@;
    outline: none;
}
QListWidget::item {
    padding: 9px 12px;
    border-radius: 8px;
    margin: 1px 0;
}
QListWidget::item:hover:!selected { background-color: @hover@; }
QListWidget::item:selected {
    background-color: @accent_soft@;
    color: @accent_text@;
}
QTreeView, QTreeWidget {
    background-color: @input@;
    border: 1px solid @border@;
    border-radius: 8px;
    outline: 0;
    selection-background-color: @accent_soft@;
    selection-color: @text@;
}
QTreeView::item { padding: 4px 6px; }
QTreeView::item:hover { background-color: @hover@; }
QTreeView::item:selected { background-color: @accent_soft@; color: @text@; }

/* ===== Buttons ===== */
QPushButton {
    background-color: @raised@;
    border: 1px solid @border@;
    border-radius: 8px;
    padding: 7px 14px;
    color: @text@;
    font-weight: 500;
}
QPushButton:hover { background-color: @raised_hover@; border-color: @border_strong@; }
QPushButton:pressed { background-color: @raised_pressed@; }
QPushButton:disabled {
    color: @faint@;
    background-color: @surface2@;
    border-color: @border_soft@;
}
QPushButton:checked {
    background-color: @accent_soft@;
    border-color: @accent@;
    color: @accent_text@;
}

QPushButton:default, QPushButton[variant="primary"] {
    background-color: @accent@;
    border-color: @accent@;
    color: @on_accent@;
    font-weight: 600;
}
QPushButton:default:hover, QPushButton[variant="primary"]:hover {
    background-color: @accent_hover@;
    border-color: @accent_hover@;
}
QPushButton:default:pressed, QPushButton[variant="primary"]:pressed {
    background-color: @accent_pressed@;
    border-color: @accent_pressed@;
}
QPushButton:default:disabled, QPushButton[variant="primary"]:disabled {
    background-color: @surface2@;
    border-color: @border_soft@;
    color: @faint@;
}

QPushButton#start_btn, QPushButton[variant="success"] {
    background-color: @success@;
    border-color: @success@;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#start_btn:hover, QPushButton[variant="success"]:hover {
    background-color: @success_hover@;
    border-color: @success_hover@;
}
QPushButton#start_btn:disabled, QPushButton[variant="success"]:disabled {
    background-color: @surface2@;
    border-color: @border_soft@;
    color: @faint@;
}
QPushButton#pause_btn, QPushButton[variant="warning"] {
    background-color: @warning_soft@;
    border-color: transparent;
    color: @warning@;
    font-weight: 600;
}
QPushButton#pause_btn:hover, QPushButton[variant="warning"]:hover {
    background-color: @warning@;
    color: #1b1e25;
}
QPushButton#pause_btn:disabled, QPushButton[variant="warning"]:disabled {
    background-color: @surface2@;
    border-color: @border_soft@;
    color: @faint@;
}
QPushButton[variant="danger"] {
    background-color: @danger_soft@;
    border-color: transparent;
    color: @danger@;
}
QPushButton[variant="danger"]:hover:enabled {
    background-color: @danger@;
    color: #ffffff;
}
QPushButton[variant="danger"]:disabled {
    background-color: @surface2@;
    border-color: @border_soft@;
    color: @faint@;
}
QPushButton[variant="ghost"] {
    background-color: transparent;
    border-color: transparent;
}
QPushButton[variant="ghost"]:hover { background-color: @hover@; }

QDialog QPushButton { padding: 8px 18px; min-width: 76px; }

QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px;
}
QToolButton:hover { background-color: @hover@; }
QToolButton:pressed { background-color: @hover_strong@; }

/* ===== Inputs ===== */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox,
QTimeEdit, QDateEdit, QDateTimeEdit, QComboBox {
    background-color: @input@;
    color: @text@;
    border: 1px solid @border@;
    border-radius: 8px;
    padding: 6px 10px;
    selection-background-color: @accent@;
    selection-color: @on_accent@;
}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QSpinBox:hover,
QDoubleSpinBox:hover, QTimeEdit:hover, QDateEdit:hover, QComboBox:hover {
    border-color: @border_strong@;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
QDoubleSpinBox:focus, QTimeEdit:focus, QDateEdit:focus, QDateTimeEdit:focus,
QComboBox:focus, QComboBox:on {
    border: 1px solid @accent@;
}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled, QTimeEdit:disabled, QDateEdit:disabled, QComboBox:disabled {
    background-color: @surface2@;
    color: @faint@;
}
/* Drop-down list. Qt's popup container can't be styled, so: use the classic
   drop-down mode (no margin strips around the list); the container window is
   made transparent and masked to a rounded shape in CustomProxyStyle.polish. */
QComboBox { combobox-popup: 0; }
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 28px;
    border: none;
    background: transparent;
}
QAbstractSpinBox { padding-right: 28px; }
QAbstractSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 22px;
    margin: 3px 3px 0 0;
    border: none;
    border-top-right-radius: 6px;
    background: transparent;
}
QAbstractSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 22px;
    margin: 0 3px 3px 0;
    border: none;
    border-bottom-right-radius: 6px;
    background: transparent;
}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover { background-color: @hover_strong@; }
QAbstractSpinBox::up-button:pressed, QAbstractSpinBox::down-button:pressed { background-color: @accent_soft@; }
QAbstractSpinBox::up-arrow { image: url(@arrow_up@); width: 10px; height: 10px; }
QAbstractSpinBox::down-arrow { image: url(@arrow_down@); width: 10px; height: 10px; }
QAbstractSpinBox::up-arrow:disabled, QAbstractSpinBox::up-arrow:off { image: url(@arrow_up_disabled@); }
QAbstractSpinBox::down-arrow:disabled, QAbstractSpinBox::down-arrow:off { image: url(@arrow_down_disabled@); }
QComboBox::down-arrow { image: url(@arrow_down@); width: 12px; height: 12px; }
QComboBox::down-arrow:disabled { image: url(@arrow_down_disabled@); }
QComboBox QAbstractItemView {
    background-color: @surface@;
    color: @text@;
    border: 1px solid @border_strong@;
    border-radius: 10px;
    padding: 4px;
    outline: 0;
    selection-background-color: @accent_soft@;
    selection-color: @accent_text@;
}
QComboBox QAbstractItemView::item {
    padding: 6px 10px;
    border-radius: 6px;
    min-height: 22px;
}
QComboBox QAbstractItemView::item:selected {
    background-color: @accent_soft@;
    color: @accent_text@;
}

/* ===== Progress bar ===== */
QProgressBar {
    background-color: @raised@;
    border: 1px solid @border@;   
    border-radius: 7px;
    text-align: center;
    color: @text@;
    font-size: 11px;
    font-weight: 600;
    min-height: 18px;
}
QProgressBar::chunk { background-color: @accent@; border-radius: 7px; }

/* ===== Menus ===== */
QMenuBar {
    background-color: @bg@;
    color: @text@;
    padding: 3px 8px;
    border-bottom: 1px solid @border@;
}
QMenuBar::item {
    padding: 6px 12px;
    border-radius: 6px;
    background: transparent;
    margin: 0 1px;
}
QMenuBar::item:selected { background-color: @hover_strong@; }
QMenuBar::item:pressed { background-color: @accent_soft@; color: @accent_text@; }
QMenu {
    background-color: @surface@;
    color: @text@;
    border: 1px solid @border_strong@;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item {
    padding: 7px 28px 7px 12px;
    border-radius: 6px;
    margin: 1px 2px;
    background: transparent;
}
QMenu::item:selected { background-color: @accent_soft@; color: @accent_text@; }
QMenu::item:disabled { color: @faint@; }
QMenu::icon { padding-left: 6px; }
QMenu::separator { height: 1px; background: @border@; margin: 5px 8px; }

/* ===== Status bar ===== */
QStatusBar {
    background-color: @surface@;
    border-top: 1px solid @border@;
    color: @muted@;
}
QStatusBar::item { border: none; }
QStatusBar QLabel { color: @muted@; }
QLabel#speed_label {
    color: @accent_text@;
    font-weight: 700;
    min-width: 84px;
}

/* ===== Check / radio ===== */
QCheckBox, QRadioButton { spacing: 8px; }

/* ===== Group box ===== */
QGroupBox {
    background-color: @surface2@;
    border: 1px solid @border@;
    border-radius: 10px;
    margin-top: 14px;
    padding-top: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    bottom:-6px;
    padding: 0 6px;
    color: @muted@;
}

/* ===== Scroll bars ===== */
QScrollBar:vertical { background: transparent; width: 12px; margin: 0; }
QScrollBar::handle:vertical {
    background: @scroll@;
    border-radius: 3px;
    margin: 2px 3px;
    min-height: 28px;
}
QScrollBar::handle:vertical:hover { background: @scroll_hover@; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
QScrollBar::handle:horizontal {
    background: @scroll@;
    border-radius: 3px;
    margin: 3px 2px;
    min-width: 28px;
}
QScrollBar::handle:horizontal:hover { background: @scroll_hover@; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; background: none; border: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

/* ===== Tabs ===== */
QTabWidget::pane { border: none; border-top: 1px solid @border@; background: transparent; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: transparent;
    color: @muted@;
    padding: 9px 16px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 500;
}
QTabBar::tab:selected { color: @text@; border-bottom: 2px solid @accent@; }
QTabBar::tab:hover:!selected { color: @text@; }

/* ===== Details panel ===== */
QWidget#details_panel {
    background-color: @surface@;
    border-top: 1px solid @border@;
}
QLabel#details_empty { color: @faint@; font-size: 14px; }
QLabel[role="muted"] { color: @muted@; font-size: 12px; font-weight: 600; }
QLabel[role="value"] { font-size: 12px; }
"""


def _make_arrow_icons(tokens: dict) -> dict:
    """Paint the combo-box chevrons once per theme (QSS needs image files)."""
    import tempfile
    from PyQt6.QtGui import QPixmap, QPainter, QPen
    from PyQt6.QtCore import QPointF

    out_dir = os.path.join(tempfile.gettempdir(), "felfeldm-ui")
    os.makedirs(out_dir, exist_ok=True)
    result = {}
    for key, color in (("arrow_down", tokens["muted"]),
                       ("arrow_down_disabled", tokens["faint"]),
                       ("arrow_up", tokens["muted"]),
                       ("arrow_up_disabled", tokens["faint"])):
        up = key.startswith("arrow_up")
        for scale, suffix in ((1, ""), (2, "@2x")):
            size = 12 * scale
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(color), 1.6 * scale)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            y_far, y_near = (7.5, 4.0) if up else (4.5, 8.0)
            painter.drawPolyline([
                QPointF(2.5 * scale, y_far * scale),
                QPointF(6 * scale, y_near * scale),
                QPointF(9.5 * scale, y_far * scale),
            ])
            painter.end()
            name = f"{key}_{color.lstrip('#')}{suffix}.png"
            pm.save(os.path.join(out_dir, name))
        result[key] = os.path.join(out_dir, f"{key}_{color.lstrip('#')}.png").replace("\\", "/")
    return result


def build_stylesheet(tokens: dict) -> str:
    qss = QSS_TEMPLATE
    tokens = {**tokens, **_make_arrow_icons(tokens)}
    # longest keys first so e.g. @accent_soft@ is never clobbered by @accent@
    for key in sorted(tokens, key=len, reverse=True):
        qss = qss.replace(f"@{key}@", tokens[key])
    return qss


def build_palette(tokens: dict) -> QPalette:
    c = QColor
    p = QPalette()
    R = QPalette.ColorRole
    G = QPalette.ColorGroup
    p.setColor(R.Window, c(tokens["bg"]))
    p.setColor(R.WindowText, c(tokens["text"]))
    p.setColor(R.Base, c(tokens["input"]))
    p.setColor(R.AlternateBase, c(tokens["surface2"]))
    p.setColor(R.Text, c(tokens["text"]))
    p.setColor(R.Button, c(tokens["raised"]))
    p.setColor(R.ButtonText, c(tokens["text"]))
    p.setColor(R.Highlight, c(tokens["accent"]))
    p.setColor(R.HighlightedText, c(tokens["on_accent"]))
    p.setColor(R.ToolTipBase, c(tokens["surface2"]))
    p.setColor(R.ToolTipText, c(tokens["text"]))
    p.setColor(R.PlaceholderText, c(tokens["faint"]))
    p.setColor(R.Link, c(tokens["accent_text"]))
    for role in (R.WindowText, R.Text, R.ButtonText):
        p.setColor(G.Disabled, role, c(tokens["faint"]))
    return p


def setup_style(app, theme="auto"):
    """Setup application style with theme support
    theme: 'auto', 'dark', 'light'
    """
    if theme == "auto":
        print("🔄 Detecting system theme...")
        is_dark = detect_system_theme()
        print(f"🎨 Detected: {'Dark' if is_dark else 'Light'} theme")
    else:
        is_dark = theme == "dark"
        print(f"🎨 Theme set to: {'Dark' if is_dark else 'Light'}")

    # Icon theme (unchanged behaviour)
    wanted, fallback = (
        ("Papirus-Dark", "breeze-dark") if is_dark else ("Papirus-Light", "breeze")
    )
    try:
        result = subprocess.run(["fc-match", wanted], capture_output=True, timeout=1)
        QIcon.setThemeName(wanted if result.returncode == 0 else fallback)
    except Exception:
        QIcon.setThemeName(fallback)

    # One consistent widget style on every desktop; the stylesheet does the rest.
    # (setStyle must come before setPalette, it resets the palette.)
    app.setStyle(CustomProxyStyle("Fusion"))

    tokens = DARK if is_dark else LIGHT
    app.setPalette(build_palette(tokens))
    app.setStyleSheet(build_stylesheet(tokens))
