# Requires: PyQt6>=6.4.0

"""
Dialog windows for adding downloads, settings, and progress display.
"""

import os
import re
import logging
from urllib.parse import urlparse
from typing import List, Optional, Dict, Any, Union, cast

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLineEdit, QTextEdit, QPushButton, QComboBox, QSpinBox,
    QCheckBox, QLabel, QFileDialog, QDialogButtonBox, QProgressBar,
    QMessageBox, QTimeEdit, QTabWidget, QWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTime, QByteArray
from PyQt6.QtGui import QIcon

from core.data_store import Queue, DataStore
from core.aria2_rpc import Aria2RPC
from utils.helpers import get_icon, format_size, format_speed, check_disk_space

logger: logging.Logger = logging.getLogger(__name__)


def is_valid_url(url: str) -> bool:
    if not url or not url.strip():
        return False
    url = url.strip()
    if url.startswith("magnet:?xt=urn:"):
        return True
    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return True
        ipv6_pattern = r'^\[([0-9a-fA-F:]+)\](:\d+)?$'
        if re.match(ipv6_pattern, url) or re.match(r'^([0-9a-fA-F:]+)$', url):
            return True
        return False
    except Exception:
        return False


class AddDownloadDialog(QDialog):
    """Dialog for adding multiple downloads with advanced options."""

    def __init__(self, queues: List[Queue], store: DataStore,
                 default_queue: int = 0, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self._queues = queues
        self._store = store
        self._default_queue = default_queue
        self.setWindowTitle("Add Downloads")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        tabs = QTabWidget()
        normal_tab = QWidget()
        advanced_tab = QWidget()

        # Normal tab
        normal_layout = QVBoxLayout(normal_tab)
        url_group = QGroupBox("URLs")
        url_layout = QVBoxLayout(url_group)
        self.url_edit = QTextEdit()
        self.url_edit.setPlaceholderText("Enter URLs (one per line)...")
        self.url_edit.setMinimumHeight(80)
        url_layout.addWidget(self.url_edit)
        import_btn = QPushButton(get_icon('document-open'), "Import from File")
        import_btn.clicked.connect(self._import_from_txt)
        url_layout.addWidget(import_btn)
        normal_layout.addWidget(url_group)

        path_group = QGroupBox("Save Location")
        path_layout = QHBoxLayout(path_group)
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        path_layout.addWidget(self.path_edit)
        browse = QPushButton(get_icon('folder-open'), "Browse...")
        browse.clicked.connect(self._browse)
        path_layout.addWidget(browse)
        normal_layout.addWidget(path_group)

        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)
        self.queue_cb = QComboBox()
        for q in self._queues:
            if q.name != "__direct__":
                self.queue_cb.addItem(q.name)
        if self._default_queue < self.queue_cb.count():
            self.queue_cb.setCurrentIndex(self._default_queue)
        options_layout.addRow("Queue:", self.queue_cb)

        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 16)
        self.conn_spin.setValue(16)
        options_layout.addRow("Connections:", self.conn_spin)

        self.start_immediately = QCheckBox("Start downloads immediately")
        self.start_immediately.setChecked(False)
        options_layout.addRow("", self.start_immediately)
        normal_layout.addWidget(options_group)

        # Advanced tab
        advanced_layout = QVBoxLayout(advanced_tab)
        advanced_group = QGroupBox("Advanced Options")
        adv_form = QFormLayout(advanced_group)

        self.cookies_edit = QLineEdit()
        self.cookies_edit.setPlaceholderText("name=value; name2=value2")
        self.cookies_edit.setText(self._store.get_cookies())
        adv_form.addRow("Cookies:", self.cookies_edit)

        self.headers_edit = QTextEdit()
        self.headers_edit.setPlaceholderText("Header-Name: value\nAnother-Header: value")
        self.headers_edit.setMaximumHeight(80)
        self.headers_edit.setText(self._store.get_headers())
        adv_form.addRow("Headers:", self.headers_edit)

        advanced_layout.addWidget(advanced_group)

        tabs.addTab(normal_tab, "Basic")
        tabs.addTab(advanced_tab, "Advanced")
        lay.addWidget(tabs)

        info_label = QLabel("Downloads will be added in Paused state by default")
        info_label.setStyleSheet("color: #95a5a6; font-size: 10px; padding: 4px;")
        lay.addWidget(info_label)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def _import_from_txt(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Links File", "", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    lines = [line.strip() for line in f if line.strip()]
                if lines:
                    current_text = self.url_edit.toPlainText().strip()
                    combined = current_text + "\n" + "\n".join(lines) if current_text else "\n".join(lines)
                    self.url_edit.setPlainText(combined)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to parse file:\n{str(e)}")

    def get_data(self) -> Optional[Dict[str, Any]]:
        raw_text = self.url_edit.toPlainText()
        urls = [line.strip() for line in raw_text.split('\n') if line.strip()]
        if not urls:
            QMessageBox.warning(self, "No URLs", "Please enter at least one URL.")
            return None
        invalid_urls = [url for url in urls if not is_valid_url(url)]
        if invalid_urls:
            QMessageBox.warning(
                self,
                "Invalid URL(s)",
                f"The following URLs are invalid:\n\n" + "\n".join(invalid_urls[:5]) +
                (f"\n... and {len(invalid_urls) - 5} more" if len(invalid_urls) > 5 else "")
            )
            return None
        self._store.set_cookies(self.cookies_edit.text().strip())
        self._store.set_headers(self.headers_edit.toPlainText().strip())
        return {
            "urls": urls,
            "path": self.path_edit.text().strip(),
            "queue": self.queue_cb.currentIndex(),
            "connections": self.conn_spin.value(),
            "start_immediately": self.start_immediately.isChecked(),
        }


class SingleDownloadDialog(QDialog):
    """Dialog for adding a single download with advanced options."""
    def __init__(self, queues: List[Queue], store: DataStore, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self._queues = queues
        self._store = store
        self.setWindowTitle("Single Download")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        tabs = QTabWidget()
        normal_tab = QWidget()
        advanced_tab = QWidget()

        normal_layout = QVBoxLayout(normal_tab)
        url_group = QGroupBox("URL")
        url_layout = QVBoxLayout(url_group)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://example.com/file.zip")
        url_layout.addWidget(self.url_edit)
        normal_layout.addWidget(url_group)

        path_group = QGroupBox("Save Location")
        path_layout = QHBoxLayout(path_group)
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        path_layout.addWidget(self.path_edit)
        browse = QPushButton(get_icon('folder-open'), "Browse")
        browse.clicked.connect(self._browse)
        path_layout.addWidget(browse)
        normal_layout.addWidget(path_group)

        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)
        if self._queues:
            self.queue_cb = QComboBox()
            for q in self._queues:
                if q.name != "__direct__":
                    self.queue_cb.addItem(q.name)
            options_layout.addRow("Queue:", self.queue_cb)
        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 16)
        self.conn_spin.setValue(16)
        options_layout.addRow("Connections:", self.conn_spin)
        self.start_immediately = QCheckBox("Start download immediately")
        self.start_immediately.setChecked(True)
        options_layout.addRow("", self.start_immediately)
        normal_layout.addWidget(options_group)

        advanced_layout = QVBoxLayout(advanced_tab)
        adv_group = QGroupBox("Advanced Options")
        adv_form = QFormLayout(adv_group)
        self.cookies_edit = QLineEdit()
        self.cookies_edit.setPlaceholderText("name=value; name2=value2")
        self.cookies_edit.setText(self._store.get_cookies())
        adv_form.addRow("Cookies:", self.cookies_edit)
        self.headers_edit = QTextEdit()
        self.headers_edit.setPlaceholderText("Header-Name: value\nAnother-Header: value")
        self.headers_edit.setMaximumHeight(80)
        self.headers_edit.setText(self._store.get_headers())
        adv_form.addRow("Headers:", self.headers_edit)
        advanced_layout.addWidget(adv_group)

        tabs.addTab(normal_tab, "Basic")
        tabs.addTab(advanced_tab, "Advanced")
        lay.addWidget(tabs)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def get_data(self) -> Optional[Dict[str, Any]]:
        url = self.url_edit.text().strip()
        if not is_valid_url(url):
            QMessageBox.warning(self, "Invalid URL", f"'{url}' is not a valid URL.")
            return None
        self._store.set_cookies(self.cookies_edit.text().strip())
        self._store.set_headers(self.headers_edit.toPlainText().strip())
        data = {
            "urls": [url],
            "path": self.path_edit.text().strip(),
            "connections": self.conn_spin.value(),
            "start_immediately": self.start_immediately.isChecked(),
        }
        if hasattr(self, 'queue_cb'):
            data["queue"] = self.queue_cb.currentIndex()
        return data


