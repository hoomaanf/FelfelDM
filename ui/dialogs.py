# ui/dialogs.py
"""
Dialog windows for adding downloads, settings, torrent file selection,
and progress display.
"""

import logging
import os
from typing import List, Optional, Dict, Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLineEdit, QTextEdit, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QLabel,
    QFileDialog, QDialogButtonBox, QWidget,
    QListWidget, QListWidgetItem, QMessageBox,
)

import validators
from core.data_store import Queue, DataStore
from ui.icons import get_icon

logger = logging.getLogger(__name__)


def is_valid_url(url: str) -> bool:
    """
    Validate a URL or magnet link using the validators library.

    Supports:
    - HTTP/HTTPS URLs
    - FTP URLs
    - Magnet links
    - IPv4 and IPv6 addresses
    - Localhost
    """
    if not url or not url.strip():
        return False

    url = url.strip()

    # Magnet links
    if url.startswith("magnet:?xt=urn:"):
        return True

    # Use validators library for comprehensive validation
    if validators.url(url):
        return True

    # Also support raw IP/domain without scheme
    if validators.domain(url) or validators.ip_address.ipv4(url) or validators.ip_address.ipv6(url):
        return True

    # Support localhost
    if url == "localhost" or url.startswith("localhost:"):
        return True

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

        import_btn = QPushButton(get_icon('document-new'), "Import from File")
        import_btn.clicked.connect(self._import_from_file)
        layout.addWidget(import_btn)

    def _import_from_file(self) -> None:
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
        text = self.url_edit.toPlainText()
        urls = []
        for line in text.splitlines():
            line = line.strip()
            if line and is_valid_url(line):
                urls.append(line)
        return urls

    def set_urls(self, urls: List[str]) -> None:
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


