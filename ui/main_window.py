# ui/main_window.py
"""
Main application window - now acts as UI coordinator.
Refactored to delegate responsibilities to specialized controllers.
"""

import logging
import os
from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QAction, QKeyEvent
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableView, QHeaderView, QComboBox,
    QLabel, QToolBar, QMenu, QSystemTrayIcon, QMenuBar,
    QMessageBox, QSplitter, QFrame, QStackedWidget,
)

from core import Aria2RPC, BackendWorker, DataStore, LocalServer
from core.data_store import Queue
from core.aria2_manager import Aria2Manager
from ui.delegates import ProgressDelegate
from ui.dialogs import AddDownloadDialog, SettingsDialog
from ui.table_model import DownloadTableModel
from utils.helpers import format_speed, get_category, get_icon, format_size

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

    download_added = pyqtSignal(str)  # gid
    download_removed = pyqtSignal(str)  # gid
    download_paused = pyqtSignal(str)  # gid
    download_resumed = pyqtSignal(str)  # gid

    def __init__(self, aria2: Aria2RPC, store: DataStore) -> None:
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self._cleared_gids: set = set()

    def add_urls(self, urls: List[str], queue_idx: int, options: dict) -> List[str]:
        """Add URLs to the specified queue and return list of GIDs."""
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
        self.tray = QSystemTrayIcon(parent)
        self.tray.activated.connect(self._on_tray_activated)

        # Set up tray menu
        menu = QMenu()
        show_action = QAction("Show", parent)
        show_action.triggered.connect(self.show_window_requested.emit)
        menu.addAction(show_action)

        menu.addSeparator()

        quit_action = QAction("Quit", parent)
        quit_action.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window_requested.emit()

    def show_message(self, title: str, message: str, icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information) -> None:
        self.tray.showMessage(title, message, icon)

    def set_icon(self, icon) -> None:
        self.tray.setIcon(icon)


