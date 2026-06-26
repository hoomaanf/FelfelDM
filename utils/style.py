# utils/style.py

import sys
import os
import subprocess
from PyQt6.QtWidgets import QApplication, QStyle, QProxyStyle, QStyleFactory
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QPalette, QColor, QBrush, QPen, QFont, QIcon

# ─── Custom Style for SpinBox Arrows ──────────────────────────────────────────

class CustomProxyStyle(QProxyStyle):
    """استایل سفارشی برای نمایش فلش‌های SpinBox"""
    
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


# ─── Style Setup ──────────────────────────────────────────────────────────────

def setup_style(app):
    """تنظیم استایل با آیکون‌های پاپیروس و تشخیص خودکار تم"""
    
    is_dark = True
    try:
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
        pass
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    icon_path = os.path.join(os.path.dirname(script_dir), 'icons')
    
    if os.path.exists(icon_path):
        search_paths = QIcon.themeSearchPaths()
        if icon_path not in search_paths:
            search_paths.insert(0, icon_path)
            QIcon.setThemeSearchPaths(search_paths)
        
        if is_dark:
            if os.path.exists(os.path.join(icon_path, 'Papirus-Dark')):
                QIcon.setThemeName('Papirus-Dark')
                print("✓ Using Papirus-Dark icons")
            elif os.path.exists(os.path.join(icon_path, 'Papirus')):
                QIcon.setThemeName('Papirus')
                print("✓ Using Papirus icons")
            else:
                QIcon.setThemeName('breeze-dark')
                print("⚠ Using system icons")
        else:
            if os.path.exists(os.path.join(icon_path, 'Papirus-Light')):
                QIcon.setThemeName('Papirus-Light')
                print("✓ Using Papirus-Light icons")
            elif os.path.exists(os.path.join(icon_path, 'Papirus')):
                QIcon.setThemeName('Papirus')
                print("✓ Using Papirus icons")
            else:
                QIcon.setThemeName('breeze')
                print("⚠ Using system icons")
    else:
        print(f"⚠ Icon folder not found: {icon_path}")
        QIcon.setThemeName('breeze-dark' if is_dark else 'breeze')
    
    app.setStyle('Fusion')
    
    if is_dark:
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
            QTableView {
                background-color: #1e1e20;
                border: none;
                alternate-background-color: #2a2a2d;
                gridline-color: #3d3d40;
                color: #efeff1;
            }
            QTableView::item:selected { background-color: #3daee9; color: white; }
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
            QPushButton#single_btn {
                background-color: #3daee9;
                color: white;
                font-weight: bold;
            }
            QPushButton#single_btn:hover { background-color: #5ab8f0; }
            QLineEdit, QTextEdit, QComboBox, QTimeEdit {
                background-color: #232629;
                color: #efeff1;
                border: 1px solid #3d4045;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QSpinBox {
                background-color: #232629;       
                color: #efeff1;
                border: 1px solid #3d4045;
                border-radius: 4px;
                padding: 6px 10px;
            }                       
        
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus { border: 1px solid #3daee9; }
            QProgressBar {
                border: 1px solid #3d4045;
                border-radius: 4px;
                text-align: center;
                color: #efeff1;
            }
            QProgressBar::chunk { background-color: #3daee9; border-radius: 4px; }
            QMenuBar { background-color: #2d2d30; color: #efeff1; }
            QMenuBar::item:selected { background-color: #3a3f44; }
            QMenu { background-color: #2d2d30; color: #efeff1; }
            QMenu::item:selected { background-color: #3daee9; color: white; }
            QStatusBar { background-color: #2d2d30; color: #efeff1; }
            QGroupBox {
                border: 1px solid #3d4045;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                color: #efeff1;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QCheckBox { color: #efeff1; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; }
            QToolTip { background-color: #232629; color: #efeff1; border: 1px solid #3d4045; }
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
            QDialog { background-color: #2d2d30; }
            QLabel { color: #efeff1; }
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
        """)
    else:
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
            QTableView {
                background-color: #f5f5f8;
                border: none;
                alternate-background-color: #eeeef1;
                gridline-color: #d0d0d5;
                color: #1e1e21;
            }
            QTableView::item:selected { background-color: #3daee9; color: white; }
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
            QPushButton#single_btn {
                background-color: #3daee9;
                color: white;
                font-weight: bold;
            }
            QPushButton#single_btn:hover { background-color: #5ab8f0; }
            QLineEdit, QTextEdit, QComboBox, QTimeEdit {
                background-color: #f5f5f8;
                color: #1e1e21;
                border: 1px solid #d0d0d5;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QSpinBox {
                background-color: #f5f5f8;
                color: #1e1e21;
                border: 1px solid #d0d0d5;
                border-radius: 4px;
                padding: 6px 10px;
            }
            QProgressBar {
                border: 1px solid #d0d0d5;
                border-radius: 4px;
                text-align: center;
                color: #1e1e21;
            }
            QProgressBar::chunk { background-color: #3daee9; border-radius: 4px; }
            QMenuBar { background-color: #ebebee; color: #1e1e21; }
            QMenuBar::item:selected { background-color: #d5d5da; }
            QMenu { background-color: #ebebee; color: #1e1e21; }
            QMenu::item:selected { background-color: #3daee9; color: white; }
            QStatusBar { background-color: #ebebee; color: #6a6a70; }
            QGroupBox {
                border: 1px solid #d0d0d5;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 10px;
                color: #1e1e21;
                font-weight: bold;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QCheckBox { color: #1e1e21; spacing: 8px; }
            QCheckBox::indicator { width: 18px; height: 18px; }
            QToolTip { background-color: #ebebee; color: #1e1e21; border: 1px solid #d0d0d5; }
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
            QDialog { background-color: #ebebee; }
            QLabel { color: #1e1e21; }
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
        """)