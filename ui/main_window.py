# ui/main_window.py
"""
Main application window - UI coordinator with modern design.
"""

import logging
from typing import List, Optional

from PyQt6.QtCore import (
    Qt, QTimer, pyqtSignal, QObject, QSortFilterProxyModel, QModelIndex,
)
from PyQt6.QtGui import QAction, QKeyEvent, QIcon
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableView, QHeaderView, QComboBox,
    QLabel, QToolBar, QMenu, QSystemTrayIcon, QMenuBar,
    QMessageBox, QLineEdit, QFileDialog, QApplication, QStatusBar,
    QInputDialog, QDialog,
)

from core import Aria2RPC, BackendWorker, DataStore, LocalServer
from core.data_store import Queue
from core.aria2_manager import Aria2Manager
from ui.delegates import ProgressDelegate
from ui.dialogs import AddDownloadDialog, SettingsDialog, AddTorrentDialog, TorrentFileSelectionDialog
from ui.table_model import DownloadTableModel
from ui.icons import get_icon, clear_icon_cache
from ui.animated_dialog import AnimatedDialog
from utils.helpers import format_speed
from utils.style import apply_theme, detect_theme

logger = logging.getLogger(__name__)


class QueueController(QObject):
    """Manages queue operations."""
    queue_changed = pyqtSignal()

    def __init__(self, store: DataStore) -> None:
        super().__init__()
        self.store = store
        self.current_index = 0

    def get_queues(self) -> List[Queue]:
        return self.store.queues

    def get_current_queue(self) -> Optional[Queue]:
        if 0 <= self.current_index < len(self.store.queues):
            return self.store.queues[self.current_index]
        return None

    def set_current_index(self, index: int) -> None:
        if 0 <= index < len(self.store.queues):
            self.current_index = index
            self.queue_changed.emit()

    def toggle_pause(self, index: int) -> None:
        if 0 <= index < len(self.store.queues):
            q = self.store.queues[index]
            q.paused = not q.paused
            self.store.save()
            self.queue_changed.emit()

    def delete_queue(self, index: int) -> bool:
        if 0 <= index < len(self.store.queues):
            q = self.store.queues[index]
            if q.name == "Default":
                return False
            del self.store.queues[index]
            self.store.save()
            self.queue_changed.emit()
            return True
        return False

    def add_queue(self, name: str) -> bool:
        if any(q.name == name for q in self.store.queues):
            return False
        self.store.queues.append(Queue(name, paused=True))
        self.store.save()
        self.queue_changed.emit()
        return True


class DownloadController(QObject):
    """Manages download operations and aria2 communication."""
    download_added = pyqtSignal(str)
    download_removed = pyqtSignal(str)
    download_paused = pyqtSignal(str)
    download_resumed = pyqtSignal(str)

    def __init__(self, aria2: Aria2RPC, store: DataStore) -> None:
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self._cleared_gids = set()

    def add_urls(self, urls: List[str], queue_idx: int, options: dict) -> List[str]:
        if queue_idx >= len(self.store.queues):
            return []

        q = self.store.queues[queue_idx]
        added_gids = []

        for url in urls:
            gid = self.aria2.add_url(url, options)
            if gid:
                added_gids.append(gid)
                self.download_added.emit(gid)

        q.downloads.extend(added_gids)
        self.store.save()
        return added_gids

    def add_torrent(
        self,
        torrent_path: str,
        queue_idx: int,
        options: dict,
        selected_files: Optional[List[int]] = None,
    ) -> Optional[str]:
        if queue_idx >= len(self.store.queues):
            return None

        q = self.store.queues[queue_idx]
        gid = self.aria2.add_torrent(torrent_path, options, selected_files)
        if gid:
            q.downloads.append(gid)
            self.store.save()
            self.download_added.emit(gid)
        return gid

    def start(self, gid: str) -> None:
        result = self.aria2.resume(gid)
        if result is not None:
            self.download_resumed.emit(gid)

    def pause(self, gid: str) -> None:
        result = self.aria2.pause(gid)
        if result is not None:
            self.download_paused.emit(gid)

    def remove(self, gid: str) -> None:
        self.aria2.remove(gid)
        self._cleared_gids.add(gid)
        self.download_removed.emit(gid)

    def is_cleared(self, gid: str) -> bool:
        return gid in self._cleared_gids