class TorrentFileSelectionDialog(QDialog):
    """Dialog for selecting files from a torrent."""

    def __init__(
        self,
        torrent_info: Dict[str, Any],
        torrent_path: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.torrent_info = torrent_info
        self.torrent_path = torrent_path
        self.selected_indices: List[int] = []

        self.setWindowTitle("Select Torrent Files")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Info label
        info_text = f"Torrent: {self.torrent_info.get('name', 'Unknown')}"
        if 'totalLength' in self.torrent_info:
            from utils.helpers import format_size
            info_text += f" (Size: {format_size(self.torrent_info['totalLength'])})"
        info_label = QLabel(info_text)
        layout.addWidget(info_label)

        # File list
        self.file_list = QListWidget()
        files = self.torrent_info.get('files', [])
        if isinstance(files, list):
            for idx, file_info in enumerate(files):
                if isinstance(file_info, dict):
                    name = file_info.get('path', f'File {idx+1}')
                    size = file_info.get('length', 0)
                    from utils.helpers import format_size
                    item_text = f"{name} ({format_size(size)})"
                    item = QListWidgetItem(item_text)
                    item.setData(Qt.ItemDataRole.UserRole, idx + 1)
                    item.setCheckState(Qt.CheckState.Checked)
                    self.file_list.addItem(item)

        # Select all / None buttons
        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        btn_layout.addWidget(select_all_btn)

        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(self._select_none)
        btn_layout.addWidget(select_none_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        layout.addWidget(self.file_list)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _select_all(self) -> None:
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item:
                item.setCheckState(Qt.CheckState.Checked)

    def _select_none(self) -> None:
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item:
                item.setCheckState(Qt.CheckState.Unchecked)

    def get_selected_files(self) -> List[int]:
        indices = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                idx = item.data(Qt.ItemDataRole.UserRole)
                if idx:
                    indices.append(idx)
        return indices


class AddTorrentDialog(QDialog):
    """Dialog for adding a torrent with file selection."""

    def __init__(
        self,
        queues: List[Queue],
        store: DataStore,
        default_queue: int = 0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._queues = queues
        self._store = store
        self._default_queue = default_queue
        self._torrent_path: Optional[str] = None
        self._torrent_info: Optional[Dict[str, Any]] = None
        self._selected_files: List[int] = []

        self.setWindowTitle("Add Torrent")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Torrent file selection
        file_layout = QHBoxLayout()
        self.file_label = QLabel("No torrent selected")
        file_layout.addWidget(self.file_label)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_torrent)
        file_layout.addWidget(browse_btn)
        layout.addLayout(file_layout)

        # Options
        self.options_widget = OptionsWidget(self._queues, self._default_queue)
        layout.addWidget(self.options_widget)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_torrent(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Torrent File", "", "Torrent Files (*.torrent);;All Files (*)"
        )
        if file_path:
            self._torrent_path = file_path
            self.file_label.setText(os.path.basename(file_path))

    def get_torrent_path(self) -> Optional[str]:
        return self._torrent_path

    def get_queue_index(self) -> int:
        return self.options_widget.get_queue_index()

    def get_options(self) -> Dict[str, Any]:
        return self.options_widget.get_options()

    def get_selected_files(self) -> List[int]:
        return self._selected_files


class SettingsDialog(QDialog):
    """Settings dialog with theme selection and default download path."""

    def __init__(self, store: DataStore, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # General settings
        group = QGroupBox("General")
        form = QFormLayout(group)

        self.connections_spin = QSpinBox()
        self.connections_spin.setRange(1, 32)
        self.connections_spin.setValue(self.store.settings.connections)
        form.addRow("Max Connections:", self.connections_spin)

        self.max_concurrent_spin = QSpinBox()
        self.max_concurrent_spin.setRange(1, 20)
        self.max_concurrent_spin.setValue(self.store.settings.max_concurrent)
        form.addRow("Max Concurrent:", self.max_concurrent_spin)

        self.speed_limit_spin = QSpinBox()
        self.speed_limit_spin.setRange(0, 1000000)
        self.speed_limit_spin.setSpecialValueText("Unlimited")
        self.speed_limit_spin.setValue(self.store.settings.speed_limit)
        form.addRow("Speed Limit (KB/s):", self.speed_limit_spin)

        self.shutdown_check = QCheckBox()
        self.shutdown_check.setChecked(self.store.settings.shutdown_after_finish)
        form.addRow("Shutdown after finish:", self.shutdown_check)

        self.auto_clear_check = QCheckBox()
        self.auto_clear_check.setChecked(self.store.settings.auto_clear_completed)
        form.addRow("Auto-clear completed:", self.auto_clear_check)

        # Default download path
        default_path_layout = QHBoxLayout()
        self.default_path_edit = QLineEdit(self.store.get_default_download_path())
        default_path_layout.addWidget(self.default_path_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_default_path)
        default_path_layout.addWidget(browse_btn)
        form.addRow("Default Download Path:", default_path_layout)

        layout.addWidget(group)

        # Theme settings
        theme_group = QGroupBox("Appearance")
        theme_form = QFormLayout(theme_group)

        self.theme_combo = QComboBox()
        self.theme_combo.addItem("System (Auto)", "system")
        self.theme_combo.addItem("Dark", "dark")
        self.theme_combo.addItem("Light", "light")

        current_theme = self.store.settings.theme
        idx = self.theme_combo.findData(current_theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        theme_form.addRow("Theme:", self.theme_combo)

        layout.addWidget(theme_group)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse_default_path(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "Select Default Download Location", self.default_path_edit.text()
        )
        if path:
            self.default_path_edit.setText(path)

    def _save(self) -> None:
        self.store.settings.connections = self.connections_spin.value()
        self.store.settings.max_concurrent = self.max_concurrent_spin.value()
        self.store.settings.speed_limit = self.speed_limit_spin.value()
        self.store.settings.shutdown_after_finish = self.shutdown_check.isChecked()
        self.store.settings.auto_clear_completed = self.auto_clear_check.isChecked()
        self.store.settings.theme = self.theme_combo.currentData()
        self.store.set_default_download_path(self.default_path_edit.text())
        self.store.save()
        self.accept()


class AddDownloadDialog(QDialog):
    """Dialog for adding multiple downloads with advanced options."""

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

        # URL input
        self.url_widget = UrlInputWidget()
        layout.addWidget(self.url_widget)

        # Path selector with default from store
        default_path = self._store.get_default_download_path()
        self.path_widget = PathSelectorWidget(default_path)
        layout.addWidget(self.path_widget)

        # Options
        self.options_widget = OptionsWidget(self._queues, self._default_queue)
        layout.addWidget(self.options_widget)

        # Advanced tab
        advanced_group = QGroupBox("Advanced Options")
        advanced_layout = QFormLayout(advanced_group)

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

        layout.addWidget(advanced_group)

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

        if self.header_check.isChecked():
            headers = self.header_edit.toPlainText().strip()
            if headers:
                options["header"] = [h.strip() for h in headers.splitlines() if h.strip()]

        if self.referer_edit.text().strip():
            options["referer"] = self.referer_edit.text().strip()

        if self.user_agent_edit.text().strip():
            options["user-agent"] = self.user_agent_edit.text().strip()

        path = self.path_widget.get_path()
        if path:
            options["dir"] = path

        return options

    def get_pause(self) -> bool:
        return self.options_widget.get_pause()

    def get_clear(self) -> bool:
        return self.options_widget.get_clear()
