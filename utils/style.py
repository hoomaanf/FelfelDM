# utils/style.py

import os
import subprocess
from PyQt6.QtWidgets import QApplication, QProxyStyle, QStyle
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPalette, QColor, QBrush, QPen, QIcon

class CustomProxyStyle(QProxyStyle):
    """Custom style for SpinBox arrows"""
    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorSpinUp:
            rect = option.rect
            painter.save()
            if option.state & QStyle.StateFlag.State_MouseOver:
                painter.setBrush(QBrush(QColor(74, 77, 83)))
            else:
                painter.setBrush(QBrush(QColor(61, 61, 64)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 3, 3)
            center_x = rect.x() + rect.width() // 2
            center_y = rect.y() + rect.height() // 2
            points = [
                QPoint(center_x - 5, center_y + 2),
                QPoint(center_x + 5, center_y + 2),
                QPoint(center_x, center_y - 4)
            ]
            painter.setBrush(QBrush(QColor(239, 239, 239)))
            painter.drawPolygon(points)
            painter.restore()
            return

        if element == QStyle.PrimitiveElement.PE_IndicatorSpinDown:
            rect = option.rect
            painter.save()
            if option.state & QStyle.StateFlag.State_MouseOver:
                painter.setBrush(QBrush(QColor(74, 77, 83)))
            else:
                painter.setBrush(QBrush(QColor(61, 61, 64)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 3, 3)
            center_x = rect.x() + rect.width() // 2
            center_y = rect.y() + rect.height() // 2
            points = [
                QPoint(center_x - 5, center_y - 2),
                QPoint(center_x + 5, center_y - 2),
                QPoint(center_x, center_y + 4)
            ]
            painter.setBrush(QBrush(QColor(239, 239, 239)))
            painter.drawPolygon(points)
            painter.restore()
            return

        super().drawPrimitive(element, option, painter, widget)


def setup_style(app, theme="auto"):
    """Setup application style with theme support
    theme: 'auto', 'dark', 'light'
    """
    # Determine if dark mode
    if theme == "auto":
        try:
            is_dark = True
            try:
                result = subprocess.run(['kreadconfig5', '--group', 'Colors:Window', '--key', 'BackgroundNormal'], 
                               capture_output=True, text=True)
                if result.stdout:
                    color = result.stdout.strip()
                    if color.startswith('#'):
                        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
                        brightness = (r * 299 + g * 587 + b * 114) / 1000
                        is_dark = brightness < 128
            except:
                pass
            
            if 'QT_QPA_PLATFORMTHEME' in os.environ:
                if os.environ['QT_QPA_PLATFORMTHEME'] == 'kde':
                    try:
                        import configparser
                        config = configparser.ConfigParser()
                        config_path = os.path.expanduser('~/.config/kdeglobals')
                        if os.path.exists(config_path):
                            config.read(config_path)
                            if config.has_section('Colors:Window'):
                                bg = config.get('Colors:Window', 'BackgroundNormal', fallback='')
                                if bg.startswith('#'):
                                    r, g, b = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
                                    brightness = (r * 299 + g * 587 + b * 114) / 1000
                                    is_dark = brightness < 128
                    except:
                        pass
        except:
            is_dark = True
    else:
        is_dark = (theme == "dark")

        # === Icon Theme (اول Papirus سیستم، بعد breeze) ===
    if is_dark:
        # اول Papirus-Dark سیستم
        if subprocess.run(['fc-match', 'Papirus-Dark'], capture_output=True).returncode == 0:
            QIcon.setThemeName('Papirus-Dark')
            print("✓ Using Papirus-Dark (system)")
        else:
            QIcon.setThemeName('breeze-dark')
            print("⚠ Papirus-Dark not found on system → Using breeze-dark")
    else:
        # اول Papirus-Light سیستم
        if subprocess.run(['fc-match', 'Papirus-Light'], capture_output=True).returncode == 0:
            QIcon.setThemeName('Papirus-Light')
            print("✓ Using Papirus-Light (system)")
        else:
            QIcon.setThemeName('breeze')
            print("⚠ Papirus-Light not found on system → Using breeze")

    app.setStyle('Fusion')

    if is_dark:
        # ===== DARK THEME =====
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(45, 45, 48))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(239, 239, 239))
        palette.setColor(QPalette.ColorRole.Base, QColor(28, 28, 30))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(38, 38, 40))
        palette.setColor(QPalette.ColorRole.Text, QColor(239, 239, 239))
        palette.setColor(QPalette.ColorRole.Button, QColor(55, 55, 60))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(239, 239, 239))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(61, 174, 233))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        app.setPalette(palette)

        app.setStyleSheet("""
            QMainWindow { background-color: #2d2d30; }
            
            /* ===== Sidebar ===== */
            QWidget#sidebar {
                background-color: #2d2d30;
                border-right: 1px solid #1e1e20;
            }
            
            /* ===== Toolbar ===== */
            QWidget#toolbar {
                background-color: #2d2d30;
                border-bottom: 1px solid #1e1e20;
                padding: 4px;
            }
            
            /* ===== Toolbar Buttons ===== */
            QWidget#toolbar QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                color: #efeff1;
                height: 32px;
            }
            QWidget#toolbar QPushButton:hover {
                background-color: #3a3f44;
            }
            QWidget#toolbar QPushButton:pressed {
                background-color: #1e1e20;
            }
            QWidget#toolbar QPushButton:disabled {
                opacity: 0.4;
            }
            
            /* ===== Settings Button ===== */
            QWidget#toolbar QPushButton#btn_settings {
                padding: 6px 12px;
                height: 32px;
            }
            
            /* ===== Splitter ===== */
            QSplitter::handle {
                background-color: #3d4045;
                width: 4px;
            }
            QSplitter::handle:hover {
                background-color: #4a4d53;
            }
            
            /* ===== Table View ===== */
            QTableView {
                background-color: #1e1e20;
                border: none;
                alternate-background-color: #2a2a2d;
                gridline-color: #3d3d40;
                color: #efeff1;
            }
            QTableView::item:selected { background-color: #3daee9; color: white; }
            QTableView::item:!selected:hover { background-color: #3a3f44; }
            QHeaderView::section {
                background-color: #2d2d30;
                padding: 8px;
                border: none;
                border-right: 1px solid #1e1e20;
                border-bottom: 1px solid #1e1e20;
                color: #efeff1;
                font-weight: bold;
            }
            QHeaderView::section:hover { background-color: #3a3f44; }
            
            /* ===== List Widget ===== */
            QListWidget {
                background-color: transparent;
                border: none;
                color: #efeff1;
                outline: none;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-radius: 4px;
                margin: 2px 4px;
            }
            QListWidget::item:selected { background-color: #3daee9; color: white; }
            QListWidget::item:hover:!selected { background-color: #3a3f44; }
            
            /* ===== Push Buttons ===== */
            QPushButton {
                background-color: #3d4045;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                color: #efeff1;
            }
            QPushButton:hover { background-color: #4a4d53; }
            QPushButton:pressed { background-color: #2d3035; }
            QPushButton:disabled { opacity: 0.4; }
            QPushButton#start_btn {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
            }
            QPushButton#start_btn:hover { background-color: #2ecc71; }
            QPushButton#start_btn:disabled { background-color: #1a6e3a; opacity: 0.5; }
            QPushButton#pause_btn {
                background-color: #f39c12;
                color: white;
                font-weight: bold;
            }
            QPushButton#pause_btn:hover { background-color: #f1c40f; }
            QPushButton#pause_btn:disabled { background-color: #9e6200; opacity: 0.5; }
            
            /* ===== Input Fields ===== */
            QLineEdit, QTextEdit, QComboBox, QTimeEdit {
                background-color: #232629;
                color: #efeff1;
                border: 1px solid #3d4045;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QLineEdit:focus, QTextEdit:focus { border: 1px solid #3daee9; }
            
            /* ===== SpinBox (فقط رنگ پس‌زمینه) ===== */
            QSpinBox {
                background-color: #232629;
                color: #efeff1;
            }
            QSpinBox:focus { 
                background-color: #232629;
            }
            
            /* ===== Progress Bar ===== */
            QProgressBar {
                border: 1px solid #3d4045;
                border-radius: 4px;
                text-align: center;
                color: #efeff1;
            }
            QProgressBar::chunk { background-color: #3daee9; border-radius: 4px; }
            
            /* ===== Menu Bar ===== */
            QMenuBar {
                background-color: transparent;
                color: #efeff1;
                padding: 2px 4px;
                font-weight: 500;
                font-size: 13px;
                spacing: 2px;
            }
            QMenuBar::item {
                padding: 6px 14px;
                border-radius: 4px;
                background: transparent;
                margin: 0 2px;
            }
            QMenuBar::item:selected { background-color: #3a3f44; color: #efeff1; }
            QMenuBar::item:pressed { background-color: #3daee9; color: white; }
            
            /* ===== Menu ===== */
            QMenu {
                background-color: #2d2d30;
                color: #efeff1;
                border: 1px solid #3d4045;
                border-radius: 10px;
                padding: 6px;
            }
            QMenu::item {
                padding: 8px 36px 8px 16px;
                border-radius: 6px;
                margin: 2px 4px;
                background: transparent;
            }
            QMenu::item:selected { background-color: #3daee9; color: white; }
            QMenu::item:hover { background-color: #3daee9; color: white; }
            QMenu::separator {
                height: 1px;
                background: #3d4045;
                margin: 4px 8px;
            }
            
            /* ===== Context Menu ===== */
            QMenu#contextMenu {
                background-color: #2d2d30;
                border: 1px solid #3d4045;
                border-radius: 10px;
                padding: 6px;
            }
            QMenu#contextMenu::item {
                padding: 6px 30px 6px 14px;
                border-radius: 6px;
                margin: 2px 4px;
            }
            QMenu#contextMenu::item:selected { background-color: #3daee9; color: white; }
            QMenu#contextMenu::item:hover { background-color: #3daee9; color: white; }
            
            /* ===== Status Bar ===== */
            QStatusBar { 
                background-color: #2d2d30; 
                color: #efeff1; 
            }
            
            /* ===== Check Box ===== */
            QCheckBox { 
                color: #efeff1; 
                spacing: 8px; 
            }
            
            /* ===== Group Box ===== */
            QGroupBox {
                border: 1px solid #3d4045;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                color: #efeff1;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            
            /* ===== Tooltip ===== */
            QToolTip {
                background-color: #232629;
                color: #efeff1;
                border: 1px solid #3d4045;
                border-radius: 4px;
                padding: 4px 8px;
            }
            
            /* ===== Scroll Bar ===== */
            QScrollBar:vertical {
                background: #2d2d30;
                width: 12px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #3d4045;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #4a4d53; }
            QScrollBar:horizontal {
                background: #2d2d30;
                height: 12px;
                margin: 0;
            }
            QScrollBar::handle:horizontal {
                background: #3d4045;
                border-radius: 4px;
                min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover { background: #4a4d53; }
            
            /* ===== Dialog ===== */
            QDialog { background-color: #2d2d30; }
            QLabel { color: #efeff1; }
            
            /* ===== Tab Widget ===== */
            QTabWidget::pane { border: none; background: transparent; }
            QTabBar::tab {
                background: transparent;
                color: #888890;
                padding: 8px 16px;
                border: none;
                border-bottom: 2px solid transparent;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                color: #efeff1;
                border-bottom: 2px solid #3daee9;
            }
            QTabBar::tab:hover:!selected { color: #efeff1; }
            
            /* ===== Dialog Buttons ===== */
            QDialog QPushButton {
                padding: 8px 20px;
                min-width: 80px;
            }
            QDialog QPushButton[text="OK"] {
                background-color: #3daee9;
                color: white;
                font-weight: bold;
            }
            QDialog QPushButton[text="OK"]:hover { background-color: #5ab8f0; }
            QDialog QPushButton[text="Cancel"] {
                background-color: #e74c3c;
                color: white;
            }
            QDialog QPushButton[text="Cancel"]:hover { background-color: #ff6b6b; }
        """)
    else:
        # ===== LIGHT THEME =====
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(235, 235, 238))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(30, 30, 33))
        palette.setColor(QPalette.ColorRole.Base, QColor(245, 245, 248))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(238, 238, 241))
        palette.setColor(QPalette.ColorRole.Text, QColor(30, 30, 33))
        palette.setColor(QPalette.ColorRole.Button, QColor(225, 225, 228))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(30, 30, 33))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(61, 174, 233))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        app.setPalette(palette)

        app.setStyleSheet("""
            QMainWindow { background-color: #ebebee; }
            
            /* ===== Sidebar ===== */
            QWidget#sidebar {
                background-color: #ebebee;
                border-right: 1px solid #d0d0d5;
            }
            
            /* ===== Toolbar ===== */
            QWidget#toolbar {
                background-color: #ebebee;
                border-bottom: 1px solid #d0d0d5;
                padding: 4px;
            }
            
            /* ===== Toolbar Buttons ===== */
            QWidget#toolbar QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                color: #1e1e21;
                height: 32px;
            }
            QWidget#toolbar QPushButton:hover {
                background-color: #d5d5da;
            }
            QWidget#toolbar QPushButton:pressed {
                background-color: #c0c0c5;
            }
            QWidget#toolbar QPushButton:disabled {
                opacity: 0.4;
            }
            
            /* ===== Settings Button ===== */
            QWidget#toolbar QPushButton#btn_settings {
                padding: 6px 12px;
                height: 32px;
            }
            
            /* ===== Splitter ===== */
            QSplitter::handle {
                background-color: #d0d0d5;
                width: 4px;
            }
            QSplitter::handle:hover {
                background-color: #c0c0c5;
            }
            
            /* ===== Table View ===== */
            QTableView {
                background-color: #f5f5f8;
                border: none;
                alternate-background-color: #eeeef1;
                gridline-color: #d0d0d5;
                color: #1e1e21;
            }
            QTableView::item:selected { background-color: #3daee9; color: white; }
            QTableView::item:!selected:hover { background-color: #e0e0e5; }
            QHeaderView::section {
                background-color: #ebebee;
                padding: 8px;
                border: none;
                border-right: 1px solid #f5f5f8;
                border-bottom: 1px solid #f5f5f8;
                color: #6a6a70;
                font-weight: bold;
            }
            QHeaderView::section:hover { background-color: #d5d5da; }
            
            /* ===== List Widget ===== */
            QListWidget {
                background-color: transparent;
                border: none;
                color: #1e1e21;
                outline: none;
            }
            QListWidget::item {
                padding: 8px 12px;
                border-radius: 4px;
                margin: 2px 4px;
            }
            QListWidget::item:selected { background-color: #3daee9; color: white; }
            QListWidget::item:hover:!selected { background-color: #d5d5da; }
            
            /* ===== Push Buttons ===== */
            QPushButton {
                background-color: #d5d5da;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                color: #1e1e21;
            }
            QPushButton:hover { background-color: #c8c8cd; }
            QPushButton:pressed { background-color: #b8b8bd; }
            QPushButton:disabled { opacity: 0.4; }
            QPushButton#start_btn {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
            }
            QPushButton#start_btn:hover { background-color: #2ecc71; }
            QPushButton#start_btn:disabled { background-color: #1a6e3a; opacity: 0.5; }
            QPushButton#pause_btn {
                background-color: #f39c12;
                color: white;
                font-weight: bold;
            }
            QPushButton#pause_btn:hover { background-color: #f1c40f; }
            QPushButton#pause_btn:disabled { background-color: #9e6200; opacity: 0.5; }
            
            /* ===== Input Fields ===== */
            QLineEdit, QTextEdit, QComboBox, QTimeEdit {
                background-color: #f5f5f8;
                color: #1e1e21;
                border: 1px solid #d0d0d5;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QLineEdit:focus, QTextEdit:focus { border: 1px solid #3daee9; }
            
            /* ===== SpinBox (فقط رنگ پس‌زمینه) ===== */
            QSpinBox {
                background-color: #f5f5f8;
                color: #1e1e21;
            }
            QSpinBox:focus { 
                background-color: #f5f5f8;
            }
            
            /* ===== Progress Bar ===== */
            QProgressBar {
                border: 1px solid #d0d0d5;
                border-radius: 4px;
                text-align: center;
                color: #1e1e21;
            }
            QProgressBar::chunk { background-color: #3daee9; border-radius: 4px; }
            
            /* ===== Menu Bar ===== */
            QMenuBar {
                background-color: transparent;
                color: #1e1e21;
                padding: 2px 4px;
                font-weight: 500;
                font-size: 13px;
                spacing: 2px;
            }
            QMenuBar::item {
                padding: 6px 14px;
                border-radius: 4px;
                background: transparent;
                margin: 0 2px;
            }
            QMenuBar::item:selected { background-color: #d5d5da; color: #1e1e21; }
            QMenuBar::item:pressed { background-color: #3daee9; color: white; }
            
            /* ===== Menu ===== */
            QMenu {
                background-color: #ebebee;
                color: #1e1e21;
                border: 1px solid #d0d0d5;
                border-radius: 10px;
                padding: 6px;
            }
            QMenu::item {
                padding: 8px 36px 8px 16px;
                border-radius: 6px;
                margin: 2px 4px;
                background: transparent;
            }
            QMenu::item:selected { background-color: #3daee9; color: white; }
            QMenu::item:hover { background-color: #3daee9; color: white; }
            QMenu::separator {
                height: 1px;
                background: #d0d0d5;
                margin: 4px 8px;
            }
            
            /* ===== Context Menu ===== */
            QMenu#contextMenu {
                background-color: #ebebee;
                border: 1px solid #d0d0d5;
                border-radius: 10px;
                padding: 6px;
            }
            QMenu#contextMenu::item {
                padding: 6px 30px 6px 14px;
                border-radius: 6px;
                margin: 2px 4px;
            }
            QMenu#contextMenu::item:selected { background-color: #3daee9; color: white; }
            QMenu#contextMenu::item:hover { background-color: #3daee9; color: white; }
            
            /* ===== Status Bar ===== */
            QStatusBar { 
                background-color: #ebebee; 
                color: #6a6a70; 
            }
            
            /* ===== Check Box ===== */
            QCheckBox { 
                color: #1e1e21; 
                spacing: 8px; 
            }
            
            /* ===== Group Box ===== */
            QGroupBox {
                border: 1px solid #d0d0d5;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                color: #1e1e21;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            
            /* ===== Tooltip ===== */
            QToolTip {
                background-color: #ebebee;
                color: #1e1e21;
                border: 1px solid #d0d0d5;
                border-radius: 4px;
                padding: 4px 8px;
            }
            
            /* ===== Scroll Bar ===== */
            QScrollBar:vertical {
                background: #ebebee;
                width: 12px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #c8c8cd;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #b8b8bd; }
            QScrollBar:horizontal {
                background: #ebebee;
                height: 12px;
                margin: 0;
            }
            QScrollBar::handle:horizontal {
                background: #c8c8cd;
                border-radius: 4px;
                min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover { background: #b8b8bd; }
            
            /* ===== Dialog ===== */
            QDialog { background-color: #ebebee; }
            QLabel { color: #1e1e21; }
            
            /* ===== Tab Widget ===== */
            QTabWidget::pane { border: none; background: transparent; }
            QTabBar::tab {
                background: transparent;
                color: #888890;
                padding: 8px 16px;
                border: none;
                border-bottom: 2px solid transparent;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                color: #1e1e21;
                border-bottom: 2px solid #3daee9;
            }
            QTabBar::tab:hover:!selected { color: #1e1e21; }
            
            /* ===== Dialog Buttons ===== */
            QDialog QPushButton {
                padding: 8px 20px;
                min-width: 80px;
            }
            QDialog QPushButton[text="OK"] {
                background-color: #3daee9;
                color: white;
                font-weight: bold;
            }
            QDialog QPushButton[text="OK"]:hover { background-color: #5ab8f0; }
            QDialog QPushButton[text="Cancel"] {
                background-color: #e74c3c;
                color: white;
            }
            QDialog QPushButton[text="Cancel"]:hover { background-color: #ff6b6b; }
        """)

    print(f"✓ Theme applied: {'Dark' if is_dark else 'Light'} ({theme})")