class QuickDownloadDialog(QDialog):
    """Quick dialog for adding multiple downloads with minimal options."""
    def __init__(self, queues: List[Queue], store: DataStore, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self._queues = queues
        self._store = store
        self.setWindowTitle("Quick Download")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        lay = QVBoxLayout(self)
        url_group = QGroupBox("URLs")
        url_layout = QVBoxLayout(url_group)
        self.url_edit = QTextEdit()
        self.url_edit.setPlaceholderText("Enter URLs (one per line)...")
        self.url_edit.setMinimumHeight(80)
        url_layout.addWidget(self.url_edit)
        lay.addWidget(url_group)

        path_group = QGroupBox("Save Location")
        path_layout = QHBoxLayout(path_group)
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        path_layout.addWidget(self.path_edit)
        browse = QPushButton(get_icon('folder-open'), "Browse")
        browse.clicked.connect(self._browse)
        path_layout.addWidget(browse)
        lay.addWidget(path_group)

        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)
        if self._queues:
            self.queue_cb = QComboBox()
            for q in self._queues:
                if q.name != "__direct__":
                    self.queue_cb.addItem(q.name)
            options_layout.addRow("Queue:", self.queue_cb)
        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 16)
        self.conn_spin.setValue(16)
        options_layout.addRow("Connections:", self.conn_spin)
        self.start_immediately = QCheckBox("Start downloads immediately")
        self.start_immediately.setChecked(False)
        options_layout.addRow("", self.start_immediately)
        lay.addWidget(options_group)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def get_data(self) -> Optional[Dict[str, Any]]:
        raw = self.url_edit.toPlainText()
        urls = [l.strip() for l in raw.split('\n') if l.strip()]
        if not urls:
            QMessageBox.warning(self, "No URLs", "Please enter at least one URL.")
            return None
        invalid_urls = [url for url in urls if not is_valid_url(url)]
        if invalid_urls:
            QMessageBox.warning(
                self,
                "Invalid URL(s)",
                f"The following URLs are invalid:\n\n" + "\n".join(invalid_urls[:5]) +
                (f"\n... and {len(invalid_urls) - 5} more" if len(invalid_urls) > 5 else "")
            )
            return None
        data = {
            "urls": urls,
            "path": self.path_edit.text().strip(),
            "connections": self.conn_spin.value(),
            "start_immediately": self.start_immediately.isChecked(),
        }
        if hasattr(self, 'queue_cb'):
            data["queue"] = self.queue_cb.currentIndex()
        return data


