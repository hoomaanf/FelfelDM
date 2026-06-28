# ui/dialogs.py
"""
Dialog windows for adding downloads, settings, and progress display.
Refactored AddDownloadDialog into smaller widgets.
"""

import os
import re
import logging
from urllib.parse import urlparse
from typing import List, Optional, Dict, Any, Union, cast

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLineEdit, QTextEdit, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QLabel,
    QFileDialog, QDialogButtonBox, QProgressBar,
    QMessageBox, QTimeEdit, QTabWidget, QWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTime, QByteArray
from PyQt6.QtGui import QIcon

from core.data_store import Queue, DataStore
from core.aria2_rpc import Aria2RPC
from utils.helpers import get_icon, format_size, format_speed, check_disk_space

logger = logging.getLogger(__name__)


def is_valid_url(url: str) -> bool:
    """Validate a URL or magnet link."""
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


class UrlInputWidget(QWidget):
    """Widget for entering URLs with import functionality."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.url_edit = QTextEdit()
        self.url_edit.setPlaceholderText("Enter URLs (one per line)...")
        self.url_edit.setMinimumHeight(80)
        layout.addWidget(self.url_edit)

        import_btn = QPushButton(get_icon('document-open'), "Import from File")
        import_btn.clicked.connect(self._import_from_file)
        layout.addWidget(import_btn)

    def _import_from_file(self) -> None:
        """Import URLs from a text file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import URLs", "", "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    current = self.url_edit.toPlainText()
                    if current and not current.endswith("\n"):
                        current += "\n"
                    self.url_edit.setText(current + content)
            except Exception as e:
                QMessageBox.warning(self, "Import Error", f"Failed to import file: {e}")

    def get_urls(self) -> List[str]:
        """Get list of valid URLs from the text edit."""
        text = self.url_edit.toPlainText()
        urls = []
        for line in text.splitlines():
            line = line.strip()
            if line and is_valid_url(line):
                urls.append(line)
        return urls

    def set_urls(self, urls: List[str]) -> None:
        """Set URLs in the text edit."""
        self.url_edit.setText("\n".join(urls))


