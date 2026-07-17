# ui/dialogs.py

import os
import subprocess
import time
import socket

from PyQt6.QtWidgets import *
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtCore import *
from utils.helpers import get_icon
from core.queue_model import Queue
from datetime import datetime, time as dtime
from core.proxy_manager import ProxyType, ProxyConfig


class AccordionGroup(QWidget):
    """اکاردئون واقعی با فلش بالا/پایین"""

    def __init__(self, title, parent=None, expanded=True):
        super().__init__(parent)
        self._expanded = expanded

        self.toggle_btn = QPushButton()
        self.toggle_btn.setStyleSheet("""
            QPushButton {
                text-align: left;
                font-weight: 600;
                padding: 8px 10px;
                border: none;
                border-radius: 4px;
                background: transparent;
                font-size: 13px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.05);
            }
            QPushButton:pressed {
                background: rgba(255,255,255,0.08);
            }
        """)
        self.toggle_btn.clicked.connect(self._toggle)
        self.toggle_btn.setFixedHeight(32)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(10, 5, 10, 10)
        self.content_layout.setSpacing(8)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self.toggle_btn)

        self.line = QFrame()
        self.line.setFrameShape(QFrame.Shape.HLine)
        self.line.setFrameShadow(QFrame.Shadow.Sunken)
        self.line.setStyleSheet("background-color: #313244; max-height: 1px;")
        main_layout.addWidget(self.line)

        main_layout.addWidget(self.content)

        self.set_title(title)
        self.set_expanded(expanded)

    def set_title(self, title):
        self.toggle_btn.setText(f"  {title}")
        self._update_icon()

    def _update_icon(self):
        icon = get_icon("go-down") if self._expanded else get_icon("go-next")
        self.toggle_btn.setIcon(icon)

    def _toggle(self):
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded):
        self._expanded = expanded
        self.content.setVisible(expanded)
        self.line.setVisible(expanded)
        self._update_icon()

    def is_expanded(self):
        return self._expanded

    def addWidget(self, widget):
        self.content_layout.addWidget(widget)

    def addLayout(self, layout):
        self.content_layout.addLayout(layout)

    def layout(self):
        return self.content_layout


# ============================================================
# AddDownloadDialog
# ============================================================

