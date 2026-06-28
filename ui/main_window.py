# ui/main_window.py
"""
Main application window - now acts as UI coordinator.
"""

import logging
from typing import List, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QSortFilterProxyModel
from PyQt6.QtGui import QAction, QKeyEvent
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableView, QHeaderView, QComboBox,
    QLabel, QToolBar, QMenu, QSystemTrayIcon, QMenuBar,
    QMessageBox, QLineEdit, QFileDialog,
)

from core import Aria2RPC, BackendWorker, DataStore, LocalServer
from core.data_store import Queue
from core.aria2_manager import Aria2Manager
from ui.delegates import ProgressDelegate
from ui.dialogs import AddDownloadDialog, SettingsDialog, AddTorrentDialog, TorrentFileSelectionDialog
from ui.table_model import DownloadTableModel
from utils.helpers import format_speed, get_icon
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
        self.tray = QSystemTrayIcon(parent)
        self.tray.activated.connect(self._on_tray_activated)

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


class SearchProxyModel(QSortFilterProxyModel):
    """Proxy model for filtering downloads by name."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._filter_text = ""

    def set_filter_text(self, text: str) -> None:
        self._filter_text = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        if not self._filter_text:
            return True

        model = self.sourceModel()
        name_index = model.index(source_row, 0)  # Name column
        name = model.data(name_index, Qt.ItemDataRole.DisplayRole)
        if name and self._filter_text in str(name).lower():
            return True
        return False


class MainWindow(QMainWindow):
    """Main application window - UI coordinator."""

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("FelfelDM")
        self.setMinimumSize(1050, 680)

        # Core components
        self.store = DataStore()
        self._ensure_default_queue()

        self.aria2_manager = Aria2Manager()
        self.aria2_manager.start()

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

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter downloads by name...")
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        search_layout.addWidget(self.search_edit)
        content_layout.addLayout(search_layout)

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

        content_layout.addWidget(self.table)

        # Status bar
        self.status_label = QLabel("Ready")
        content_layout.addWidget(self.status_label)

        main_layout.addWidget(content)

        self._update_queue_ui()

    def _build_toolbar(self, parent_layout) -> None:
        toolbar = QToolBar()
        toolbar.setMovable(False)

        # Add download button
        add_action = QAction(get_icon("list-add"), "Add Download", self)
        add_action.triggered.connect(self._show_add_dialog)
        toolbar.addAction(add_action)

        # Add torrent button
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

        remove_action = QAction("Remove", self)
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
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Add Queue", "Queue name:")
        if ok and name:
            self.queue_controller.add_queue(name)

    def _toggle_current_queue(self) -> None:
        idx = self.queue_combo.currentIndex()
        self.queue_controller.toggle_pause(idx)

    def _delete_current_queue(self) -> None:
        idx = self.queue_combo.currentIndex()
        if idx >= 0:
            self.queue_controller.delete_queue(idx)

    def _show_add_dialog(self) -> None:
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

    def _show_add_torrent_dialog(self) -> None:
        dialog = AddTorrentDialog(
            self.queue_controller.get_queues(),
            self.store,
            self.queue_controller.current_index,
            self
        )
        if dialog.exec():
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
                    # Show file selection dialog
                    file_dialog = TorrentFileSelectionDialog(torrent_info, torrent_path, self)
                    if file_dialog.exec():
                        selected_files = file_dialog.get_selected_files()
                        if not selected_files:
                            QMessageBox.warning(self, "No Files Selected", "Please select at least one file to download.")
                            return
                        # Add torrent with selected files
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
        for idx in selection:
            source_idx = self.proxy_model.mapToSource(idx)
            gid = self.table_model.get_gid(source_idx.row())
            if gid:
                self.download_controller.remove(gid)
        self.table_model.refresh()

    def _show_settings(self) -> None:
        dialog = SettingsDialog(self.store, self)
        if dialog.exec():
            self._apply_theme_from_settings()

    def _apply_theme_from_settings(self) -> None:
        theme_setting = self.store.settings.get("theme", "system")
        if theme_setting == "system":
            is_dark = detect_theme()
        elif theme_setting == "dark":
            is_dark = True
        else:  # "light"
            is_dark = False
        apply_theme(self, is_dark)

    def _on_aria2_error(self, msg: str) -> None:
        logger.error("aria2 error: %s", msg)
        self.status_label.setText(f"Error: {msg}")

    def _on_stats_updated(self, stats: dict) -> None:
        self.table_model.refresh()
        if "global" in stats:
            gs = stats["global"]
            speed = format_speed(gs.get("downloadSpeed", 0))
            self.status_label.setText(f"Download Speed: {speed}")

    def _on_connection_changed(self, connected: bool) -> None:
        if connected:
            self.status_label.setText("Connected to aria2")
        else:
            self.status_label.setText("Disconnected from aria2")

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
        if dialog.exec():
            urls = dialog.get_urls()
            queue_idx = dialog.get_queue_index()
            options = dialog.get_options()
            if urls:
                self.download_controller.add_urls(urls, queue_idx, options)

    def _update_ui(self) -> None:
        pass

    def _update_tray_icon(self) -> None:
        from PyQt6.QtGui import QIcon
        self.tray_controller.set_icon(QIcon.fromTheme("download"))

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
        if hasattr(self, 'worker'):
            self.worker.stop()
        if hasattr(self, 'local_server'):
            self.local_server.stop()
        self.aria2_manager.stop()
        from PyQt6.QtWidgets import QApplication
        QApplication.quit()
