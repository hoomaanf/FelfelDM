# ui/dialogs.py
"""
Dialog windows for adding downloads, settings, torrent file selection,
schedule configuration, and progress display.
"""

import logging
import os
from typing import List, Optional, Dict, Any

from PyQt6.QtCore import Qt, pyqtSignal, QDate, QTime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QLineEdit, QTextEdit, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QLabel,
    QFileDialog, QDialogButtonBox, QWidget,
    QListWidget, QListWidgetItem, QMessageBox,
    QCalendarWidget, QTimeEdit, QTabWidget, QProgressBar,
)

import validators
from core.data_store import Queue, DataStore
from core.constants import DEFAULT_DOWNLOAD_PATH
from ui.icons import get_icon
from ui.animated_dialog import AnimatedDialog

logger = logging.getLogger(__name__)


def is_valid_url(url: str) -> bool:
    """Validate a URL or magnet link using validators library."""
    if not url or not url.strip():
        return False

    url = url.strip()

    if url.startswith("magnet:?xt=urn:"):
        return True

    if validators.url(url):
        return True

    if validators.domain(url) or validators.ip_address.ipv4(url) or validators.ip_address.ipv6(url):
        return True

    if url == "localhost" or url.startswith("localhost:"):
        return True

    return False


class AnimatedDialogWrapper(AnimatedDialog):
    """Wrapper for adding animation to any QDialog content."""
    
    def __init__(self, content_widget: QWidget, parent: QWidget = None, **kwargs):
        super().__init__(parent, **kwargs)
        self.set_content_widget(content_widget)
        if hasattr(content_widget, 'windowTitle'):
            self.setWindowTitle(content_widget.windowTitle())


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

        import_btn = QPushButton(get_icon("document-new"), "Import from File")
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

        self.path_edit = QLineEdit(default_path or str(DEFAULT_DOWNLOAD_PATH))
        self.path_edit.textChanged.connect(self.path_changed.emit)
        layout.addWidget(self.path_edit)

        browse = QPushButton(get_icon("folder-open"), "Browse...")
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
    """Widget for download options including speed limit."""

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

        self.speed_limit_spin = QSpinBox()
        self.speed_limit_spin.setRange(0, 1000000)
        self.speed_limit_spin.setSpecialValueText("Unlimited")
        self.speed_limit_spin.setValue(0)
        layout.addRow("Speed Limit (KB/s):", self.speed_limit_spin)

        self.pause_check = QCheckBox("Start Paused")
        self.pause_check.setChecked(False)
        layout.addRow("", self.pause_check)

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
        speed_limit = self.speed_limit_spin.value()
        if speed_limit > 0:
            options["max-download-limit"] = f"{speed_limit}K"
        return options

    def get_pause(self) -> bool:
        return self.pause_check.isChecked()


class AddDownloadDialog(QDialog):
    """Dialog for adding multiple downloads with advanced options."""

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
        path = self.path_widget.get_path()
        if path:
            options["dir"] = path
        return options

    def get_pause(self) -> bool:
        return self.options_widget.get_pause()


class AddTorrentDialog(QDialog):
    """Dialog for adding a torrent with file selection and options."""

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

    def get_pause(self) -> bool:
        return self.options_widget.get_pause()


class TorrentFileSelectionDialog(QDialog):
    """Dialog for selecting files from a torrent with progress display."""

    def __init__(
        self,
        torrent_info: Dict[str, Any],
        torrent_path: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.torrent_info = torrent_info
        self.torrent_path = torrent_path
        self._gid: Optional[str] = None

        self.setWindowTitle("Select Torrent Files")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        info_text = f"Torrent: {self.torrent_info.get('name', 'Unknown')}"
        if 'totalLength' in self.torrent_info:
            from utils.helpers import format_size
            info_text += f" (Size: {format_size(self.torrent_info['totalLength'])})"
        info_label = QLabel(info_text)
        layout.addWidget(info_label)

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

        # Progress section for when download is active
        progress_group = QGroupBox("Download Progress")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        progress_layout.addWidget(self.progress_bar)
        
        self.progress_label = QLabel("Waiting for download to start...")
        progress_layout.addWidget(self.progress_label)
        
        layout.addWidget(progress_group)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Timer for progress updates
        self._progress_timer = QTimer()
        self._progress_timer.timeout.connect(self._update_progress)
        self._progress_timer.start(1000)

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

    def set_gid(self, gid: str) -> None:
        self._gid = gid
        self.progress_label.setText("Download started...")

    def _update_progress(self) -> None:
        """Update the progress bar from aria2 status."""
        if not self._gid:
            return
        
        try:
            from core import Aria2RPC
            # This assumes we have access to aria2 instance
            # In practice, this should be connected via a signal
            pass
        except Exception as e:
            logger.debug("Progress update failed: %s", e)


class SettingsDialog(QDialog):
    """Settings dialog with theme, default path, and async option."""

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
        self.connections_spin.setValue(self.store.settings.get("connections", 16))
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

        current_theme = self.store.settings.get("theme", "system")
        idx = self.theme_combo.findData(current_theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        theme_form.addRow("Theme:", self.theme_combo)

        layout.addWidget(theme_group)

        # Async mode option
        async_group = QGroupBox("Performance")
        async_form = QFormLayout(async_group)

        self.async_check = QCheckBox()
        self.async_check.setChecked(self.store.settings.get("async_mode", False))
        async_form.addRow("Use Async Mode (experimental):", self.async_check)

        layout.addWidget(async_group)

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
        self.store.settings["connections"] = self.connections_spin.value()
        self.store.settings["max_concurrent"] = self.max_concurrent_spin.value()
        self.store.settings["speed_limit"] = self.speed_limit_spin.value()
        self.store.settings["shutdown_after_finish"] = self.shutdown_check.isChecked()
        self.store.settings["theme"] = self.theme_combo.currentData()
        self.store.set_default_download_path(self.default_path_edit.text())
        self.store.settings["async_mode"] = self.async_check.isChecked()
        self.store.save()
        self.accept()
