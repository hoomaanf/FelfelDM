# Requires: PyQt6>=6.4.0

"""
Application-wide stylesheet.
"""

from PyQt6.QtWidgets import QApplication


def apply_style(app: QApplication) -> None:
    style = """
    QWidget {
        background-color: #2b2b2b;
        color: #dcdcdc;
        font-family: "Segoe UI", "Ubuntu", sans-serif;
        font-size: 10pt;
    }
    QMainWindow, QDialog {
        background-color: #2b2b2b;
    }
    QMenuBar {
        background-color: #3c3c3c;
        color: #dcdcdc;
    }
    QMenuBar::item:selected {
        background-color: #4a4a4a;
    }
    QMenu {
        background-color: #3c3c3c;
        color: #dcdcdc;
        border: 1px solid #5a5a5a;
    }
    QMenu::item:selected {
        background-color: #4a4a4a;
    }
    QToolBar {
        background-color: #3c3c3c;
        border: none;
        spacing: 4px;
        padding: 4px;
    }
    QToolBar QToolButton {
        background-color: transparent;
        color: #dcdcdc;
        border: none;
        padding: 4px 8px;
        border-radius: 4px;
    }
    QToolBar QToolButton:hover {
        background-color: #4a4a4a;
    }
    QToolBar QToolButton:pressed {
        background-color: #5a5a5a;
    }
    QTableView {
        background-color: #2b2b2b;
        gridline-color: #3c3c3c;
        selection-background-color: #3c5a8a;
        selection-color: #ffffff;
        alternate-background-color: #333333;
    }
    QTableView::item:selected {
        background-color: #3c5a8a;
        color: #ffffff;
    }
    QHeaderView::section {
        background-color: #3c3c3c;
        color: #dcdcdc;
        padding: 4px;
        border: 1px solid #4a4a4a;
    }
    QLineEdit, QTextEdit, QSpinBox, QComboBox, QTimeEdit {
        background-color: #3c3c3c;
        color: #dcdcdc;
        border: 1px solid #5a5a5a;
        border-radius: 4px;
        padding: 4px;
    }
    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus, QTimeEdit:focus {
        border: 1px solid #5a8a5a;
    }
    QPushButton {
        background-color: #3c3c3c;
        color: #dcdcdc;
        border: 1px solid #5a5a5a;
        border-radius: 4px;
        padding: 6px 12px;
    }
    QPushButton:hover {
        background-color: #4a4a4a;
    }
    QPushButton:pressed {
        background-color: #5a5a5a;
    }
    QProgressBar {
        background-color: #3c3c3c;
        color: #dcdcdc;
        border: 1px solid #5a5a5a;
        border-radius: 4px;
        text-align: center;
    }
    QProgressBar::chunk {
        background-color: #5a8a5a;
        border-radius: 4px;
    }
    QGroupBox {
        border: 1px solid #5a5a5a;
        border-radius: 4px;
        margin-top: 10px;
        padding-top: 10px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 5px;
    }
    QCheckBox {
        spacing: 8px;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
    }
    QTabWidget::pane {
        border: 1px solid #5a5a5a;
        border-radius: 4px;
    }
    QTabBar::tab {
        background-color: #3c3c3c;
        color: #dcdcdc;
        padding: 6px 12px;
        border: 1px solid #5a5a5a;
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
    }
    QTabBar::tab:selected {
        background-color: #4a4a4a;
    }
    QTabBar::tab:hover {
        background-color: #4a4a4a;
    }
    QScrollBar:vertical {
        background-color: #3c3c3c;
        width: 14px;
        border-radius: 7px;
    }
    QScrollBar::handle:vertical {
        background-color: #5a5a5a;
        border-radius: 7px;
        min-height: 20px;
    }
    QScrollBar::handle:vertical:hover {
        background-color: #6a6a6a;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        border: none;
        background: none;
    }
    QScrollBar:horizontal {
        background-color: #3c3c3c;
        height: 14px;
        border-radius: 7px;
    }
    QScrollBar::handle:horizontal {
        background-color: #5a5a5a;
        border-radius: 7px;
        min-width: 20px;
    }
    QScrollBar::handle:horizontal:hover {
        background-color: #6a6a6a;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        border: none;
        background: none;
    }
    QStatusBar {
        background-color: #3c3c3c;
        color: #dcdcdc;
    }
    QToolTip {
        background-color: #3c3c3c;
        color: #dcdcdc;
        border: 1px solid #5a5a5a;
        border-radius: 4px;
        padding: 4px;
    }
    QMessageBox {
        background-color: #2b2b2b;
    }
    QMessageBox QPushButton {
        min-width: 80px;
    }
    """
    app.setStyleSheet(style)