class PathSelectorWidget(QWidget):
    """Widget for selecting a save path."""

    path_changed = pyqtSignal(str)

    def __init__(self, default_path: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.path_edit = QLineEdit(default_path or os.path.expanduser("~/Downloads"))
        self.path_edit.textChanged.connect(self.path_changed.emit)
        layout.addWidget(self.path_edit)

        browse = QPushButton(get_icon('folder-open'), "Browse...")
        browse.clicked.connect(self._browse)
        layout.addWidget(browse)

    def _browse(self) -> None:
        """Open a directory selection dialog."""
        path = QFileDialog.getExistingDirectory(self, "Select Save Location", self.path_edit.text())
        if path:
            self.path_edit.setText(path)

    def get_path(self) -> str:
        return self.path_edit.text()

    def set_path(self, path: str) -> None:
        self.path_edit.setText(path)


class OptionsWidget(QWidget):
    """Widget for download options."""

    def __init__(self, queues: List[Queue], default_queue: int = 0, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QFormLayout(self)

        self.queue_cb = QComboBox()
        for q in queues:
            if q.name != "__direct__":
                self.queue_cb.addItem(q.name)
        if default_queue < self.queue_cb.count():
            self.queue_cb.setCurrentIndex(default_queue)
        layout.addRow("Queue:", self.queue_cb)

        self.conn_spin = QSpinBox()
        self.conn_spin.setRange(1, 16)
        self.conn_spin.setValue(16)
        layout.addRow("Connections:", self.conn_spin)

        self.split_spin = QSpinBox()
        self.split_spin.setRange(1, 16)
        self.split_spin.setValue(16)
        layout.addRow("Split:", self.split_spin)

        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 100)
        self.retry_spin.setValue(0)
        self.retry_spin.setSpecialValueText("Unlimited")
        layout.addRow("Max Tries:", self.retry_spin)

        self.pause_check = QCheckBox("Start Paused")
        self.pause_check.setChecked(False)
        layout.addRow("", self.pause_check)

        self.clear_check = QCheckBox("Clear completed after finish")
        layout.addRow("", self.clear_check)

    def get_queue_index(self) -> int:
        return self.queue_cb.currentIndex()

    def get_options(self) -> Dict[str, Any]:
        options = {
            "max-connection-per-server": str(self.conn_spin.value()),
            "split": str(self.split_spin.value()),
        }
        if self.retry_spin.value() > 0:
            options["max-tries"] = str(self.retry_spin.value())
        if self.pause_check.isChecked():
            options["pause"] = "true"
        return options

    def get_pause(self) -> bool:
        return self.pause_check.isChecked()

    def get_clear(self) -> bool:
        return self.clear_check.isChecked()


class AddDownloadDialog(QDialog):
    """
    Dialog for adding multiple downloads with advanced options.
    Now composed of smaller widgets.
    """

    def __init__(
        self,
        queues: List[Queue],
        store: DataStore,
        default_queue: int = 0,
        parent: Optional[QDialog] = None,
    ) -> None:
        super().__init__(parent)
        self._queues = queues
        self._store = store
        self._default_queue = default_queue

        self.setWindowTitle("Add Downloads")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Tab widget
        tabs = QTabWidget()

        # Normal tab
        normal_tab = QWidget()
        normal_layout = QVBoxLayout(normal_tab)

        # URL input
        self.url_widget = UrlInputWidget()
        normal_layout.addWidget(self.url_widget)

        # Path selector
        self.path_widget = PathSelectorWidget()
        normal_layout.addWidget(self.path_widget)

        # Options
        self.options_widget = OptionsWidget(self._queues, self._default_queue)
        normal_layout.addWidget(self.options_widget)

        normal_layout.addStretch()
        tabs.addTab(normal_tab, "Normal")

        # Advanced tab
        advanced_tab = QWidget()
        advanced_layout = QFormLayout(advanced_tab)

        self.header_check = QCheckBox("Add custom headers")
        advanced_layout.addRow("", self.header_check)

        self.header_edit = QTextEdit()
        self.header_edit.setPlaceholderText("Header: value (one per line)")
        self.header_edit.setMaximumHeight(80)
        self.header_edit.setEnabled(False)
        self.header_check.toggled.connect(self.header_edit.setEnabled)
        advanced_layout.addRow("Headers:", self.header_edit)

        self.referer_edit = QLineEdit()
        advanced_layout.addRow("Referer:", self.referer_edit)

        self.user_agent_edit = QLineEdit()
        advanced_layout.addRow("User-Agent:", self.user_agent_edit)

        tabs.addTab(advanced_tab, "Advanced")
        layout.addWidget(tabs)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_urls(self) -> List[str]:
        return self.url_widget.get_urls()

    def set_urls(self, urls: List[str]) -> None:
        self.url_widget.set_urls(urls)

    def get_queue_index(self) -> int:
        return self.options_widget.get_queue_index()

    def get_options(self) -> Dict[str, Any]:
        options = self.options_widget.get_options()

        # Advanced options
        if self.header_check.isChecked():
            headers = self.header_edit.toPlainText().strip()
            if headers:
                options["header"] = [h.strip() for h in headers.splitlines() if h.strip()]

        if self.referer_edit.text().strip():
            options["referer"] = self.referer_edit.text().strip()

        if self.user_agent_edit.text().strip():
            options["user-agent"] = self.user_agent_edit.text().strip()

        # Save path
        path = self.path_widget.get_path()
        if path:
            options["dir"] = path

        return options

    def get_pause(self) -> bool:
        return self.options_widget.get_pause()

    def get_clear(self) -> bool:
        return self.options_widget.get_clear()


class SettingsDialog(QDialog):
    """Settings dialog."""

    def __init__(self, store: DataStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Settings")
        self.setMinimumWidth(400)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # General settings
        group = QGroupBox("General")
        form = QFormLayout(group)

        self.connections_spin = QSpinBox()
        self.connections_spin.setRange(1, 32)
        self.connections_spin.setValue(self.store.settings.get("connections", 8))
        form.addRow("Max Connections:", self.connections_spin)

        self.max_concurrent_spin = QSpinBox()
        self.max_concurrent_spin.setRange(1, 20)
        self.max_concurrent_spin.setValue(self.store.settings.get("max_concurrent", 5))
        form.addRow("Max Concurrent:", self.max_concurrent_spin)

        self.speed_limit_spin = QSpinBox()
        self.speed_limit_spin.setRange(0, 1000000)
        self.speed_limit_spin.setSpecialValueText("Unlimited")
        self.speed_limit_spin.setValue(self.store.settings.get("speed_limit", 0))
        form.addRow("Speed Limit (KB/s):", self.speed_limit_spin)

        self.shutdown_check = QCheckBox()
        self.shutdown_check.setChecked(self.store.settings.get("shutdown_after_finish", False))
        form.addRow("Shutdown after finish:", self.shutdown_check)

        self.auto_clear_check = QCheckBox()
        self.auto_clear_check.setChecked(self.store.settings.get("auto_clear_completed", False))
        form.addRow("Auto-clear completed:", self.auto_clear_check)

        layout.addWidget(group)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        """Save settings."""
        self.store.settings["connections"] = self.connections_spin.value()
        self.store.settings["max_concurrent"] = self.max_concurrent_spin.value()
        self.store.settings["speed_limit"] = self.speed_limit_spin.value()
        self.store.settings["shutdown_after_finish"] = self.shutdown_check.isChecked()
        self.store.settings["auto_clear_completed"] = self.auto_clear_check.isChecked()
        self.store.save()
        self.accept()