class AddDownloadDialog(QDialog):
    def __init__(self, queues, default_queue=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Downloads")
        self.setMinimumWidth(620)
        self.setMinimumHeight(420)

        self.queues = queues
        self.default_queue = default_queue
        self._custom_proxy = None

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(16, 12, 16, 16)

        # ===== URLs =====
        url_acc = AccordionGroup("URLs")
        url_acc.set_expanded(True)

        self.url_edit = QTextEdit()
        self.url_edit.setPlaceholderText("Enter URLs (one per line)...")
        self.url_edit.setMinimumHeight(100)
        url_acc.addWidget(self.url_edit)

        self.import_btn = QPushButton(get_icon("document-open"), " Import from File")
        self.import_btn.clicked.connect(self._import_from_txt)
        url_acc.addWidget(self.import_btn)

        main_layout.addWidget(url_acc)

        # ===== Settings =====
        settings_acc = AccordionGroup("Settings")
        settings_acc.set_expanded(True)

        row1 = QHBoxLayout()
        row1.setSpacing(12)

        queue_widget = QWidget()
        queue_widget.setMinimumWidth(180)
        queue_layout = QVBoxLayout(queue_widget)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_layout.setSpacing(2)
        queue_layout.addWidget(QLabel("Queue:"))
        self.queue_cb = QComboBox()
        for q in self.queues:
            if q.name != "__direct__":
                self.queue_cb.addItem(q.name)
        if self.default_queue < self.queue_cb.count():
            self.queue_cb.setCurrentIndex(self.default_queue)
        queue_layout.addWidget(self.queue_cb)
        row1.addWidget(queue_widget)

        conn_widget = QWidget()
        conn_widget.setMinimumWidth(120)
        conn_layout = QVBoxLayout(conn_widget)
        conn_layout.setContentsMargins(0, 0, 0, 0)
        conn_layout.setSpacing(2)
        conn_layout.addWidget(QLabel("Connections:"))
        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 16)
        self.conn_spin.setValue(8)
        conn_layout.addWidget(self.conn_spin)
        row1.addWidget(conn_widget)

        row1.addStretch()
        settings_acc.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        row2.addWidget(QLabel("Save to:"))
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        row2.addWidget(self.path_edit)
        self.browse_btn = QPushButton()
        self.browse_btn.setIcon(get_icon("folder-open"))
        self.browse_btn.setFixedSize(28, 28)
        self.browse_btn.clicked.connect(self._browse)
        row2.addWidget(self.browse_btn)
        settings_acc.addLayout(row2)

        main_layout.addWidget(settings_acc)

        # ===== Proxy =====
        proxy_acc = AccordionGroup("Proxy Settings")
        proxy_acc.set_expanded(False)

        self.proxy_combo = QComboBox()
        self.proxy_combo.addItems(
            ["Use Global/Queue Proxy", "Custom Proxy", "No Proxy"]
        )
        self.proxy_combo.currentIndexChanged.connect(self._on_proxy_mode_changed)
        proxy_acc.addWidget(self.proxy_combo)

        proxy_btn_row = QHBoxLayout()
        proxy_btn_row.setSpacing(6)

        self.proxy_config_btn = QPushButton(get_icon("configure"), " Configure")
        self.proxy_config_btn.setEnabled(False)
        self.proxy_config_btn.clicked.connect(self._configure_custom_proxy)
        proxy_btn_row.addWidget(self.proxy_config_btn)

        self.proxy_clear_btn = QPushButton(get_icon("edit-clear"), " Clear")
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_clear_btn.clicked.connect(self._clear_custom_proxy)
        proxy_btn_row.addWidget(self.proxy_clear_btn)

        proxy_btn_row.addStretch()
        proxy_acc.addLayout(proxy_btn_row)

        self.proxy_status_label = QLabel("")
        self.proxy_status_label.setWordWrap(True)
        self.proxy_status_label.setStyleSheet("font-size: 11px; padding: 2px;")
        proxy_acc.addWidget(self.proxy_status_label)

        main_layout.addWidget(proxy_acc)

        # ===== Info & Buttons =====
        self.info_label = QLabel("Downloads will be added in Paused state")
        self.info_label.setStyleSheet("color: #95a5a6; font-size: 11px; padding: 4px;")
        main_layout.addWidget(self.info_label)

        self.btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        main_layout.addWidget(self.btn_box)

        self._setup_tab_order()

    def _setup_tab_order(self):
        self.setTabOrder(self.url_edit, self.import_btn)
        self.setTabOrder(self.import_btn, self.queue_cb)
        self.setTabOrder(self.queue_cb, self.conn_spin)
        self.setTabOrder(self.conn_spin, self.path_edit)
        self.setTabOrder(self.path_edit, self.browse_btn)
        self.setTabOrder(self.browse_btn, self.proxy_combo)
        self.setTabOrder(self.proxy_combo, self.proxy_config_btn)
        self.setTabOrder(self.proxy_config_btn, self.proxy_clear_btn)
        self.setTabOrder(self.proxy_clear_btn, self.btn_box)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def _import_from_txt(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Links File", "", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    current = self.url_edit.toPlainText().strip()
                    combined = (
                        current + "\n" + "\n".join(lines)
                        if current
                        else "\n".join(lines)
                    )
                    self.url_edit.setPlainText(combined)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to parse file:\n{str(e)}")

    def _on_proxy_mode_changed(self, index):
        is_custom = index == 1
        self.proxy_config_btn.setEnabled(is_custom)
        self.proxy_clear_btn.setEnabled(is_custom and self._custom_proxy is not None)
        if not is_custom:
            self.proxy_status_label.setText("")
        elif self._custom_proxy:
            self._update_proxy_status()

    def _configure_custom_proxy(self):
        from ui.download_proxy_dialog import SimpleProxyDialog

        url = (
            self.url_edit.toPlainText().strip().split("\n")[0]
            if self.url_edit.toPlainText()
            else "Download"
        )
        display_name = os.path.basename(url) if url else "Download"
        dlg = SimpleProxyDialog(display_name, self._custom_proxy, self)
        if dlg.exec():
            new_config = dlg.get_proxy_config()
            self._custom_proxy = new_config
            self.proxy_clear_btn.setEnabled(True)
            self._update_proxy_status()

    def _clear_custom_proxy(self):
        self._custom_proxy = None
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_status_label.setText("")

    def _update_proxy_status(self):
        if self._custom_proxy and self._custom_proxy.is_valid():
            self.proxy_status_label.setText(
                f"✓ {self._custom_proxy.get_display_string()}"
            )
            self.proxy_status_label.setStyleSheet("color: #27ae60; font-size: 11px;")
        else:
            self.proxy_status_label.setText("Invalid proxy configuration")
            self.proxy_status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")

    def _get_urls(self):
        raw = self.url_edit.toPlainText()
        return [line.strip() for line in raw.split("\n") if line.strip()]

    def get_data(self):
        urls = self._get_urls()
        proxy_mode = self.proxy_combo.currentIndex()
        return {
            "urls": urls,
            "path": self.path_edit.text().strip(),
            "queue": self.queue_cb.currentIndex(),
            "connections": self.conn_spin.value(),
            "proxy_mode": proxy_mode,
            "custom_proxy": self._custom_proxy if proxy_mode == 1 else None,
        }


# ============================================================
# QuickDownloadDialog
# ============================================================

class QuickDownloadDialog(QDialog):
    def __init__(self, queues, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Download")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        self.queues = queues
        self._custom_proxy = None

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(16, 12, 16, 16)

        # ===== URLs =====
        url_acc = AccordionGroup("URLs")
        url_acc.set_expanded(True)

        self.url_edit = QTextEdit()
        self.url_edit.setPlaceholderText("Enter URLs (one per line)...")
        self.url_edit.setMinimumHeight(90)
        url_acc.addWidget(self.url_edit)

        main_layout.addWidget(url_acc)

        # ===== Settings =====
        settings_acc = AccordionGroup("Settings")
        settings_acc.set_expanded(True)

        row1 = QHBoxLayout()
        row1.setSpacing(12)

        queue_widget = QWidget()
        queue_widget.setMinimumWidth(180)
        queue_layout = QVBoxLayout(queue_widget)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        queue_layout.setSpacing(2)
        queue_layout.addWidget(QLabel("Queue:"))
        self.queue_combo = QComboBox()
        self.queue_combo.addItem("Direct Downloads", "__direct__")
        for q in self.queues:
            if q.name != "__direct__":
                self.queue_combo.addItem(q.name, q.name)
        queue_layout.addWidget(self.queue_combo)
        row1.addWidget(queue_widget)

        conn_widget = QWidget()
        conn_widget.setMinimumWidth(120)
        conn_layout = QVBoxLayout(conn_widget)
        conn_layout.setContentsMargins(0, 0, 0, 0)
        conn_layout.setSpacing(2)
        conn_layout.addWidget(QLabel("Connections:"))
        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 16)
        self.conn_spin.setValue(8)
        conn_layout.addWidget(self.conn_spin)
        row1.addWidget(conn_widget)

        row1.addStretch()
        settings_acc.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        row2.addWidget(QLabel("Save to:"))
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        row2.addWidget(self.path_edit)
        self.browse_btn = QPushButton()
        self.browse_btn.setIcon(get_icon("folder-open"))
        self.browse_btn.setFixedSize(28, 28)
        self.browse_btn.clicked.connect(self._browse)
        row2.addWidget(self.browse_btn)
        settings_acc.addLayout(row2)

        # ===== حذف چک‌باکس Start Immediately =====

        main_layout.addWidget(settings_acc)

        # ===== Proxy =====
        proxy_acc = AccordionGroup("Proxy Settings")
        proxy_acc.set_expanded(False)

        self.proxy_combo = QComboBox()
        self.proxy_combo.addItems(["Use Global Proxy", "Custom Proxy", "No Proxy"])
        self.proxy_combo.currentIndexChanged.connect(self._on_proxy_mode_changed)
        proxy_acc.addWidget(self.proxy_combo)

        proxy_btn_row = QHBoxLayout()
        proxy_btn_row.setSpacing(6)

        self.proxy_config_btn = QPushButton(get_icon("configure"), " Configure")
        self.proxy_config_btn.setEnabled(False)
        self.proxy_config_btn.clicked.connect(self._configure_custom_proxy)
        proxy_btn_row.addWidget(self.proxy_config_btn)

        self.proxy_clear_btn = QPushButton(get_icon("edit-clear"), " Clear")
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_clear_btn.clicked.connect(self._clear_custom_proxy)
        proxy_btn_row.addWidget(self.proxy_clear_btn)

        proxy_btn_row.addStretch()
        proxy_acc.addLayout(proxy_btn_row)

        self.proxy_status_label = QLabel("")
        self.proxy_status_label.setWordWrap(True)
        self.proxy_status_label.setStyleSheet("font-size: 11px; padding: 2px;")
        proxy_acc.addWidget(self.proxy_status_label)

        main_layout.addWidget(proxy_acc)

        # ===== Buttons =====
        self.btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        main_layout.addWidget(self.btn_box)

        self._setup_tab_order()

    def _setup_tab_order(self):
        self.setTabOrder(self.url_edit, self.queue_combo)
        self.setTabOrder(self.queue_combo, self.conn_spin)
        self.setTabOrder(self.conn_spin, self.path_edit)
        self.setTabOrder(self.path_edit, self.browse_btn)
        self.setTabOrder(self.browse_btn, self.proxy_combo)
        self.setTabOrder(self.proxy_combo, self.proxy_config_btn)
        self.setTabOrder(self.proxy_config_btn, self.proxy_clear_btn)
        self.setTabOrder(self.proxy_clear_btn, self.btn_box)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def _on_proxy_mode_changed(self, index):
        is_custom = index == 1
        self.proxy_config_btn.setEnabled(is_custom)
        self.proxy_clear_btn.setEnabled(is_custom and self._custom_proxy is not None)
        if not is_custom:
            self.proxy_status_label.setText("")
        elif self._custom_proxy:
            self._update_proxy_status()

    def _configure_custom_proxy(self):
        from ui.download_proxy_dialog import DownloadProxyDialog

        urls = self._get_urls()
        display_name = os.path.basename(urls[0]) if urls else "Download"
        dlg = DownloadProxyDialog(display_name, self._custom_proxy, self)
        if dlg.exec():
            data = dlg.get_data()
            if data["use_custom"] and data["config"]:
                self._custom_proxy = data["config"]
                self.proxy_clear_btn.setEnabled(True)
                self._update_proxy_status()

    def _clear_custom_proxy(self):
        self._custom_proxy = None
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_status_label.setText("")

    def _update_proxy_status(self):
        if self._custom_proxy and self._custom_proxy.is_valid():
            self.proxy_status_label.setText(
                f"✓ {self._custom_proxy.get_display_string()}"
            )
            self.proxy_status_label.setStyleSheet("color: #27ae60; font-size: 11px;")

    def _get_urls(self):
        raw = self.url_edit.toPlainText()
        return [line.strip() for line in raw.split("\n") if line.strip()]

    def get_data(self):
        urls = self._get_urls()
        proxy_mode = self.proxy_combo.currentIndex()
        return {
            "urls": urls,
            "path": self.path_edit.text().strip(),
            "connections": self.conn_spin.value(),
            "queue_name": self.queue_combo.currentData(),
            "proxy_mode": proxy_mode,
            "custom_proxy": self._custom_proxy if proxy_mode == 1 else None,
        }
# ============================================================
# SingleDownloadDialog
# ============================================================

class SingleDownloadDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Single Download")
        self.setMinimumWidth(560)
        self.setMinimumHeight(380)

        self._custom_proxy = None

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(16, 12, 16, 16)

        # ===== URL =====
        url_acc = AccordionGroup("URL")
        url_acc.set_expanded(True)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/file.zip")
        url_acc.addWidget(self.url_edit)

        main_layout.addWidget(url_acc)

        # ===== Settings =====
        settings_acc = AccordionGroup("Settings")
        settings_acc.set_expanded(True)

        row1 = QHBoxLayout()
        row1.setSpacing(12)

        conn_widget = QWidget()
        conn_widget.setMinimumWidth(150)
        conn_layout = QVBoxLayout(conn_widget)
        conn_layout.setContentsMargins(0, 0, 0, 0)
        conn_layout.setSpacing(2)
        conn_layout.addWidget(QLabel("Connections:"))
        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 16)
        self.conn_spin.setValue(8)
        conn_layout.addWidget(self.conn_spin)
        row1.addWidget(conn_widget)

        row1.addStretch()
        settings_acc.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        row2.addWidget(QLabel("Save to:"))
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        row2.addWidget(self.path_edit)
        self.browse_btn = QPushButton()
        self.browse_btn.setIcon(get_icon("folder-open"))
        self.browse_btn.setFixedSize(28, 28)
        self.browse_btn.clicked.connect(self._browse)
        row2.addWidget(self.browse_btn)
        settings_acc.addLayout(row2)

        self.start_immediately = QCheckBox("Start download immediately")
        self.start_immediately.setChecked(True)
        settings_acc.addWidget(self.start_immediately)

        main_layout.addWidget(settings_acc)

        # ===== Proxy =====
        proxy_acc = AccordionGroup("Proxy Settings")
        proxy_acc.set_expanded(False)

        self.proxy_combo = QComboBox()
        self.proxy_combo.addItems(
            ["Use Global/Queue Proxy", "Custom Proxy", "No Proxy"]
        )
        self.proxy_combo.currentIndexChanged.connect(self._on_proxy_mode_changed)
        proxy_acc.addWidget(self.proxy_combo)

        proxy_btn_row = QHBoxLayout()
        proxy_btn_row.setSpacing(6)

        self.proxy_config_btn = QPushButton(get_icon("configure"), " Configure")
        self.proxy_config_btn.setEnabled(False)
        self.proxy_config_btn.clicked.connect(self._configure_custom_proxy)
        proxy_btn_row.addWidget(self.proxy_config_btn)

        self.proxy_clear_btn = QPushButton(get_icon("edit-clear"), " Clear")
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_clear_btn.clicked.connect(self._clear_custom_proxy)
        proxy_btn_row.addWidget(self.proxy_clear_btn)

        proxy_btn_row.addStretch()
        proxy_acc.addLayout(proxy_btn_row)

        self.proxy_status_label = QLabel("")
        self.proxy_status_label.setWordWrap(True)
        self.proxy_status_label.setStyleSheet("font-size: 11px; padding: 2px;")
        proxy_acc.addWidget(self.proxy_status_label)

        main_layout.addWidget(proxy_acc)

        # ===== Buttons =====
        self.btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.btn_box.accepted.connect(self.accept)
        self.btn_box.rejected.connect(self.reject)
        main_layout.addWidget(self.btn_box)

        self._setup_tab_order()

    def _setup_tab_order(self):
        self.setTabOrder(self.url_edit, self.conn_spin)
        self.setTabOrder(self.conn_spin, self.path_edit)
        self.setTabOrder(self.path_edit, self.browse_btn)
        self.setTabOrder(self.browse_btn, self.start_immediately)
        self.setTabOrder(self.start_immediately, self.proxy_combo)
        self.setTabOrder(self.proxy_combo, self.proxy_config_btn)
        self.setTabOrder(self.proxy_config_btn, self.proxy_clear_btn)
        self.setTabOrder(self.proxy_clear_btn, self.btn_box)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def _on_proxy_mode_changed(self, index):
        is_custom = index == 1
        self.proxy_config_btn.setEnabled(is_custom)
        self.proxy_clear_btn.setEnabled(is_custom and self._custom_proxy is not None)
        if not is_custom:
            self.proxy_status_label.setText("")
        elif self._custom_proxy:
            self._update_proxy_status()

    def _configure_custom_proxy(self):
        from ui.download_proxy_dialog import DownloadProxyDialog

        url = self.url_edit.text().strip()
        display_name = os.path.basename(url) if url else "Download"
        dlg = DownloadProxyDialog(display_name, self._custom_proxy, self)
        if dlg.exec():
            data = dlg.get_data()
            if data["use_custom"] and data["config"]:
                self._custom_proxy = data["config"]
                self.proxy_clear_btn.setEnabled(True)
                self._update_proxy_status()

    def _clear_custom_proxy(self):
        self._custom_proxy = None
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_status_label.setText("")

    def _update_proxy_status(self):
        if self._custom_proxy and self._custom_proxy.is_valid():
            self.proxy_status_label.setText(
                f"✓ {self._custom_proxy.get_display_string()}"
            )
            self.proxy_status_label.setStyleSheet("color: #27ae60; font-size: 11px;")

    def get_data(self):
        proxy_mode = self.proxy_combo.currentIndex()
        return {
            "url": self.url_edit.text().strip(),
            "path": self.path_edit.text().strip(),
            "connections": self.conn_spin.value(),
            "start_immediately": self.start_immediately.isChecked(),
            "proxy_mode": proxy_mode,
            "custom_proxy": self._custom_proxy if proxy_mode == 1 else None,
        }