class TrayController(QObject):
    """Manages system tray icon and notifications."""
    show_window_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent: QWidget = None) -> None:
        super().__init__(parent)
        self.parent = parent
        self.tray = QSystemTrayIcon(parent)
        self.tray.activated.connect(self._on_tray_activated)
        self._current_progress: Optional[int] = None

        menu = QMenu()
        show_action = QAction("Show", parent)
        show_action.triggered.connect(self.show_window_requested.emit)
        menu.addAction(show_action)

        menu.addSeparator()

        quit_action = QAction("Quit", parent)
        quit_action.triggered.connect(self._on_quit_clicked)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def _on_quit_clicked(self) -> None:
        """Handle quit action from tray menu."""
        self.quit_requested.emit()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window_requested.emit()

    def show_message(self, title: str, message: str,
                     icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information) -> None:
        self.tray.showMessage(title, message, icon)

    def set_icon(self, icon: QIcon) -> None:
        self.tray.setIcon(icon)

    def update_progress(self, progress: Optional[int], speed: Optional[str] = None) -> None:
        self._current_progress = progress

        if progress is not None and progress > 0:
            tooltip = f"FelfelDM\nDownloading: {progress}%"
            if speed:
                tooltip += f"\nSpeed: {speed}"
            self.tray.setToolTip(tooltip)
        else:
            self.tray.setToolTip("FelfelDM\nReady")


class SearchProxyModel(QSortFilterProxyModel):
    """Proxy model for filtering downloads by name."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._filter_text = ""

    def set_filter_text(self, text: str) -> None:
        self._filter_text = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        if not self._filter_text:
            return True

        model = self.sourceModel()
        if model is None:
            return False

        name_index = model.index(source_row, 0)
        name = model.data(name_index, Qt.ItemDataRole.DisplayRole)
        if name and self._filter_text in str(name).lower():
            return True
        return False


class ConnectionIndicator(QLabel):
    """Custom widget for displaying aria2 connection status."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.set_connected(False)

    def set_connected(self, connected: bool) -> None:
        if connected:
            self.setText("● Connected")
            self.setStyleSheet("color: #27ae60; font-weight: bold;")
        else:
            self.setText("● Disconnected")
            self.setStyleSheet("color: #e74c3c; font-weight: bold;")