class MainWindow(QMainWindow):
    """
    Main application window - now acts as UI coordinator.
    Delegates responsibilities to QueueController, DownloadController, and TrayController.
    """

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("FelfelDM")
        self.setMinimumSize(1050, 680)

        # Core components
        self.store = DataStore()
        self._ensure_default_queue()

        # Aria2 manager (starts the subprocess)
        self.aria2_manager = Aria2Manager()
        self.aria2_manager.start()

        # RPC client
        self.aria2 = Aria2RPC(
            self.store.settings["aria2_host"],
            self.store.settings["aria2_port"],
            self.store.settings["aria2_secret"],
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

        # Tray signals
        self.tray_controller.show_window_requested.connect(self.show)
        self.tray_controller.quit_requested.connect(self._quit_app)

        # Build UI
        self._build_ui()

        # Backend worker for polling
        self._setup_worker()

        # Local server for browser extension
        self._setup_local_server()

        # Timer for periodic UI updates
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._update_ui)
        self._update_timer.start(1000)

        # Ensure tray icon is set
        self._update_tray_icon()

    def _ensure_default_queue(self) -> None:
        if not any(q.name == "Default" for q in self.store.queues):
            self.store.queues.insert(0, Queue("Default", paused=True))
            self.store.save()

    def _setup_worker(self) -> None:
        """Set up the background worker for polling aria2."""
        self.worker = BackendWorker(self.aria2, self.store)
        self.worker.stats_updated.connect(self._on_stats_updated)
        self.worker.connection_changed.connect(self._on_connection_changed)
        self.worker.start()

    def _setup_local_server(self) -> None:
        """Set up the local HTTP server for browser extension."""
        self.local_server = LocalServer(self.download_controller)
        self.local_server.urls_received.connect(self._on_urls_received)
        self.local_server.start()

    def _build_ui(self) -> None:
        """Build the user interface."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Toolbar
        self._build_toolbar(main_layout)

        # Main content
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(10, 10, 10, 10)

        # Queue selector and controls
        queue_layout = QHBoxLayout()
        self.queue_combo = QComboBox()
        self.queue_combo.currentIndexChanged.connect(self._on_queue_changed)
        queue_layout.addWidget(QLabel("Queue:"))
        queue_layout.addWidget(self.queue_combo)
        queue_layout.addStretch()

        # Queue management buttons
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

        content_layout.addLayout(queue_layout)

        # Table view
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)

        self.table_model = DownloadTableModel(self.store, self.queue_controller)
        self.table.setModel(self.table_model)

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

        # Set progress delegate
        self.table.setItemDelegateForColumn(2, ProgressDelegate(self.table))

        content_layout.addWidget(self.table)

        # Status bar
        self.status_label = QLabel("Ready")
        content_layout.addWidget(self.status_label)

        main_layout.addWidget(content)

        # Update queue combo
        self._update_queue_ui()

    def _build_toolbar(self, parent_layout) -> None:
        """Build the toolbar."""
        toolbar = QToolBar()
        toolbar.setMovable(False)

        # Add download button
        add_action = QAction(get_icon("list-add"), "Add Download", self)
        add_action.triggered.connect(self._show_add_dialog)
        toolbar.addAction(add_action)

        toolbar.addSeparator()

        # Start/pause/remove actions
        start_action = QAction(get_icon("media-playback-start"), "Start", self)
        start_action.triggered.connect(self._start_selected)
        toolbar.addAction(start_action)

        pause_action = QAction(get_icon("media-playback-pause"), "Pause", self)
        pause_action.triggered.connect(self._pause_selected)
        toolbar.addAction(pause_action)

        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(self._remove_selected)
        toolbar.addAction(remove_action)

        toolbar.addSeparator()

        # Settings
        settings_action = QAction(get_icon("preferences-system"), "Settings", self)
        settings_action.triggered.connect(self._show_settings)
        toolbar.addAction(settings_action)

        parent_layout.addWidget(toolbar)

    def _update_queue_ui(self) -> None:
        """Update the queue combo box and table."""
        current = self.queue_combo.currentIndex()
        self.queue_combo.clear()
        for q in self.queue_controller.get_queues():
            self.queue_combo.addItem(q.name)

        # Restore selection
        if 0 <= current < self.queue_combo.count():
            self.queue_combo.setCurrentIndex(current)
        elif self.queue_combo.count() > 0:
            self.queue_combo.setCurrentIndex(0)

        # Update table
        self.table_model.refresh()

    def _on_queue_changed(self, index: int) -> None:
        """Handle queue selection change."""
        self.queue_controller.set_current_index(index)
        self.table_model.refresh()

    def _add_queue(self) -> None:
        """Add a new queue."""
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Add Queue", "Queue name:")
        if ok and name:
            self.queue_controller.add_queue(name)

    def _toggle_current_queue(self) -> None:
        """Toggle pause/resume of the current queue."""
        idx = self.queue_combo.currentIndex()
        self.queue_controller.toggle_pause(idx)

    def _delete_current_queue(self) -> None:
        """Delete the current queue."""
        idx = self.queue_combo.currentIndex()
        if idx >= 0:
            self.queue_controller.delete_queue(idx)

    def _show_add_dialog(self) -> None:
        """Show the Add Download dialog."""
        dialog = AddDownloadDialog(
            self.queue_controller.get_queues(),
            self.store,
            self.queue_controller.current_index,
            self
        )
        if dialog.exec():
            urls = dialog.get_urls()
            queue_idx = dialog.get_queue_index()
            options = dialog.get_options()
            if urls:
                self.download_controller.add_urls(urls, queue_idx, options)

    def _start_selected(self) -> None:
        """Start the selected download."""
        selection = self.table.selectionModel().selectedRows()
        for idx in selection:
            gid = self.table_model.get_gid(idx.row())
            if gid:
                self.download_controller.start(gid)

    def _pause_selected(self) -> None:
        """Pause the selected download."""
        selection = self.table.selectionModel().selectedRows()
        for idx in selection:
            gid = self.table_model.get_gid(idx.row())
            if gid:
                self.download_controller.pause(gid)

    def _remove_selected(self) -> None:
        """Remove the selected download."""
        selection = self.table.selectionModel().selectedRows()
        for idx in selection:
            gid = self.table_model.get_gid(idx.row())
            if gid:
                self.download_controller.remove(gid)
        self.table_model.refresh()

    def _show_settings(self) -> None:
        """Show the Settings dialog."""
        dialog = SettingsDialog(self.store, self)
        if dialog.exec():
            # Reconnect if settings changed
            pass

    def _on_aria2_error(self, msg: str) -> None:
        """Handle aria2 errors."""
        logger.error("aria2 error: %s", msg)
        self.status_label.setText(f"Error: {msg}")

    def _on_stats_updated(self, stats: dict) -> None:
        """Update UI with new stats."""
        self.table_model.refresh()
        # Update status label with global stats
        if "global" in stats:
            gs = stats["global"]
            speed = format_speed(gs.get("downloadSpeed", 0))
            self.status_label.setText(f"Download Speed: {speed}")

    def _on_connection_changed(self, connected: bool) -> None:
        """Handle connection status change."""
        if connected:
            self.status_label.setText("Connected to aria2")
        else:
            self.status_label.setText("Disconnected from aria2")

    def _on_download_added(self, gid: str) -> None:
        """Handle download added event."""
        self.table_model.refresh()
        self.tray_controller.show_message(
            "Download Started",
            f"New download added: {gid[:8]}"
        )

    def _on_urls_received(self, urls: List[str]) -> None:
        """Handle URLs received from browser extension."""
        dialog = AddDownloadDialog(
            self.queue_controller.get_queues(),
            self.store,
            self.queue_controller.current_index,
            self
        )
        dialog.set_urls(urls)
        if dialog.exec():
            urls = dialog.get_urls()
            queue_idx = dialog.get_queue_index()
            options = dialog.get_options()
            if urls:
                self.download_controller.add_urls(urls, queue_idx, options)

    def _update_ui(self) -> None:
        """Periodic UI update."""
        # Update tray icon with download speed if needed
        pass

    def _update_tray_icon(self) -> None:
        """Update the tray icon."""
        # Set a default icon
        from PyQt6.QtGui import QIcon
        self.tray_controller.set_icon(QIcon.fromTheme("download"))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key press events."""
        if event.key() == Qt.Key.Key_Delete:
            self._remove_selected()
        elif event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self._start_selected()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        """Handle close event - hide to tray instead of closing."""
        event.ignore()
        self.hide()
        self.tray_controller.show_message(
            "FelfelDM",
            "Application minimized to system tray"
        )

    def _quit_app(self) -> None:
        """Quit the application."""
        # Stop worker
        if hasattr(self, 'worker'):
            self.worker.stop()
        # Stop local server
        if hasattr(self, 'local_server'):
            self.local_server.stop()
        # Stop aria2
        self.aria2_manager.stop()
        QApplication.quit()