# ============================================================
# YouTubeDownloadDialog
# ============================================================

class YouTubeDownloadDialog(QDialog):
    youtube_download_requested = pyqtSignal(dict)

    def __init__(self, parent=None, queues=None, default_queue=0):
        super().__init__(parent)
        self.setWindowTitle("YouTube Download")
        self.setMinimumWidth(600)
        self.setMinimumHeight(420)

        self.queues = queues or []
        self.default_queue = default_queue
        self.video_info = None
        self._custom_proxy = None
        self._format_map = {}
        self.worker = None

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(16, 12, 16, 16)

        # ===== Video =====
        video_acc = AccordionGroup("Video")
        video_acc.set_expanded(True)

        url_row = QHBoxLayout()
        url_row.setSpacing(6)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://www.youtube.com/watch?v=...")
        url_row.addWidget(self.url_edit)

        self.fetch_btn = QPushButton(get_icon("view-refresh"), " Get Info")
        self.fetch_btn.setFixedHeight(32)
        self.fetch_btn.clicked.connect(self._fetch_info)
        url_row.addWidget(self.fetch_btn)
        video_acc.addLayout(url_row)

        info_group = QGroupBox("Video Info")
        self.info_layout = QFormLayout(info_group)
        self.info_layout.setSpacing(6)

        self.info_placeholder = QLabel("Enter a YouTube URL and click 'Get Info'")
        self.info_placeholder.setStyleSheet("color: #95a5a6; font-size: 11px;")
        self.info_layout.addRow(self.info_placeholder)

        video_acc.addWidget(info_group)

        main_layout.addWidget(video_acc)

        # ===== Options =====
        opts_acc = AccordionGroup("Options")
        opts_acc.set_expanded(True)

        self.format_combo = QComboBox()
        self.format_combo.setEnabled(False)
        opts_acc.addWidget(self.format_combo)

        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        path_row.addWidget(self.path_edit)
        self.browse_btn = QPushButton()
        self.browse_btn.setIcon(get_icon("folder-open"))
        self.browse_btn.setFixedSize(28, 28)
        self.browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.browse_btn)
        opts_acc.addLayout(path_row)

        cookie_row = QHBoxLayout()
        cookie_row.setSpacing(6)
        self.cookie_edit = QLineEdit()
        self.cookie_edit.setPlaceholderText("Optional: cookies.txt path")
        cookie_row.addWidget(self.cookie_edit)
        self.cookie_browse = QPushButton()
        self.cookie_browse.setIcon(get_icon("folder-open"))
        self.cookie_browse.setFixedSize(28, 28)
        self.cookie_browse.clicked.connect(self._browse_cookie)
        cookie_row.addWidget(self.cookie_browse)
        opts_acc.addLayout(cookie_row)

        self.queue_combo = QComboBox()
        for i, q in enumerate(self.queues):
            if q.name != "__direct__":
                self.queue_combo.addItem(q.name, i)
        if self.default_queue < self.queue_combo.count():
            self.queue_combo.setCurrentIndex(self.default_queue)
        opts_acc.addWidget(self.queue_combo)

        main_layout.addWidget(opts_acc)

        # ===== Proxy =====
        proxy_acc = AccordionGroup("Proxy Settings")
        proxy_acc.set_expanded(False)

        self.proxy_combo = QComboBox()
        self.proxy_combo.addItems(["Use Global Proxy", "Custom Proxy", "No Proxy"])
        self.proxy_combo.currentIndexChanged.connect(self._on_proxy_mode_changed)
        proxy_acc.addWidget(self.proxy_combo)

        proxy_btn_row = QHBoxLayout()
        proxy_btn_row.setSpacing(6)

        self.proxy_config_btn = QPushButton(get_icon("configure"), " Configure")
        self.proxy_config_btn.setEnabled(False)
        self.proxy_config_btn.clicked.connect(self._configure_custom_proxy)
        proxy_btn_row.addWidget(self.proxy_config_btn)

        self.proxy_clear_btn = QPushButton(get_icon("edit-clear"), " Clear")
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_clear_btn.clicked.connect(self._clear_custom_proxy)
        proxy_btn_row.addWidget(self.proxy_clear_btn)

        proxy_btn_row.addStretch()
        proxy_acc.addLayout(proxy_btn_row)

        self.proxy_status_label = QLabel("")
        self.proxy_status_label.setWordWrap(True)
        self.proxy_status_label.setStyleSheet("font-size: 11px; padding: 2px;")
        proxy_acc.addWidget(self.proxy_status_label)

        main_layout.addWidget(proxy_acc)

        # ===== Buttons =====
        self.btn_box = QDialogButtonBox()
        self.download_btn = self.btn_box.addButton(
            "Add to Queue", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.download_btn.setIcon(get_icon("download"))
        self.download_btn.setEnabled(False)
        self.download_btn.clicked.connect(self._on_add_to_queue)

        self.cancel_btn = self.btn_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        self.cancel_btn.setIcon(get_icon("dialog-cancel"))
        self.cancel_btn.clicked.connect(self.reject)

        main_layout.addWidget(self.btn_box)

        self._setup_tab_order()

    def _setup_tab_order(self):
        self.setTabOrder(self.url_edit, self.fetch_btn)
        self.setTabOrder(self.fetch_btn, self.format_combo)
        self.setTabOrder(self.format_combo, self.path_edit)
        self.setTabOrder(self.path_edit, self.browse_btn)
        self.setTabOrder(self.browse_btn, self.cookie_edit)
        self.setTabOrder(self.cookie_edit, self.cookie_browse)
        self.setTabOrder(self.cookie_browse, self.queue_combo)
        self.setTabOrder(self.queue_combo, self.proxy_combo)
        self.setTabOrder(self.proxy_combo, self.proxy_config_btn)
        self.setTabOrder(self.proxy_config_btn, self.proxy_clear_btn)
        self.setTabOrder(self.proxy_clear_btn, self.download_btn)
        self.setTabOrder(self.download_btn, self.cancel_btn)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def _browse_cookie(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Cookies File", "", "Cookies Files (*.txt);;All Files (*)"
        )
        if file_path:
            self.cookie_edit.setText(file_path)

    def _on_proxy_mode_changed(self, index):
        is_custom = index == 1
        self.proxy_config_btn.setEnabled(is_custom)
        self.proxy_clear_btn.setEnabled(is_custom and self._custom_proxy is not None)
        if not is_custom:
            self.proxy_status_label.setText("")
        elif self._custom_proxy:
            self._update_proxy_status()

    def _configure_custom_proxy(self):
        from ui.download_proxy_dialog import SimpleProxyDialog

        url = self.url_edit.text().strip()
        display_name = os.path.basename(url) if url else "YouTube Download"
        dlg = SimpleProxyDialog(display_name, self._custom_proxy, self)
        if dlg.exec():
            new_config = dlg.get_proxy_config()
            self._custom_proxy = new_config
            self.proxy_clear_btn.setEnabled(True)
            self._update_proxy_status()

    def _clear_custom_proxy(self):
        self._custom_proxy = None
        self.proxy_clear_btn.setEnabled(False)
        self.proxy_status_label.setText("")

    def _update_proxy_status(self):
        if self._custom_proxy and self._custom_proxy.is_valid():
            self.proxy_status_label.setText(
                f"✓ {self._custom_proxy.get_display_string()}"
            )
            self.proxy_status_label.setStyleSheet("color: #27ae60; font-size: 11px;")

    def _get_proxy_url(self):
        proxy_mode = self.proxy_combo.currentIndex()
        if proxy_mode == 0:
            if hasattr(self.parent(), "proxy_manager"):
                proxy = self.parent().proxy_manager.get_proxy_for_queue(None)
                if proxy and proxy.is_valid():
                    return proxy._build_proxy_url()
        elif proxy_mode == 1:
            if self._custom_proxy and self._custom_proxy.is_valid():
                return self._custom_proxy._build_proxy_url()
        return None

    def clear_info_layout(self):
        while self.info_layout.rowCount() > 0:
            self.info_layout.removeRow(self.info_layout.rowCount() - 1)

    def _fetch_info(self):
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a YouTube URL")
            return

        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("Fetching...")

        self.clear_info_layout()
        self.info_placeholder = QLabel("Getting video info...")
        self.info_placeholder.setStyleSheet("color: #3daee9; font-size: 11px;")
        self.info_layout.addRow(self.info_placeholder)

        try:
            from core.youtube_worker import YouTubeWorker

            cookie_file = self.cookie_edit.text().strip() or None
            proxy_url = self._get_proxy_url()

            self.worker = YouTubeWorker(url, "", "mp4", cookie_file, proxy_url)
            self.worker.is_fetching_info = True
            self.worker.info_fetched.connect(self._on_info_fetched)
            self.worker.finished.connect(self._on_info_fetch_finished)
            self.worker.start()

        except Exception as e:
            self.clear_info_layout()
            self.info_placeholder = QLabel(f"Error: {str(e)}")
            self.info_placeholder.setStyleSheet("color: #e74c3c; font-size: 11px;")
            self.info_layout.addRow(self.info_placeholder)
            self.fetch_btn.setEnabled(True)
            self.fetch_btn.setText("Get Info")

    def _on_info_fetched(self, info):
        self.video_info = info
        self.clear_info_layout()

        title = info.get("title", "Unknown")
        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet("font-weight: 600;")
        self.info_layout.addRow("Title:", title_label)

        uploader = info.get("uploader", "Unknown")
        self.info_layout.addRow("Channel:", QLabel(uploader))

        duration = info.get("duration", 0)
        minutes = duration // 60
        seconds = duration % 60
        self.info_layout.addRow("Duration:", QLabel(f"{minutes}:{seconds:02d}"))

        formats = info.get("formats", [])
        self.format_combo.clear()
        self._format_map = {}

        video_formats = []
        audio_formats = []

        for f in formats:
            format_id = f.get("format_id")
            resolution = f.get("resolution")
            ext = f.get("ext")
            filesize = f.get("filesize")
            vcodec = f.get("vcodec")
            acodec = f.get("acodec")

            if vcodec and vcodec != "none":
                label = f"Video ({ext.upper()})"
                if resolution and resolution != "audio only":
                    label += f" - {resolution}"
                if filesize:
                    from utils.helpers import format_size

                    label += f" ({format_size(filesize)})"
                video_formats.append((format_id, label, f))

            elif acodec and acodec != "none" and (not vcodec or vcodec == "none"):
                bitrate = f.get("abr")
                label = f"Audio ({ext.upper()})"
                if bitrate:
                    label += f" - {bitrate}kbps"
                if filesize:
                    from utils.helpers import format_size

                    label += f" ({format_size(filesize)})"
                audio_formats.append((format_id, label, f))

        def sort_key(item):
            resolution = item[2].get("resolution", "")
            if "p" in resolution:
                return int(resolution.replace("p", ""))
            return 0

        video_formats.sort(key=sort_key, reverse=True)

        for format_id, label, f in video_formats:
            self.format_combo.addItem(label, format_id)
            self._format_map[format_id] = f

        if audio_formats:
            self.format_combo.addItem("--- Audio Only ---", None)
            for format_id, label, f in audio_formats:
                self.format_combo.addItem(label, format_id)
                self._format_map[format_id] = f

        if video_formats:
            self.format_combo.insertItem(0, "Best Quality", "best")

        self.format_combo.setCurrentIndex(0)

        if video_formats:
            quality_labels = [
                f[2].get("resolution", "Unknown") for f in video_formats[:5]
            ]
            self.info_layout.addRow("Qualities:", QLabel(", ".join(quality_labels)))

        filesize = info.get("filesize")
        if filesize:
            from utils.helpers import format_size

            self.info_layout.addRow("Size:", QLabel(format_size(filesize)))

        self.format_combo.setEnabled(True)
        self.download_btn.setEnabled(True)
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Get Info")

    def _on_info_fetch_finished(self, success, message):
        if not success:
            self.clear_info_layout()
            self.info_placeholder = QLabel(f"Error: {message}")
            self.info_placeholder.setStyleSheet("color: #e74c3c; font-size: 11px;")
            self.info_layout.addRow(self.info_placeholder)
            self.download_btn.setEnabled(False)

        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("Get Info")

    def _on_add_to_queue(self):
        data = self.get_data()
        if not data["url"]:
            QMessageBox.warning(self, "Error", "Please enter a valid YouTube URL")
            return

        download_data = {
            "url": data["url"],
            "save_path": data["path"],
            "queue_id": data["queue_name"],
            "download_type": "youtube",
            "yt_options": {
                "quality": data.get("quality", "best"),
                "format": data.get("format", "video"),
                "cookies_path": data.get("cookie_file"),
                "title": data.get("video_info", {}).get("title", ""),
                "format_id": data.get("format_id"),
                "format_info": data.get("format_info", {}),
            },
            "proxy": data.get("proxy_url"),
            "video_info": data.get("video_info"),
        }

        self.youtube_download_requested.emit(download_data)
        self.accept()

    def get_data(self):
        proxy_mode = self.proxy_combo.currentIndex()
        selected_format_id = self.format_combo.currentData()
        format_type = "video"
        quality = "best"

        if selected_format_id == "best":
            quality = "best"
            format_type = "video"
        else:
            format_info = self._format_map.get(selected_format_id, {})
            if format_info.get("vcodec") and format_info.get("vcodec") != "none":
                format_type = "video"
                quality = format_info.get("resolution", "best")
            else:
                format_type = "audio"
                quality = format_info.get("abr", "best")

        return {
            "url": self.url_edit.text().strip(),
            "path": self.path_edit.text().strip(),
            "format": format_type,
            "quality": quality,
            "format_id": selected_format_id,
            "format_info": self._format_map.get(selected_format_id, {}),
            "cookie_file": self.cookie_edit.text().strip() or None,
            "video_info": self.video_info,
            "proxy_mode": proxy_mode,
            "custom_proxy": self._custom_proxy if proxy_mode == 1 else None,
            "proxy_url": self._get_proxy_url(),
            "queue_name": self.queue_combo.currentText(),
        }


# ============================================================
# QueueSettingsDialog (تب‌بندی)
# ============================================================

class QueueSettingsDialog(QDialog):
    def __init__(self, queue: Queue, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Queue Settings — {queue.name}")
        self.setMinimumWidth(540)
        self.setMinimumHeight(440)

        self.queue = queue
        self._queue_proxy_config = None

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 12, 16, 16)

        tabs = QTabWidget()

        # ---- General ----
        general_tab = QWidget()
        general_layout = QFormLayout(general_tab)
        general_layout.setSpacing(10)
        general_layout.setContentsMargins(12, 12, 12, 12)

        self.name_edit = QLineEdit(queue.name)
        general_layout.addRow("Queue Name:", self.name_edit)

        path_row = QHBoxLayout()
        path_row.setSpacing(6)
        self.path_edit = QLineEdit(queue.save_path)
        path_row.addWidget(self.path_edit)
        browse = QPushButton()
        browse.setIcon(get_icon("folder-open"))
        browse.setFixedSize(28, 28)
        browse.clicked.connect(self._browse)
        path_row.addWidget(browse)
        general_layout.addRow("Save Directory:", path_row)

        self.conc_spin = QSpinBox()
        self.conc_spin.setRange(1, 20)
        self.conc_spin.setValue(queue.max_concurrent)
        general_layout.addRow("Max Concurrent:", self.conc_spin)

        tabs.addTab(general_tab, get_icon("configure"), "General")

        # ---- Schedule ----
        sched_tab = QWidget()
        sched_layout = QVBoxLayout(sched_tab)
        sched_layout.setSpacing(10)
        sched_layout.setContentsMargins(12, 12, 12, 12)

        self.sched_cb = QCheckBox("Enable Schedule")
        self.sched_cb.setChecked(queue.schedule_enabled)
        sched_layout.addWidget(self.sched_cb)

        time_row = QHBoxLayout()
        time_row.setSpacing(6)

        self.start_time = QTimeEdit(
            QTime(queue.schedule_start.hour, queue.schedule_start.minute)
        )
        self.end_time = QTimeEdit(
            QTime(queue.schedule_end.hour, queue.schedule_end.minute)
        )
        self.start_time.setDisplayFormat("HH:mm")
        self.end_time.setDisplayFormat("HH:mm")

        time_row.addWidget(QLabel("From:"))
        time_row.addWidget(self.start_time)
        time_row.addWidget(QLabel("To:"))
        time_row.addWidget(self.end_time)
        time_row.addStretch()
        sched_layout.addLayout(time_row)

        days_row = QHBoxLayout()
        days_row.setSpacing(4)
        self.day_checks = []
        for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            cb = QCheckBox(d)
            cb.setChecked(i in queue.days)
            self.day_checks.append(cb)
            days_row.addWidget(cb)
        days_row.addStretch()
        sched_layout.addLayout(days_row)

        sched_layout.addStretch()
        tabs.addTab(sched_tab, get_icon("alarm-clock"), "Schedule")

        # ---- Speed ----
        speed_tab = QWidget()
        speed_layout = QVBoxLayout(speed_tab)
        speed_layout.setSpacing(10)
        speed_layout.setContentsMargins(12, 12, 12, 12)

        speed_row = QHBoxLayout()
        speed_row.setSpacing(6)

        self.queue_speed_enabled = QCheckBox("Enable Speed Limit")
        self.queue_speed_enabled.setChecked(getattr(queue, "speed_limit", 0) > 0)
        self.queue_speed_enabled.toggled.connect(self._toggle_queue_speed)

        self.queue_speed_spin = QSpinBox()
        self.queue_speed_spin.setRange(0, 999999)
        self.queue_speed_spin.setSuffix(" KB/s")
        self.queue_speed_spin.setValue(getattr(queue, "speed_limit", 0) or 1024)
        self.queue_speed_spin.setEnabled(self.queue_speed_enabled.isChecked())
        self.queue_speed_spin.setMinimumWidth(120)

        speed_row.addWidget(self.queue_speed_enabled)
        speed_row.addWidget(self.queue_speed_spin)
        speed_row.addStretch()

        speed_layout.addLayout(speed_row)

        speed_info = QLabel("0 = unlimited")
        speed_info.setStyleSheet("color: #95a5a6; font-size: 11px;")
        speed_layout.addWidget(speed_info)

        speed_layout.addStretch()
        tabs.addTab(speed_tab, get_icon("preferences-system-speed"), "Speed")

        # ---- Proxy ----
        proxy_tab = QWidget()
        proxy_layout = QVBoxLayout(proxy_tab)
        proxy_layout.setSpacing(10)
        proxy_layout.setContentsMargins(12, 12, 12, 12)

        self.queue_proxy_cb = QCheckBox("Use custom proxy for this queue")
        self.queue_proxy_cb.toggled.connect(self._toggle_queue_proxy)
        proxy_layout.addWidget(self.queue_proxy_cb)

        proxy_row = QHBoxLayout()
        proxy_row.setSpacing(6)

        self.queue_proxy_status = QLabel("Using global proxy")
        proxy_row.addWidget(self.queue_proxy_status)
        proxy_row.addStretch()

        self.queue_proxy_btn = QPushButton(get_icon("configure"), " Configure")
        self.queue_proxy_btn.setEnabled(False)
        self.queue_proxy_btn.clicked.connect(self._configure_queue_proxy)
        proxy_row.addWidget(self.queue_proxy_btn)

        proxy_layout.addLayout(proxy_row)
        proxy_layout.addStretch()
        tabs.addTab(proxy_tab, get_icon("network-vpn"), "Proxy")

        main_layout.addWidget(tabs)

        self._load_queue_proxy()

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def _toggle_queue_speed(self, checked):
        self.queue_speed_spin.setEnabled(checked)

    def _toggle_queue_proxy(self, checked):
        self.queue_proxy_btn.setEnabled(checked)
        if checked:
            self.queue_proxy_status.setText("Click 'Configure' to set proxy")
            self.queue_proxy_status.setStyleSheet("color: #f39c12; font-size: 11px;")
        else:
            self.queue_proxy_status.setText("Using global proxy")
            self.queue_proxy_status.setStyleSheet("color: #95a5a6; font-size: 11px;")
            self._queue_proxy_config = None

    def _load_queue_proxy(self):
        from core.proxy_manager import ProxyManager

        if hasattr(self.parent(), "store"):
            proxy_mgr = ProxyManager(self.parent().store)
            queue_proxy = proxy_mgr.get_queue_proxy(self.name_edit.text())
            if queue_proxy and queue_proxy.host:
                self.queue_proxy_cb.setChecked(True)
                self.queue_proxy_status.setText(f"✓ {queue_proxy.get_display_string()}")
                self.queue_proxy_status.setStyleSheet(
                    "color: #27ae60; font-size: 11px;"
                )
                self.queue_proxy_btn.setEnabled(True)
                self._queue_proxy_config = queue_proxy

    def _configure_queue_proxy(self):
        from ui.proxy_dialog import ProxyDialog
        from core.proxy_manager import ProxyConfig

        current = getattr(self, "_queue_proxy_config", None) or ProxyConfig()
        dlg = ProxyDialog(current, self, f"Queue Proxy: {self.name_edit.text()}")
        if dlg.exec():
            new_config = dlg.get_proxy_config()
            self._queue_proxy_config = new_config
            self.queue_proxy_status.setText(f"✓ {new_config.get_display_string()}")
            self.queue_proxy_status.setStyleSheet("color: #27ae60; font-size: 11px;")

    def get_queue_data(self):
        st, en = self.start_time.time(), self.end_time.time()
        data = {
            "name": self.name_edit.text().strip(),
            "save_path": self.path_edit.text().strip(),
            "max_concurrent": self.conc_spin.value(),
            "schedule_enabled": self.sched_cb.isChecked(),
            "schedule_start": dtime(st.hour(), st.minute()),
            "schedule_end": dtime(en.hour(), en.minute()),
            "days": [i for i, cb in enumerate(self.day_checks) if cb.isChecked()],
            "speed_limit": (
                self.queue_speed_spin.value()
                if self.queue_speed_enabled.isChecked()
                else 0
            ),
            "proxy_config": None,
        }
        if hasattr(self, "_queue_proxy_config") and self.queue_proxy_cb.isChecked():
            data["proxy_config"] = self._queue_proxy_config
        return data


# ============================================================
# SettingsDialog (تب‌بندی)
# ============================================================

class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(540)
        self.setMinimumHeight(460)

        self.settings = settings

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 12, 16, 16)

        tabs = QTabWidget()

        # ---- General ----
        general_tab = QWidget()
        general_layout = QVBoxLayout(general_tab)
        general_layout.setSpacing(10)
        general_layout.setContentsMargins(12, 12, 12, 12)

        rpc_group = QGroupBox("aria2 RPC")
        rpc_layout = QFormLayout(rpc_group)
        rpc_layout.setSpacing(6)

        self.host = QLineEdit(settings.get("aria2_host", "http://localhost"))
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(settings.get("aria2_port", 6800))
        self.secret = QLineEdit(settings.get("aria2_secret", ""))
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)

        rpc_layout.addRow("Host:", self.host)
        rpc_layout.addRow("Port:", self.port)
        rpc_layout.addRow("Secret:", self.secret)
        general_layout.addWidget(rpc_group)

        dl_group = QGroupBox("Download")
        dl_layout = QFormLayout(dl_group)
        dl_layout.setSpacing(6)

        self.max_concurrent = QSpinBox()
        self.max_concurrent.setRange(1, 50)
        self.max_concurrent.setValue(settings.get("max_concurrent", 5))

        self.max_retries = QSpinBox()
        self.max_retries.setRange(0, 20)
        self.max_retries.setSpecialValueText("Disabled")
        self.max_retries.setValue(settings.get("max_retries", 3))

        self.max_tries = QSpinBox()
        self.max_tries.setRange(0, 100)
        self.max_tries.setSpecialValueText("Unlimited")
        self.max_tries.setValue(settings.get("max_tries", 0))

        self.conns = QSpinBox()
        self.conns.setRange(1, 16)
        self.conns.setValue(settings.get("connections", 8))

        dl_layout.addRow("Max Concurrent:", self.max_concurrent)
        dl_layout.addRow("Max Retry Attempts:", self.max_retries)
        dl_layout.addRow("Max Tries (aria2):", self.max_tries)
        dl_layout.addRow("Default Connections:", self.conns)
        general_layout.addWidget(dl_group)

        cleanup_group = QGroupBox("Cleanup")
        cleanup_layout = QVBoxLayout(cleanup_group)
        self.auto_clear_completed = QCheckBox("Auto-clear completed downloads")
        self.auto_clear_completed.setChecked(
            settings.get("auto_clear_completed", False)
        )
        cleanup_layout.addWidget(self.auto_clear_completed)
        general_layout.addWidget(cleanup_group)

        general_layout.addStretch()
        tabs.addTab(general_tab, get_icon("configure"), "General")

        # ---- Appearance ----
        appearance_tab = QWidget()
        appearance_layout = QVBoxLayout(appearance_tab)
        appearance_layout.setSpacing(10)
        appearance_layout.setContentsMargins(12, 12, 12, 12)

        theme_group = QGroupBox("Theme")
        theme_layout = QFormLayout(theme_group)
        theme_layout.setSpacing(6)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Auto", "Dark", "Light"])
        current_theme = settings.get("theme", "auto").capitalize()
        index = self.theme_combo.findText(current_theme)
        if index >= 0:
            self.theme_combo.setCurrentIndex(index)
        theme_layout.addRow("Theme:", self.theme_combo)
        appearance_layout.addWidget(theme_group)

        appearance_layout.addStretch()
        tabs.addTab(appearance_tab, get_icon("preferences-desktop-theme"), "Appearance")

        # ---- Speed ----
        speed_tab = QWidget()
        speed_layout = QVBoxLayout(speed_tab)
        speed_layout.setSpacing(10)
        speed_layout.setContentsMargins(12, 12, 12, 12)

        speed_group = QGroupBox("Global Speed Limit")
        speed_group_layout = QVBoxLayout(speed_group)

        speed_row = QHBoxLayout()
        speed_row.setSpacing(6)

        self.global_speed_enabled = QCheckBox("Enable Speed Limit")
        self.global_speed_enabled.setChecked(settings.get("speed_limit", 0) > 0)
        self.global_speed_enabled.toggled.connect(self._toggle_global_speed)

        self.global_speed_spin = QSpinBox()
        self.global_speed_spin.setRange(0, 999999)
        self.global_speed_spin.setSuffix(" KB/s")
        self.global_speed_spin.setValue(settings.get("speed_limit", 1024))
        self.global_speed_spin.setEnabled(self.global_speed_enabled.isChecked())
        self.global_speed_spin.setMinimumWidth(120)

        speed_row.addWidget(self.global_speed_enabled)
        speed_row.addWidget(self.global_speed_spin)
        speed_row.addStretch()

        speed_group_layout.addLayout(speed_row)

        speed_info = QLabel("0 = unlimited")
        speed_info.setStyleSheet("color: #95a5a6; font-size: 11px;")
        speed_group_layout.addWidget(speed_info)

        speed_layout.addWidget(speed_group)
        speed_layout.addStretch()
        tabs.addTab(speed_tab, get_icon("preferences-system-speed"), "Speed")

        # ---- Proxy ----
        proxy_tab = QWidget()
        proxy_layout = QVBoxLayout(proxy_tab)
        proxy_layout.setSpacing(10)
        proxy_layout.setContentsMargins(12, 12, 12, 12)

        proxy_group = QGroupBox("Global Proxy")
        proxy_group_layout = QVBoxLayout(proxy_group)

        proxy_status_row = QHBoxLayout()
        proxy_status_row.setSpacing(6)

        self.proxy_status_label = QLabel("Disabled")
        proxy_status_row.addWidget(self.proxy_status_label)
        proxy_status_row.addStretch()

        self.proxy_edit_btn = QPushButton(get_icon("configure"), " Configure")
        self.proxy_edit_btn.clicked.connect(self._configure_global_proxy)
        proxy_status_row.addWidget(self.proxy_edit_btn)

        proxy_group_layout.addLayout(proxy_status_row)

        self.proxy_info_label = QLabel("")
        self.proxy_info_label.setStyleSheet("color: #95a5a6; font-size: 11px;")
        proxy_group_layout.addWidget(self.proxy_info_label)

        proxy_layout.addWidget(proxy_group)
        proxy_layout.addStretch()
        tabs.addTab(proxy_tab, get_icon("network-vpn"), "Proxy")

        # ---- Service ----
        service_tab = QWidget()
        service_layout = QVBoxLayout(service_tab)
        service_layout.setSpacing(10)
        service_layout.setContentsMargins(12, 12, 12, 12)

        service_group = QGroupBox("Background Service")
        service_group_layout = QVBoxLayout(service_group)

        self.run_as_service = QCheckBox(
            "Run as background service (auto-start on login)"
        )
        self.run_as_service.setChecked(settings.get("run_as_service", False))
        self.run_as_service.toggled.connect(self._on_service_toggle)
        service_group_layout.addWidget(self.run_as_service)

        self.service_status = QLabel("")
        self.service_status.setStyleSheet("color: #95a5a6; font-size: 11px;")
        service_group_layout.addWidget(self.service_status)

        service_layout.addWidget(service_group)
        service_layout.addStretch()
        tabs.addTab(service_tab, get_icon("applications-system"), "Service")

        main_layout.addWidget(tabs)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

        self._update_proxy_status()
        self._update_service_status()

    def _toggle_global_speed(self, checked):
        self.global_speed_spin.setEnabled(checked)

    def _update_proxy_status(self):
        from core.proxy_manager import ProxyManager

        proxy_mgr = ProxyManager(
            self.parent().store if hasattr(self.parent(), "store") else None
        )

        if (
            proxy_mgr.global_proxy
            and proxy_mgr.global_proxy.enabled
            and proxy_mgr.global_proxy.host
        ):
            self.proxy_status_label.setText(
                f"✓ {proxy_mgr.global_proxy.get_display_string()}"
            )
            self.proxy_status_label.setStyleSheet("color: #27ae60;")
            self.proxy_info_label.setText(
                f"{proxy_mgr.global_proxy.type.value.upper()} • {proxy_mgr.global_proxy.host}:{proxy_mgr.global_proxy.port}"
            )
        else:
            self.proxy_status_label.setText("Disabled")
            self.proxy_status_label.setStyleSheet("color: #95a5a6;")
            self.proxy_info_label.setText("No global proxy configured")

    def _configure_global_proxy(self):
        from ui.proxy_dialog import ProxyDialog
        from core.proxy_manager import ProxyManager, ProxyConfig

        if not hasattr(self.parent(), "store"):
            QMessageBox.warning(self, "Error", "Data store not available")
            return

        proxy_mgr = ProxyManager(self.parent().store)
        current_config = proxy_mgr.global_proxy or ProxyConfig()

        dlg = ProxyDialog(current_config, self, "Global Proxy Settings")
        if dlg.exec():
            new_config = dlg.get_proxy_config()
            proxy_mgr.set_global_proxy(new_config)
            self._update_proxy_status()

            if hasattr(self.parent(), "aria2"):
                self.parent().aria2.set_global_proxy(new_config)

            QMessageBox.information(self, "Success", "Proxy settings applied!")

    def _update_service_status(self):
        QTimer.singleShot(100, self._check_service_status)

    def _check_service_status(self):
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-active", "felfeldm.service"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            is_active = result.stdout.strip() == "active"

            result2 = subprocess.run(
                ["systemctl", "--user", "is-enabled", "felfeldm.service"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            is_enabled = result2.stdout.strip() == "enabled"

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            port_open = sock.connect_ex(("localhost", 8765)) == 0
            sock.close()

            if is_active and is_enabled and port_open:
                self.service_status.setText("✓ Service is active")
                self.service_status.setStyleSheet("color: #27ae60; font-size: 11px;")
            elif is_active:
                self.service_status.setText("Service is active but not enabled")
                self.service_status.setStyleSheet("color: #f39c12; font-size: 11px;")
            else:
                self.service_status.setText("Service is stopped")
                self.service_status.setStyleSheet("color: #95a5a6; font-size: 11px;")
        except:
            self.service_status.setText("Service is stopped")
            self.service_status.setStyleSheet("color: #95a5a6; font-size: 11px;")

    def _on_service_toggle(self, checked):
        if checked:
            self.service_status.setText("Installing service...")
            self.service_status.setStyleSheet("color: #f39c12; font-size: 11px;")
            QApplication.processEvents()
            QTimer.singleShot(100, self._install_service_async)
        else:
            self.service_status.setText("Stopping service...")
            self.service_status.setStyleSheet("color: #f39c12; font-size: 11px;")
            QApplication.processEvents()
            QTimer.singleShot(100, self._stop_service_async)

    def _install_service_async(self):
        try:
            result = subprocess.run(
                ["which", "FelfelDM"], capture_output=True, text=True
            )
            exe_path = (
                result.stdout.strip() if result.returncode == 0 else "/usr/bin/FelfelDM"
            )

            if not os.path.exists(exe_path):
                exe_path = "/usr/local/bin/FelfelDM"
            if not os.path.exists(exe_path):
                exe_path = "/usr/bin/FelfelDM"

            self._free_port(8765)

            service_dir = os.path.expanduser("~/.config/systemd/user")
            os.makedirs(service_dir, exist_ok=True)

            service_content = f"""[Unit]
Description=FelfelDM Download Manager Service
After=network.target

[Service]
Type=simple
ExecStart={exe_path} --daemon
Restart=on-failure
RestartSec=10
TimeoutStopSec=3
WorkingDirectory=/usr/share/felfeldm
StandardOutput=journal
StandardError=journal
KillMode=process
KillSignal=SIGTERM

[Install]
WantedBy=default.target
"""

            service_path = os.path.join(service_dir, "felfeldm.service")
            with open(service_path, "w") as f:
                f.write(service_content)

            subprocess.Popen(
                ["systemctl", "--user", "daemon-reload"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            subprocess.Popen(
                ["systemctl", "--user", "enable", "felfeldm.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            subprocess.Popen(
                ["systemctl", "--user", "start", "felfeldm.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            QTimer.singleShot(1500, self._check_service_status)
            self.service_status.setText("✓ Service installed and running")
            self.service_status.setStyleSheet("color: #27ae60; font-size: 11px;")
            self.run_as_service.setEnabled(True)
            self.run_as_service.setChecked(True)

        except Exception as e:
            self.service_status.setText(f"Failed: {str(e)}")
            self.service_status.setStyleSheet("color: #e74c3c; font-size: 11px;")
            self.run_as_service.setEnabled(True)
            self.run_as_service.setChecked(False)

    def _stop_service_async(self):
        try:
            subprocess.Popen(
                ["systemctl", "--user", "stop", "felfeldm.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            subprocess.Popen(
                ["systemctl", "--user", "disable", "felfeldm.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            subprocess.Popen(
                ["systemctl", "--user", "daemon-reload"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            subprocess.Popen(
                ["systemctl", "--user", "reset-failed"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            QTimer.singleShot(1000, self._check_service_status)
            self.service_status.setText("Service stopped")
            self.service_status.setStyleSheet("color: #f39c12; font-size: 11px;")
            self.run_as_service.setEnabled(True)
            self.run_as_service.setChecked(False)

        except Exception as e:
            self.service_status.setText(f"Failed: {str(e)}")
            self.service_status.setStyleSheet("color: #e74c3c; font-size: 11px;")
            self.run_as_service.setEnabled(True)
            self.run_as_service.setChecked(True)

    def _free_port(self, port):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("localhost", port))
            sock.close()

            if result != 0:
                return True

            try:
                result = subprocess.run(
                    ["lsof", "-ti", f":{port}"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                pids = result.stdout.strip().split("\n")
                current_pid = str(os.getpid())

                for pid in pids:
                    if pid and pid.isdigit() and pid != current_pid:
                        subprocess.Popen(
                            ["kill", "-9", pid],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )

                time.sleep(1)
                return True
            except:
                return False
        except:
            return False

    def get_settings(self):
        speed_limit = (
            self.global_speed_spin.value()
            if self.global_speed_enabled.isChecked()
            else 0
        )
        return {
            "aria2_host": self.host.text().strip(),
            "aria2_port": self.port.value(),
            "aria2_secret": self.secret.text(),
            "connections": self.conns.value(),
            "max_retries": self.max_retries.value(),
            "max_tries": self.max_tries.value(),
            "max_concurrent": self.max_concurrent.value(),
            "auto_clear_completed": self.auto_clear_completed.isChecked(),
            "theme": self.theme_combo.currentText().lower(),
            "run_as_service": self.run_as_service.isChecked(),
            "speed_limit": speed_limit,
        }


# ============================================================
# DownloadProgressDialog
# ============================================================
class DownloadProgressDialog(QDialog):
    pause_requested = pyqtSignal(str)
    resume_requested = pyqtSignal(str)
    cancel_requested = pyqtSignal(str)
    cancel_with_delete_requested = pyqtSignal(str)

    def __init__(self, gid, dl_data, parent=None):
        super().__init__(parent)
        self.gid = gid
        self.setWindowTitle("Download Progress")
        self.setMinimumWidth(480)
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self._status = "unknown"
        self._is_complete = False
        self._file_path = None

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(4)
        main_layout.setContentsMargins(20, 16, 20, 20)

        # Title
        self.name_lbl = QLabel(dl_data.get("name", "Unknown"))
        self.name_lbl.setWordWrap(True)
        self.name_lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        main_layout.addWidget(self.name_lbl)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)

        # Info Grid با آیکون Papirus
        info_group = QGroupBox("Details")
        info_group.setStyleSheet("QGroupBox { font-weight: 600; }")
        info_layout = QGridLayout(info_group)
        info_layout.setSpacing(6)
        info_layout.setHorizontalSpacing(10)

        items = [
            ("document-open", "Size:", "size"),
            ("media-playback-start", "Speed:", "speed"),
            ("alarm-clock", "ETA:", "eta"),
            ("network-transmit", "Connections:", "connections"),
            ("dialog-information", "Status:", "status"),
        ]

        self.info_labels = {}
        for i, (icon_name, label, key) in enumerate(items):
            icon_lbl = QLabel()
            icon_lbl.setPixmap(get_icon(icon_name).pixmap(16, 16))
            info_layout.addWidget(icon_lbl, i, 0)

            lbl = QLabel(label)
            lbl.setStyleSheet("color: #a6adc8;")
            info_layout.addWidget(lbl, i, 1)

            val_lbl = QLabel("—")
            val_lbl.setStyleSheet("color: #cdd6f4; font-weight: 500;")
            info_layout.addWidget(val_lbl, i, 2)
            self.info_labels[key] = val_lbl

        main_layout.addWidget(info_group)

        # ===== Spacer برای فاصله بیشتر بین Info و دکمه‌ها =====
        main_layout.addSpacing(8)  # فاصله اضافه

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.action_btn = QPushButton()
        self.action_btn.setIcon(get_icon("media-playback-pause"))
        self.action_btn.setText("Pause")
        self.action_btn.setMinimumWidth(100)
        self.action_btn.clicked.connect(self._on_action_clicked)
        btn_row.addWidget(self.action_btn)

        btn_row.addStretch()

        self.cancel_btn = QPushButton()
        self.cancel_btn.setIcon(get_icon("edit-delete"))
        self.cancel_btn.setText("Cancel")
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.clicked.connect(self._on_cancel_clicked)
        btn_row.addWidget(self.cancel_btn)

        main_layout.addLayout(btn_row)

        if dl_data:
            files = dl_data.get("files", [])
            if files and files[0].get("path"):
                self._file_path = files[0]["path"]
            self.update_data(dl_data)

    def _on_action_clicked(self):
        if self._is_complete:
            if self._file_path and os.path.exists(self._file_path):
                folder = os.path.dirname(self._file_path)
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
            else:
                QMessageBox.warning(self, "Folder Not Found", "Folder not found.")
            return

        btn_text = self.action_btn.text().strip()
        if btn_text == "Pause":
            self.pause_requested.emit(self.gid)
        elif btn_text in ["Resume", "Start", "Retry"]:
            self.resume_requested.emit(self.gid)

    def _on_cancel_clicked(self):
        if self._is_complete:
            self.close()
            return

        reply = QMessageBox.question(
            self,
            "Cancel Download",
            "Cancel this download?\n\nDo you also want to delete downloaded files?",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No |
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return
        elif reply == QMessageBox.StandardButton.Yes:
            self.cancel_with_delete_requested.emit(self.gid)
            self.close()
        else:
            self.cancel_requested.emit(self.gid)
            self.close()

    def update_data(self, dl_data):
        from utils.helpers import format_size, format_speed

        if not dl_data:
            return

        total = int(dl_data.get("totalLength", 0))
        completed = int(dl_data.get("completedLength", 0))
        speed = int(dl_data.get("downloadSpeed", 0))
        status = dl_data.get("status", "unknown")
        name = dl_data.get("name", "")

        if status == "complete" and not self._is_complete:
            self._is_complete = True
            self.setWindowTitle("Download Completed!")
            self.setWindowFlags(
                Qt.WindowType.Window |
                Qt.WindowType.WindowCloseButtonHint |
                Qt.WindowType.WindowMinimizeButtonHint |
                Qt.WindowType.WindowMaximizeButtonHint |
                Qt.WindowType.WindowStaysOnTopHint
            )
            self.show()
            self.raise_()
            self.activateWindow()

        if name:
            self.name_lbl.setText(name)

        if total > 0:
            pct = int((completed / total) * 100)
            self.progress_bar.setValue(min(pct, 100))
            self.progress_bar.setFormat(f"{pct}%")
            self.info_labels["size"].setText(f"{format_size(completed)} / {format_size(total)}")
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("—")
            self.info_labels["size"].setText(f"{format_size(completed)} / Unknown")

        if status == "paused":
            self.info_labels["speed"].setText("0 B/s")
        elif status == "complete":
            self.info_labels["speed"].setText("Done")
        elif status == "error":
            self.info_labels["speed"].setText("Error")
        else:
            self.info_labels["speed"].setText(format_speed(speed) if speed > 0 else "—")

        if status in ["paused", "complete", "error"]:
            self.info_labels["eta"].setText("—")
        elif speed > 0 and total > completed:
            eta_sec = (total - completed) // speed
            h, m, s = eta_sec // 3600, (eta_sec % 3600) // 60, eta_sec % 60
            self.info_labels["eta"].setText(f"{h:02d}:{m:02d}:{s:02d}")
        else:
            self.info_labels["eta"].setText("—")

        self.info_labels["connections"].setText(str(dl_data.get("connections", 0)))

        status_map = {
            "active": {"text": "Downloading", "color": "#89b4fa"},
            "downloading": {"text": "Downloading", "color": "#89b4fa"},
            "waiting": {"text": "Waiting", "color": "#a6adc8"},
            "paused": {"text": "Paused", "color": "#f9e2af"},
            "complete": {"text": "Complete", "color": "#a6e3a1"},
            "completed": {"text": "Complete", "color": "#a6e3a1"},
            "error": {"text": "Error", "color": "#f38ba8"},
            "removed": {"text": "Removed", "color": "#6c7086"},
        }
        
        info = status_map.get(status, {"text": status.capitalize(), "color": "#a6adc8"})
        self.info_labels["status"].setText(info["text"])
        self.info_labels["status"].setStyleSheet(f"color: {info['color']}; font-weight: 600;")

        self._status = status
        self._update_buttons(status)

    def _update_buttons(self, status):
        if status == "complete":
            self.action_btn.setIcon(get_icon("folder"))
            self.action_btn.setText("Open Folder")
            self.action_btn.setEnabled(True)
            self.cancel_btn.setText("Close")
            self.cancel_btn.setIcon(get_icon("window-close"))
            self.cancel_btn.setEnabled(True)
        elif status == "active":
            self.action_btn.setIcon(get_icon("media-playback-pause"))
            self.action_btn.setText("Pause")
            self.action_btn.setEnabled(True)
            self.cancel_btn.setText("Cancel")
            self.cancel_btn.setIcon(get_icon("edit-delete"))
            self.cancel_btn.setEnabled(True)
        elif status in ["paused", "waiting"]:
            self.action_btn.setIcon(get_icon("media-playback-start"))
            self.action_btn.setText("Resume")
            self.action_btn.setEnabled(True)
            self.cancel_btn.setText("Cancel")
            self.cancel_btn.setIcon(get_icon("edit-delete"))
            self.cancel_btn.setEnabled(True)
        elif status == "error":
            self.action_btn.setIcon(get_icon("media-playback-start"))
            self.action_btn.setText("Retry")
            self.action_btn.setEnabled(True)
            self.cancel_btn.setText("Cancel")
            self.cancel_btn.setIcon(get_icon("edit-delete"))
            self.cancel_btn.setEnabled(True)
        else:
            self.action_btn.setEnabled(False)
            self.cancel_btn.setEnabled(False)
# ============================================================
# ProxyDialog
# ============================================================

class ProxyDialog(QDialog):
    def __init__(
        self, proxy_config: ProxyConfig = None, parent=None, title="Proxy Settings"
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(450)
        self.setMinimumHeight(350)

        self.proxy_config = proxy_config or ProxyConfig()

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(16, 12, 16, 16)

        self.enable_cb = QCheckBox("Enable Proxy")
        self.enable_cb.setChecked(self.proxy_config.enabled)
        self.enable_cb.toggled.connect(self._toggle_enable)
        main_layout.addWidget(self.enable_cb)

        form_group = QGroupBox("Proxy Configuration")
        form_layout = QFormLayout(form_group)
        form_layout.setSpacing(6)

        self.type_combo = QComboBox()
        self.type_combo.addItems([t.value.upper() for t in ProxyType])
        current_type = self.proxy_config.type.value.upper()
        index = self.type_combo.findText(current_type)
        if index >= 0:
            self.type_combo.setCurrentIndex(index)
        form_layout.addRow("Type:", self.type_combo)

        self.host_edit = QLineEdit(self.proxy_config.host)
        self.host_edit.setPlaceholderText("proxy.example.com or 127.0.0.1")
        form_layout.addRow("Host:", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.proxy_config.port)
        form_layout.addRow("Port:", self.port_spin)

        auth_label = QLabel("Authentication (optional)")
        auth_label.setStyleSheet("font-weight: 500; margin-top: 4px;")
        form_layout.addRow(auth_label)

        self.username_edit = QLineEdit(self.proxy_config.username or "")
        self.username_edit.setPlaceholderText("Username")
        form_layout.addRow("Username:", self.username_edit)

        self.password_edit = QLineEdit(self.proxy_config.password or "")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("Password")
        form_layout.addRow("Password:", self.password_edit)

        main_layout.addWidget(form_group)

        test_btn = QPushButton(get_icon("view-refresh"), "Test Proxy Connection")
        test_btn.clicked.connect(self._test_proxy)
        main_layout.addWidget(test_btn)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; padding: 4px;")
        main_layout.addWidget(self.status_label)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

        self._toggle_enable(self.proxy_config.enabled)

    def _toggle_enable(self, checked):
        self.type_combo.setEnabled(checked)
        self.host_edit.setEnabled(checked)
        self.port_spin.setEnabled(checked)
        self.username_edit.setEnabled(checked)
        self.password_edit.setEnabled(checked)

    def _test_proxy(self):
        config = self.get_proxy_config()
        if not config.is_valid():
            self.status_label.setText("Invalid proxy configuration")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
            return

        try:
            import requests

            proxy_url = config._build_proxy_url()
            proxies = {"http": proxy_url, "https": proxy_url}

            self.status_label.setText("Testing connection...")
            self.status_label.setStyleSheet("color: #f39c12; font-size: 11px;")
            QApplication.processEvents()

            response = requests.get(
                "https://www.google.com", proxies=proxies, timeout=10
            )

            if response.status_code == 200:
                self.status_label.setText("Proxy is working!")
                self.status_label.setStyleSheet("color: #27ae60; font-size: 11px;")
            else:
                self.status_label.setText(f"Status: {response.status_code}")
                self.status_label.setStyleSheet("color: #f39c12; font-size: 11px;")

        except requests.exceptions.Timeout:
            self.status_label.setText("Connection timeout")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        except requests.exceptions.ConnectionError:
            self.status_label.setText("Connection failed")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)[:50]}")
            self.status_label.setStyleSheet("color: #e74c3c; font-size: 11px;")

    def get_proxy_config(self) -> ProxyConfig:
        type_str = self.type_combo.currentText().lower()
        proxy_type = ProxyType(type_str)

        return ProxyConfig(
            proxy_type=proxy_type,
            host=self.host_edit.text().strip(),
            port=self.port_spin.value(),
            username=self.username_edit.text().strip() or None,
            password=self.password_edit.text().strip() or None,
            enabled=self.enable_cb.isChecked(),
        )


# ============================================================
# ShutdownCountdownDialog
# ============================================================

class ShutdownCountdownDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("System Shutdown")
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setMinimumWidth(400)
        self.setMinimumHeight(250)

        self._countdown = 20
        self._timer = None
        self._cancelled = False

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(25, 25, 25, 25)

        title = QLabel("System Shutdown")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(title)

        msg = QLabel("All downloads are complete!\nThe system will shut down in:")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(msg)

        self.countdown_lbl = QLabel("20")
        self.countdown_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_lbl.setStyleSheet("font-size: 42px; font-weight: bold;")
        main_layout.addWidget(self.countdown_lbl)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(20)
        self.progress_bar.setValue(20)
        main_layout.addWidget(self.progress_bar)

        self.cancel_btn = QPushButton("Cancel Shutdown")
        self.cancel_btn.setFixedHeight(36)
        self.cancel_btn.clicked.connect(self._on_cancel)
        main_layout.addWidget(self.cancel_btn)

    def start_countdown(self):
        self._countdown = 20
        self.countdown_lbl.setText("20")
        self.progress_bar.setValue(20)
        self._cancelled = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_countdown)
        self._timer.start(1000)

    def _update_countdown(self):
        self._countdown -= 1
        self.countdown_lbl.setText(str(self._countdown))
        self.progress_bar.setValue(self._countdown)

        if self._countdown <= 0:
            self._timer.stop()
            self._timer = None
            self.accept()

    def _on_cancel(self):
        self._cancelled = True
        if self._timer:
            self._timer.stop()
            self._timer = None
        self.reject()

    def is_cancelled(self):
        return self._cancelled

    def closeEvent(self, event):
        if self._timer:
            self._timer.stop()
            self._timer = None
        event.accept()