class TorrentDialog(QDialog):
    """Dialog for adding torrent download (file or magnet)."""
    def __init__(self, queues: List[Queue], store: DataStore, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self._queues = queues
        self._store = store
        self.setWindowTitle("Add Torrent")
        self.setMinimumWidth(500)
        self._torrent_data: Optional[bytes] = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        lay = QVBoxLayout(self)

        group = QGroupBox("Torrent Source")
        form = QFormLayout(group)
        self.magnet_edit = QLineEdit()
        self.magnet_edit.setPlaceholderText("magnet:?xt=urn:btih:...")
        form.addRow("Magnet Link:", self.magnet_edit)

        self.file_btn = QPushButton("Select .torrent File")
        self.file_btn.clicked.connect(self._select_torrent)
        self.file_label = QLabel("No file selected")
        form.addRow("Torrent File:", self.file_btn)
        form.addRow("", self.file_label)
        lay.addWidget(group)

        path_group = QGroupBox("Save Location")
        path_layout = QHBoxLayout(path_group)
        self.path_edit = QLineEdit(os.path.expanduser("~/Downloads"))
        path_layout.addWidget(self.path_edit)
        browse = QPushButton(get_icon('folder-open'), "Browse")
        browse.clicked.connect(self._browse)
        path_layout.addWidget(browse)
        lay.addWidget(path_group)

        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)
        if self._queues:
            self.queue_cb = QComboBox()
            for q in self._queues:
                if q.name != "__direct__":
                    self.queue_cb.addItem(q.name)
            options_layout.addRow("Queue:", self.queue_cb)
        self.start_immediately = QCheckBox("Start download immediately")
        self.start_immediately.setChecked(True)
        options_layout.addRow("", self.start_immediately)
        lay.addWidget(options_group)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        lay.addWidget(btn_box)

    def _browse(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def _select_torrent(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Torrent File", "", "Torrent Files (*.torrent);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    self._torrent_data = f.read()
                self.file_label.setText(os.path.basename(file_path))
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to read torrent file: {e}")

    def get_data(self) -> Optional[Dict[str, Any]]:
        magnet = self.magnet_edit.text().strip()
        if not magnet and not self._torrent_data:
            QMessageBox.warning(self, "Missing Source", "Please provide a magnet link or select a .torrent file.")
            return None
        return {
            "magnet": magnet if magnet else None,
            "torrent_file": self._torrent_data,
            "path": self.path_edit.text().strip(),
            "queue": self.queue_cb.currentIndex() if hasattr(self, 'queue_cb') else 0,
            "start_immediately": self.start_immediately.isChecked(),
        }


class QueueSettingsDialog(QDialog):
    """Dialog for editing queue settings."""
    def __init__(self, queue: Queue, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.queue = queue
        self.setWindowTitle(f"Queue Settings - {queue.name}")
        self.setMinimumWidth(450)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        name_layout = QFormLayout()
        self.name_edit = QLineEdit(self.queue.name)
        name_layout.addRow("Queue Name:", self.name_edit)
        layout.addLayout(name_layout)

        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(self.queue.max_concurrent)
        concurrent_layout = QFormLayout()
        concurrent_layout.addRow("Max Concurrent Downloads:", self.concurrent_spin)
        layout.addLayout(concurrent_layout)

        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit(self.queue.save_path)
        path_layout.addWidget(self.path_edit)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_path)
        path_layout.addWidget(browse_btn)
        path_group = QGroupBox("Save Location")
        path_group.setLayout(path_layout)
        layout.addWidget(path_group)

        schedule_group = QGroupBox("Schedule")
        schedule_layout = QVBoxLayout(schedule_group)
        self.schedule_check = QCheckBox("Enable schedule")
        self.schedule_check.setChecked(self.queue.schedule_enabled)
        schedule_layout.addWidget(self.schedule_check)
        time_layout = QHBoxLayout()
        self.start_time = QTimeEdit()
        self.start_time.setTime(QTime.fromString(self.queue.schedule_start.strftime("%H:%M"), "HH:mm"))
        self.end_time = QTimeEdit()
        self.end_time.setTime(QTime.fromString(self.queue.schedule_end.strftime("%H:%M"), "HH:mm"))
        time_layout.addWidget(QLabel("Start:"))
        time_layout.addWidget(self.start_time)
        time_layout.addWidget(QLabel("End:"))
        time_layout.addWidget(self.end_time)
        schedule_layout.addLayout(time_layout)
        days_layout = QHBoxLayout()
        self.days_checkboxes = []
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, name in enumerate(day_names):
            cb = QCheckBox(name)
            cb.setChecked(i in self.queue.days)
            self.days_checkboxes.append(cb)
            days_layout.addWidget(cb)
        schedule_layout.addLayout(days_layout)
        layout.addWidget(schedule_group)

        self.paused_check = QCheckBox("Paused (start downloads in paused state)")
        self.paused_check.setChecked(self.queue.paused)
        layout.addWidget(self.paused_check)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _browse_path(self) -> None:
        d = QFileDialog.getExistingDirectory(
            self, "Select Directory", self.path_edit.text()
        )
        if d:
            self.path_edit.setText(d)

    def get_queue(self) -> Queue:
        self.queue.name = self.name_edit.text().strip()
        self.queue.max_concurrent = self.concurrent_spin.value()
        self.queue.save_path = self.path_edit.text().strip()
        self.queue.schedule_enabled = self.schedule_check.isChecked()
        st = self.start_time.time()
        en = self.end_time.time()
        self.queue.schedule_start = st.toPyTime()
        self.queue.schedule_end = en.toPyTime()
        self.queue.days = [i for i, cb in enumerate(self.days_checkboxes) if cb.isChecked()]
        self.queue.paused = self.paused_check.isChecked()
        return self.queue


class SettingsDialog(QDialog):
    """Main settings dialog for the application."""
    def __init__(
        self,
        store: DataStore,
        aria2: Optional[Aria2RPC] = None,
        parent: Optional[QDialog] = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.aria2 = aria2
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        aria2_group = QGroupBox("aria2 RPC")
        aria2_layout = QFormLayout(aria2_group)
        self.host_edit = QLineEdit(self.store.settings.get("aria2_host", "https://127.0.0.1"))
        aria2_layout.addRow("Host:", self.host_edit)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(self.store.settings.get("aria2_port", 6800))
        aria2_layout.addRow("Port:", self.port_spin)
        self.secret_edit = QLineEdit()
        self.secret_edit.setPlaceholderText("Enter secret (optional)")
        self.secret_edit.setText(self.store.get_aria2_secret())
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        aria2_layout.addRow("Secret:", self.secret_edit)
        layout.addWidget(aria2_group)

        timeout_group = QGroupBox("Network")
        timeout_layout = QFormLayout(timeout_group)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 30)
        self.timeout_spin.setValue(self.store.settings.get("aria2_timeout", 5))
        self.timeout_spin.setSuffix(" seconds")
        timeout_layout.addRow("Request Timeout:", self.timeout_spin)
        self.poll_interval_spin = QSpinBox()
        self.poll_interval_spin.setRange(200, 5000)
        self.poll_interval_spin.setSingleStep(100)
        self.poll_interval_spin.setValue(self.store.settings.get("poll_interval", 5000))
        self.poll_interval_spin.setSuffix(" ms")
        timeout_layout.addRow("Poll Interval:", self.poll_interval_spin)
        timeout_label = QLabel("Maximum time to wait for aria2 response")
        timeout_label.setStyleSheet("color: #95a5a6; font-size: 10px;")
        timeout_layout.addRow("", timeout_label)
        layout.addWidget(timeout_group)

        other_group = QGroupBox("General")
        other_layout = QFormLayout(other_group)
        self.connections_spin = QSpinBox()
        self.connections_spin.setRange(1, 16)
        self.connections_spin.setValue(self.store.settings.get("connections", 16))
        other_layout.addRow("Default Connections:", self.connections_spin)
        self.max_concurrent_spin = QSpinBox()
        self.max_concurrent_spin.setRange(1, 10)
        self.max_concurrent_spin.setValue(self.store.settings.get("max_concurrent", 5))
        other_layout.addRow("Max Concurrent Downloads:", self.max_concurrent_spin)
        self.speed_limit_spin = QSpinBox()
        self.speed_limit_spin.setRange(0, 1000000)
        self.speed_limit_spin.setValue(self.store.settings.get("speed_limit", 0))
        self.speed_limit_spin.setSuffix(" KB/s")
        self.speed_limit_spin.setSpecialValueText("Unlimited")
        other_layout.addRow("Download Speed Limit:", self.speed_limit_spin)
        self.disk_cache_edit = QLineEdit()
        self.disk_cache_edit.setPlaceholderText("e.g., 64M, 128M")
        self.disk_cache_edit.setText(self.store.settings.get("disk_cache", "128M"))
        other_layout.addRow("Disk Cache:", self.disk_cache_edit)
        self.shutdown_check = QCheckBox()
        self.shutdown_check.setChecked(self.store.settings.get("shutdown_after_finish", False))
        other_layout.addRow("Shutdown after all downloads finish:", self.shutdown_check)
        self.auto_clear_check = QCheckBox()
        self.auto_clear_check.setChecked(self.store.settings.get("auto_clear_completed", False))
        other_layout.addRow("Auto clear completed downloads:", self.auto_clear_check)
        layout.addWidget(other_group)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def save_settings(self) -> None:
        self.store.settings["aria2_host"] = self.host_edit.text().strip()
        self.store.settings["aria2_port"] = self.port_spin.value()
        new_secret = self.secret_edit.text().strip()
        self.store.set_aria2_secret(new_secret)
        # Update RPC client with new secret
        if self.aria2:
            self.aria2.set_secret(new_secret)
        new_timeout = self.timeout_spin.value()
        self.store.settings["aria2_timeout"] = new_timeout
        if self.aria2:
            self.aria2.set_timeout(float(new_timeout))
        self.store.settings["poll_interval"] = self.poll_interval_spin.value()
        self.store.settings["connections"] = self.connections_spin.value()
        self.store.settings["max_concurrent"] = self.max_concurrent_spin.value()
        self.store.settings["speed_limit"] = self.speed_limit_spin.value()
        self.store.settings["disk_cache"] = self.disk_cache_edit.text().strip()
        self.store.settings["shutdown_after_finish"] = self.shutdown_check.isChecked()
        self.store.settings["auto_clear_completed"] = self.auto_clear_check.isChecked()
        self.store.save()
        QMessageBox.information(self, "Success", "Settings saved successfully!")


class DownloadProgressDialog(QDialog):
    """Dialog showing detailed progress of a single download."""
    pause_requested = pyqtSignal(str, bool)
    cancel_requested = pyqtSignal(str)

    def __init__(self, gid: str, url: str, parent: Optional[QDialog] = None) -> None:
        super().__init__(parent)
        self.gid = gid
        self.url = url
        self._status = "unknown"
        self._completed = False
        self.setWindowTitle(f"Downloading: {url[:60]}...")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        info_layout = QFormLayout()
        self.size_label = QLabel("0 B")
        info_layout.addRow("Size:", self.size_label)

        self.speed_label = QLabel("0 B/s")
        info_layout.addRow("Speed:", self.speed_label)

        self.eta_label = QLabel("--")
        info_layout.addRow("ETA:", self.eta_label)

        self.status_label = QLabel("Waiting...")
        info_layout.addRow("Status:", self.status_label)

        layout.addLayout(info_layout)

        btn_layout = QHBoxLayout()
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._cancel)
        btn_layout.addWidget(self.pause_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addLayout(btn_layout)

        self.setModal(False)

    def update_status(self, status_data: Optional[Dict[str, Any]]) -> None:
        if not status_data:
            return

        total = int(status_data.get("totalLength", 0))
        completed = int(status_data.get("completedLength", 0))
        speed = int(status_data.get("downloadSpeed", 0))
        eta = int(status_data.get("eta", 0))

        if total > 0:
            progress = int((completed / total) * 100)
            self.progress_bar.setValue(progress)
            self.size_label.setText(f"{format_size(completed)} / {format_size(total)}")
        else:
            self.progress_bar.setValue(0)
            self.size_label.setText(f"{format_size(completed)} / ?")

        self.speed_label.setText(format_speed(speed))
        if eta > 0:
            hours = eta // 3600
            minutes = (eta % 3600) // 60
            seconds = eta % 60
            self.eta_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        else:
            self.eta_label.setText("--")

        status = status_data.get("status", "unknown")
        self._status = status
        status_map = {
            "active": "Downloading",
            "waiting": "Waiting",
            "paused": "Paused",
            "error": "Error",
            "complete": "Complete",
            "removed": "Removed",
        }
        self.status_label.setText(status_map.get(status, status))

        if status in ("complete", "removed"):
            self._completed = True
            self.pause_btn.setEnabled(False)
            self.cancel_btn.setText("Close")
            # Disconnect old signal and connect to accept
            try:
                self.cancel_btn.clicked.disconnect()
            except TypeError:
                pass
            self.cancel_btn.clicked.connect(self.accept)
        else:
            if status == "paused":
                self.pause_btn.setText("Resume")
            else:
                self.pause_btn.setText("Pause")

    def _toggle_pause(self) -> None:
        if self._completed:
            return
        if self._status == "paused":
            self.pause_requested.emit(self.gid, False)
        else:
            self.pause_requested.emit(self.gid, True)

    def _cancel(self) -> None:
        if not self._completed:
            self.cancel_requested.emit(self.gid)
        self.reject()