class AsyncModeIndicator(QLabel):
    """Custom widget for displaying async/sync mode status."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.set_mode(False)

    def set_mode(self, async_mode: bool) -> None:
        if async_mode:
            self.setText("⚡ Async")
            self.setStyleSheet("color: #3498db; font-weight: bold;")
        else:
            self.setText("🔄 Sync")
            self.setStyleSheet("color: #95a5a6; font-weight: bold;")


class MainWindow(QMainWindow):
    """Main application window - UI coordinator with modern design."""

    def __init__(self, container=None) -> None:
        super().__init__()

        self.setWindowTitle("FelfelDM")
        self.setMinimumSize(1050, 680)

        # Core components
        self.store = DataStore()
        self._ensure_default_queue()

        # aria2 manager
        self.aria2_manager = Aria2Manager()
        self.aria2_manager.start()

        # aria2 RPC client - استفاده از attribute به جای .get()
        self.aria2 = Aria2RPC(
            self.store.settings.aria2_host,
            self.store.settings.aria2_port,
            self.store.get_secret(),
            verify_ssl=True,
        )
        self.aria2.on_error = self._on_aria2_error

        # Controllers
        self.download_controller = DownloadController(self.aria2, self.store)
        self.queue_controller = QueueController(self.store)
        self.tray_controller = TrayController(self)

        # Connect controller signals
        self.queue_controller.queue_changed.connect(self._update_queue_ui)
        self.download_controller.download_added.connect(self._on_download_added)

        # Tray signals - CRITICAL: must connect properly
        self.tray_controller.show_window_requested.connect(self.show)
        self.tray_controller.quit_requested.connect(self._quit_app)

        # Build UI
        self._build_ui()

        # Backend worker
        self._setup_worker()

        # Local server
        self._setup_local_server()

        # Timer for UI updates
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_ui)
        self._update_timer.start(1000)

        # Search timer for debouncing
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._apply_search)

        # Apply initial theme
        self._apply_theme_from_settings()

        self._update_tray_icon()

    def _ensure_default_queue(self) -> None:
        if not any(q.name == "Default" for q in self.store.queues):
            self.store.queues.insert(0, Queue("Default", paused=True))
            self.store.save()

    def _setup_worker(self) -> None:
        # استفاده از attribute
        async_mode = self.store.settings.async_mode
        if async_mode:
            from core.async_worker import AsyncWorker
            from core.aria2_rpc_async import AsyncAria2RPC
            async_aria2 = AsyncAria2RPC(
                host=self.aria2.url.rsplit(':', 1)[0],
                port=int(self.aria2.url.rsplit(':', 1)[1].split('/')[0]),
                secret=self.aria2.secret,
                verify_ssl=self.aria2.verify_ssl,
            )
            self.worker = AsyncWorker(async_aria2, self.store)
        else:
            self.worker = BackendWorker(self.aria2, self.store)

        self.worker.stats_updated.connect(self._on_stats_updated)
        self.worker.connection_changed.connect(self._on_connection_changed)
        self.worker.start()

    def _setup_local_server(self) -> None:
        self.local_server = LocalServer(self.download_controller)
        self.local_server.urls_received.connect(self._on_urls_received)
        self.local_server.start()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # Toolbar
        self._build_toolbar(main_layout)

        # Queue selector and controls
        queue_layout = QHBoxLayout()
        self.queue_combo = QComboBox()
        self.queue_combo.currentIndexChanged.connect(self._on_queue_changed)
        queue_layout.addWidget(QLabel("Queue:"))
        queue_layout.addWidget(self.queue_combo)
        queue_layout.addStretch()

        add_queue_btn = QPushButton("+")
        add_queue_btn.setToolTip("Add Queue")
        add_queue_btn.clicked.connect(self._add_queue)
        queue_layout.addWidget(add_queue_btn)

        toggle_queue_btn = QPushButton("⏸")
        toggle_queue_btn.setToolTip("Pause/Resume Queue")
        toggle_queue_btn.clicked.connect(self._toggle_current_queue)
        queue_layout.addWidget(toggle_queue_btn)

        delete_queue_btn = QPushButton("✕")
        delete_queue_btn.setToolTip("Delete Queue")
        delete_queue_btn.clicked.connect(self._delete_current_queue)
        queue_layout.addWidget(delete_queue_btn)

        main_layout.addLayout(queue_layout)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter downloads by name...")
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self.search_edit)
        main_layout.addLayout(search_layout)

        # Table view with proxy model
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)

        self.table_model = DownloadTableModel(self.store, self.queue_controller)
        self.proxy_model = SearchProxyModel(self)
        self.proxy_model.setSourceModel(self.table_model)
        self.table.setModel(self.proxy_model)

        # Set up columns
        for i, name in enumerate(self.table_model.COLS):
            if name == "Category":
                self.table.setColumnWidth(i, 80)
            elif name == "Name":
                self.table.setColumnWidth(i, 300)
            elif name == "Size":
                self.table.setColumnWidth(i, 80)
            elif name == "Progress":
                self.table.setColumnWidth(i, 120)
            elif name == "Speed":
                self.table.setColumnWidth(i, 100)
            elif name == "ETA":
                self.table.setColumnWidth(i, 80)
            elif name == "Status":
                self.table.setColumnWidth(i, 100)
            else:
                self.table.setColumnWidth(i, 100)

        self.table.setItemDelegateForColumn(2, ProgressDelegate(self.table))

        main_layout.addWidget(self.table)

        # Status bar with indicators
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        self.status_label = QLabel("Ready")
        status_bar.addWidget(self.status_label)

        status_bar.addPermanentWidget(self._create_connection_indicator())
        status_bar.addPermanentWidget(self._create_async_mode_indicator())

    def _create_connection_indicator(self) -> ConnectionIndicator:
        self.connection_indicator = ConnectionIndicator()
        self.connection_indicator.set_connected(True)
        return self.connection_indicator

    def _create_async_mode_indicator(self) -> AsyncModeIndicator:
        self.async_mode_indicator = AsyncModeIndicator()
        # استفاده از attribute
        async_mode = self.store.settings.async_mode
        self.async_mode_indicator.set_mode(async_mode)
        return self.async_mode_indicator

    def _build_toolbar(self, parent_layout) -> None:
        toolbar = QToolBar()
        toolbar.setMovable(False)

        add_action = QAction(get_icon("list-add"), "Add Download", self)
        add_action.triggered.connect(self._show_add_dialog)
        toolbar.addAction(add_action)

        torrent_action = QAction(get_icon("torrent"), "Add Torrent", self)
        torrent_action.triggered.connect(self._show_add_torrent_dialog)
        toolbar.addAction(torrent_action)

        toolbar.addSeparator()

        start_action = QAction(get_icon("media-playback-start"), "Start", self)
        start_action.triggered.connect(self._start_selected)
        toolbar.addAction(start_action)

        pause_action = QAction(get_icon("media-playback-pause"), "Pause", self)
        pause_action.triggered.connect(self._pause_selected)
        toolbar.addAction(pause_action)

        remove_action = QAction(get_icon("edit-delete"), "Remove", self)
        remove_action.triggered.connect(self._remove_selected)
        toolbar.addAction(remove_action)

        toolbar.addSeparator()

        settings_action = QAction(get_icon("preferences-system"), "Settings", self)
        settings_action.triggered.connect(self._show_settings)
        toolbar.addAction(settings_action)

        parent_layout.addWidget(toolbar)

    def _update_queue_ui(self) -> None:
        current = self.queue_combo.currentIndex()
        self.queue_combo.clear()
        for q in self.queue_controller.get_queues():
            self.queue_combo.addItem(q.name)

        if 0 <= current < self.queue_combo.count():
            self.queue_combo.setCurrentIndex(current)
        elif self.queue_combo.count() > 0:
            self.queue_combo.setCurrentIndex(0)

        self.table_model.refresh()

    def _on_queue_changed(self, index: int) -> None:
        self.queue_controller.set_current_index(index)
        self.table_model.refresh()

    def _add_queue(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Queue", "Queue name:")
        if ok and name.strip():
            self.queue_controller.add_queue(name.strip())

    def _toggle_current_queue(self) -> None:
        idx = self.queue_combo.currentIndex()
        if idx >= 0:
            self.queue_controller.toggle_pause(idx)

    def _delete_current_queue(self) -> None:
        idx = self.queue_combo.currentIndex()
        if idx >= 0:
            if not self.queue_controller.delete_queue(idx):
                QMessageBox.warning(self, "Cannot Delete", "Cannot delete the Default queue.")

    def _show_add_dialog(self) -> None:
        """Show the Add Download dialog."""
        dialog = AddDownloadDialog(
            self.queue_controller.get_queues(),
            self.store,
            self.queue_controller.current_index,
            self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            urls = dialog.get_urls()
            queue_idx = dialog.get_queue_index()
            options = dialog.get_options()
            if urls:
                self.download_controller.add_urls(urls, queue_idx, options)

    def _show_add_torrent_dialog(self) -> None:
        """Show the Add Torrent dialog."""
        dialog = AddTorrentDialog(
            self.queue_controller.get_queues(),
            self.store,
            self.queue_controller.current_index,
            self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            torrent_path = dialog.get_torrent_path()
            queue_idx = dialog.get_queue_index()
            options = dialog.get_options()

            if not torrent_path:
                QMessageBox.warning(self, "Error", "No torrent file selected.")
                return

            # Try to get torrent info for file selection
            try:
                torrent_info = self.aria2.get_torrent_info(torrent_path)
                if torrent_info and torrent_info.get('files'):
                    file_dialog = TorrentFileSelectionDialog(torrent_info, torrent_path, self)
                    if file_dialog.exec():
                        selected_files = file_dialog.get_selected_files()
                        if not selected_files:
                            QMessageBox.warning(self, "No Files Selected",
                                                "Please select at least one file to download.")
                            return
                        gid = self.download_controller.add_torrent(
                            torrent_path, queue_idx, options, selected_files
                        )
                        if gid:
                            QMessageBox.information(self, "Success", "Torrent added successfully.")
                        else:
                            QMessageBox.warning(self, "Error", "Failed to add torrent.")
                    return
            except Exception as e:
                logger.warning("Could not get torrent info: %s", e)

            # Fallback: add without file selection
            gid = self.download_controller.add_torrent(torrent_path, queue_idx, options)
            if gid:
                QMessageBox.information(self, "Success", "Torrent added successfully.")
            else:
                QMessageBox.warning(self, "Error", "Failed to add torrent.")

    def _start_selected(self) -> None:
        selection = self.table.selectionModel().selectedRows()
        for idx in selection:
            source_idx = self.proxy_model.mapToSource(idx)
            gid = self.table_model.get_gid(source_idx.row())
            if gid:
                self.download_controller.start(gid)

    def _pause_selected(self) -> None:
        selection = self.table.selectionModel().selectedRows()
        for idx in selection:
            source_idx = self.proxy_model.mapToSource(idx)
            gid = self.table_model.get_gid(source_idx.row())
            if gid:
                self.download_controller.pause(gid)

    def _remove_selected(self) -> None:
        selection = self.table.selectionModel().selectedRows()
        if not selection:
            return
        if QMessageBox.question(self, "Remove Downloads",
                               f"Remove {len(selection)} download(s)?",
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            for idx in selection:
                source_idx = self.proxy_model.mapToSource(idx)
                gid = self.table_model.get_gid(source_idx.row())
                if gid:
                    self.download_controller.remove(gid)
            self.table_model.refresh()

    def _show_settings(self) -> None:
        """Show the Settings dialog."""
        dialog = SettingsDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Reload settings
            self._apply_theme_from_settings()
            # استفاده از attribute
            async_mode = self.store.settings.async_mode
            self.async_mode_indicator.set_mode(async_mode)
            # Restart worker if async mode changed
            self._restart_worker()

    def _restart_worker(self) -> None:
        """Restart the backend worker."""
        if hasattr(self, 'worker'):
            self.worker.stop()
        self._setup_worker()

    def _apply_theme_from_settings(self) -> None:
        """Apply the theme based on settings."""
        try:
            theme_setting = self.store.settings.theme
            if theme_setting == "system":
                is_dark = detect_theme()
            elif theme_setting == "dark":
                is_dark = True
            else:
                is_dark = False

            apply_theme(self, is_dark)

            # Clear icon cache and update icons
            clear_icon_cache()
            self._update_tray_icon()
            # Force UI update
            self.update()
            logger.info("Theme applied: %s", "Dark" if is_dark else "Light")
        except Exception as e:
            logger.error("Failed to apply theme: %s", e)

    def _on_aria2_error(self, msg: str) -> None:
        logger.error("aria2 error: %s", msg)
        self.status_label.setText(f"Error: {msg}")

    def _on_stats_updated(self, stats: dict) -> None:
        self.table_model.refresh()

        if "global" in stats:
            gs = stats["global"]
            if gs:
                speed = format_speed(gs.get("downloadSpeed", 0))
                self.status_label.setText(f"Download Speed: {speed}")

                total_downloaded = gs.get("totalDownloaded", 0)
                total_uploaded = gs.get("totalUploaded", 0)
                total = total_downloaded + total_uploaded
                if total > 0:
                    progress = min(100, int((total_downloaded / total) * 100))
                    self.tray_controller.update_progress(progress, speed)
                else:
                    self.tray_controller.update_progress(None, speed)

        if stats.get("connected", True):
            self.connection_indicator.set_connected(True)
        else:
            self.connection_indicator.set_connected(False)

    def _on_connection_changed(self, connected: bool) -> None:
        if connected:
            self.status_label.setText("Connected to aria2")
        else:
            self.status_label.setText("Disconnected from aria2")
        self.connection_indicator.set_connected(connected)

    def _on_download_added(self, gid: str) -> None:
        self.table_model.refresh()
        self.tray_controller.show_message(
            "Download Started",
            f"New download added: {gid[:8]}"
        )

    def _on_urls_received(self, urls: List[str]) -> None:
        dialog = AddDownloadDialog(
            self.queue_controller.get_queues(),
            self.store,
            self.queue_controller.current_index,
            self
        )
        dialog.set_urls(urls)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            urls = dialog.get_urls()
            queue_idx = dialog.get_queue_index()
            options = dialog.get_options()
            if urls:
                self.download_controller.add_urls(urls, queue_idx, options)

    def _update_ui(self) -> None:
        """Periodic UI updates."""
        pass

    def _update_tray_icon(self) -> None:
        """Update the tray icon with themed icon."""
        is_dark = False
        try:
            palette = self.palette()
            bg = palette.color(QPalette.ColorRole.Window)
            brightness = (bg.red() * 299 + bg.green() * 587 + bg.blue() * 114) / 1000
            is_dark = brightness < 128
        except Exception:
            pass

        # Use a simple built-in icon
        icon = get_icon("download", is_dark)
        if icon.isNull():
            icon = QIcon.fromTheme("download")
        if icon.isNull():
            icon = QIcon.fromTheme("folder-download")
        if icon.isNull():
            # Fallback: create a simple icon
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor(0, 0, 0, 0))
            from PyQt6.QtGui import QPainter, QColor
            painter = QPainter(pixmap)
            painter.setBrush(QColor("#e67e22"))
            painter.setPen(QColor("#e67e22"))
            painter.drawRoundedRect(10, 10, 44, 44, 8, 8)
            painter.end()
            icon = QIcon(pixmap)

        self.tray_controller.set_icon(icon)

    def _on_search_text_changed(self, text: str) -> None:
        self._search_timer.start(300)

    def _apply_search(self) -> None:
        text = self.search_edit.text()
        self.proxy_model.set_filter_text(text)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Delete:
            self._remove_selected()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self._start_selected()
        elif event.key() == Qt.Key.Key_N and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._show_add_dialog()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        event.ignore()
        self.hide()
        self.tray_controller.show_message(
            "FelfelDM",
            "Application minimized to system tray"
        )

    def _quit_app(self) -> None:
        """Cleanly quit the application."""
        logger.info("Quitting application...")

        # Stop worker
        if hasattr(self, 'worker'):
            self.worker.stop()

        # Stop local server
        if hasattr(self, 'local_server'):
            self.local_server.stop()

        # Stop aria2
        if hasattr(self, 'aria2_manager'):
            self.aria2_manager.stop()

        # Close RPC connection
        if hasattr(self, 'aria2'):
            self.aria2.close()

        # Quit application
        QApplication.quit()
