# ui/main_window.py
import logging
import os
import subprocess
import time
from typing import List, Optional

from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PyQt6.QtWidgets import *

from core import Aria2RPC, BackendWorker, DataStore
from core.data_store import Queue
from core.local_server import LocalServer
from ui.delegates import ProgressDelegate
from ui.dialogs import AddDownloadDialog, SettingsDialog
from ui.table_model import DownloadTableModel
from utils.helpers import format_speed, get_category, get_icon

logger = logging.getLogger(__name__)


class DownloadController:
    """Manages download operations and aria2 communication."""

    def __init__(self, aria2: Aria2RPC, store: DataStore):
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
        q.downloads.extend(added_gids)
        self.store.save()
        return added_gids

    def start(self, gid: str) -> None:
        self.aria2.resume(gid)

    def pause(self, gid: str) -> None:
        self.aria2.pause(gid)

    def remove(self, gid: str) -> None:
        self.aria2.remove(gid)
        self._cleared_gids.add(gid)

    def is_cleared(self, gid: str) -> bool:
        return gid in self._cleared_gids


class QueueManager:
    """Manages queue operations."""

    def __init__(self, store: DataStore):
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

    def toggle_pause(self, index: int) -> None:
        if 0 <= index < len(self.store.queues):
            q = self.store.queues[index]
            q.paused = not q.paused
            self.store.save()

    def delete_queue(self, index: int) -> bool:
        if 0 <= index < len(self.store.queues):
            q = self.store.queues[index]
            if q.name == "Default":
                return False
            del self.store.queues[index]
            self.store.save()
            return True
        return False

    def add_queue(self, name: str) -> bool:
        if any(q.name == name for q in self.store.queues):
            return False
        self.store.queues.append(Queue(name, paused=True))
        self.store.save()
        return True


class MainWindow(QMainWindow):
    """Main application window - now acts as UI coordinator."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FelfelDM")
        self.setMinimumSize(1050, 680)

        # Core components
        self.store = DataStore()
        self._ensure_default_queue()

        self.aria2 = Aria2RPC(
            self.store.settings["aria2_host"],
            self.store.settings["aria2_port"],
            self.store.settings["aria2_secret"],
            verify_ssl=True
        )
        self.aria2.on_error = self._on_aria2_error

        self.download_controller = DownloadController(self.aria2, self.store)
        self.queue_manager = QueueManager(self.store)

        # Build UI
        self._build_ui()
        self._build_tray()

        # Start services
        self._start_aria2_if_needed()
        self._apply_global_speed_limit()
        self._start_backend()

        # Start local server in a separate thread
        self.local_server = LocalServer(callback=self._add_downloads_from_extension)
        self.local_server.start(8765)

    def _ensure_default_queue(self) -> None:
        if not any(q.name == "Default" for q in self.store.queues):
            self.store.queues.insert(0, Queue("Default", paused=True))
            self.store.save()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #3d4045;
                width: 4px;
            }
            QSplitter::handle:hover {
                background-color: #4a4d53;
            }
        """)

        sidebar = self._build_sidebar()
        splitter.addWidget(sidebar)

        content = self._build_content()
        splitter.addWidget(content)

        splitter.setSizes([220, 800])
        root.addWidget(splitter)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(180)
        sidebar.setMaximumWidth(350)
        sidebar.setStyleSheet("""
            QWidget#sidebar {
                background-color: #2d2d30;
                border-right: 1px solid #1e1e20;
            }
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(10, 12, 10, 12)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Queues"))
        layout.addSpacing(4)

        self.queue_list = QListWidget()
        self.queue_list.currentRowChanged.connect(self._on_queue_changed)
        layout.addWidget(self.queue_list)

        btn_layout = QHBoxLayout()
        self.start_queue_btn = QPushButton(get_icon('media-playback-start'), "Start")
        self.start_queue_btn.clicked.connect(self._toggle_queue_pause)
        btn_layout.addWidget(self.start_queue_btn)

        self.delete_queue_btn = QPushButton(get_icon('edit-delete'), "Delete")
        self.delete_queue_btn.clicked.connect(self._delete_current_queue)
        btn_layout.addWidget(self.delete_queue_btn)

        layout.addLayout(btn_layout)

        add_queue_btn = QPushButton(get_icon('list-add'), "Add Queue")
        add_queue_btn.clicked.connect(self._add_queue)
        layout.addWidget(add_queue_btn)

        layout.addStretch()

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #95a5a6; font-size: 10px;")
        layout.addWidget(self.status_label)

        return sidebar

    def _build_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        toolbar = self._build_toolbar()
        layout.addWidget(toolbar)

        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        self.model = DownloadTableModel()
        self.table.setModel(self.model)

        self.progress_delegate = ProgressDelegate()
        self.table.setItemDelegateForColumn(2, self.progress_delegate)

        layout.addWidget(self.table)

        self.status_bar = QStatusBar()
        self.status_bar.setStyleSheet("QStatusBar { background-color: #2d2d30; color: #efefef; }")
        self.download_speed_label = QLabel("⬇ 0 B/s")
        self.upload_speed_label = QLabel("⬆ 0 B/s")
        self.download_count_label = QLabel("Active: 0")
        self.status_bar.addWidget(self.download_speed_label)
        self.status_bar.addWidget(self.upload_speed_label)
        self.status_bar.addWidget(self.download_count_label)
        self.status_bar.addPermanentWidget(QLabel("FelfelDM"))
        layout.addWidget(self.status_bar)

        return content

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setStyleSheet("""
            QWidget {
                background-color: #2d2d30;
                border-bottom: 1px solid #1e1e20;
            }
            QPushButton {
                background-color: transparent;
                color: #efefef;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3d4045;
            }
        """)
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        add_btn = QPushButton(get_icon('list-add'), "Add")
        add_btn.clicked.connect(self._add_downloads)
        layout.addWidget(add_btn)

        start_btn = QPushButton(get_icon('media-playback-start'), "Start")
        start_btn.clicked.connect(self._start_selected)
        layout.addWidget(start_btn)

        pause_btn = QPushButton(get_icon('media-playback-pause'), "Pause")
        pause_btn.clicked.connect(self._pause_selected)
        layout.addWidget(pause_btn)

        remove_btn = QPushButton(get_icon('edit-delete'), "Remove")
        remove_btn.clicked.connect(self._remove_selected)
        layout.addWidget(remove_btn)

        layout.addStretch()

        settings_btn = QPushButton(get_icon('preferences-system'), "Settings")
        settings_btn.clicked.connect(self._show_settings)
        layout.addWidget(settings_btn)

        return toolbar

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(self.windowIcon())
        self.tray.setToolTip("FelfelDM")

        tray_menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show)
        tray_menu.addAction(show_action)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_application)
        tray_menu.addAction(quit_action)

        self.tray.setContextMenu(tray_menu)
        self.tray.show()

    def _start_aria2_if_needed(self) -> None:
        if self.aria2.is_connected():
            return

        try:
            import shutil
            aria2_path = shutil.which("aria2c")
            if aria2_path:
                cmd = [
                    aria2_path,
                    "--enable-rpc",
                    f"--rpc-listen-port={self.store.settings['aria2_port']}",
                    "--max-concurrent-downloads=5",
                    "--max-connection-per-server=16",
                    "--split=16",
                    "--min-split-size=1M",
                    "--console-log-level=error"
                ]
                secret = self.store.get_secret()
                if secret:
                    cmd.append(f"--rpc-secret={secret}")
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(1)
        except Exception as e:
            logger.error(f"Failed to start aria2: {e}")

    def _apply_global_speed_limit(self) -> None:
        limit = self.store.settings.get("speed_limit", 0)
        if limit > 0:
            self.aria2.change_global_option({"max-download-limit": str(limit)})

    def _start_backend(self) -> None:
        self.worker = BackendWorker(self.aria2, self.store)
        self.worker.stats_updated.connect(self._on_stats_updated)
        self.worker.start()

    def _on_stats_updated(self, data: dict) -> None:
        if not data.get("connected", False):
            self.status_label.setText("⚠ aria2 disconnected")
            return

        stat = data.get("stat", {})
        if not isinstance(stat, dict):
            stat = {}

        active = [item for item in data.get("active", []) if isinstance(item, dict)]
        waiting = [item for item in data.get("waiting", []) if isinstance(item, dict)]
        stopped = [item for item in data.get("stopped", []) if isinstance(item, dict)]

        dl_speed = int(stat.get("downloadSpeed", 0))
        ul_speed = int(stat.get("uploadSpeed", 0))
        self.download_speed_label.setText(f"⬇ {format_speed(dl_speed)}")
        self.upload_speed_label.setText(f"⬆ {format_speed(ul_speed)}")
        self.download_count_label.setText(f"Active: {len(active)}")

        self._update_queue_list()

        all_downloads = {}
        for d in active + waiting + stopped:
            gid = d.get("gid")
            if gid:
                all_downloads[gid] = d

        current_queue = self.queue_manager.get_current_queue()
        queue_gids = set(current_queue.downloads) if current_queue else set()

        rows = []
        for gid, d in all_downloads.items():
            if self.download_controller.is_cleared(gid):
                continue
            if queue_gids and gid not in queue_gids:
                continue
            files = d.get("files", [])
            name = files[0].get("path", "unknown").split("/")[-1] if files else "unknown"
            rows.append({
                "gid": gid,
                "name": name,
                "totalLength": d.get("totalLength", 0),
                "completedLength": d.get("completedLength", 0),
                "downloadSpeed": d.get("downloadSpeed", 0),
                "status": d.get("status", ""),
                "category": get_category(name),
                "errorMessage": d.get("errorMessage", ""),
            })

        self.model.update_rows(rows)

    def _update_queue_list(self) -> None:
        current = self.queue_list.currentRow()
        self.queue_list.clear()
        for q in self.store.queues:
            status = "⏸" if q.paused else "▶"
            self.queue_list.addItem(f"{status} {q.name}")
        if current >= 0 and current < self.queue_list.count():
            self.queue_list.setCurrentRow(current)
        elif self.queue_list.count() > 0:
            self.queue_list.setCurrentRow(0)

    def _on_queue_changed(self, index: int) -> None:
        self.queue_manager.set_current_index(index)

    def _toggle_queue_pause(self) -> None:
        self.queue_manager.toggle_pause(self.queue_manager.current_index)
        self._update_queue_list()

    def _delete_current_queue(self) -> None:
        index = self.queue_manager.current_index
        if index < len(self.store.queues):
            q = self.store.queues[index]
            if q.name == "Default":
                QMessageBox.warning(self, "Cannot Delete", "Cannot delete the Default queue.")
                return
            if QMessageBox.question(self, "Delete Queue",
                                   f"Delete queue '{q.name}' and all its downloads?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                if self.queue_manager.delete_queue(index):
                    self._update_queue_list()

    def _add_queue(self) -> None:
        name, ok = QInputDialog.getText(self, "Add Queue", "Enter queue name:")
        if ok and name.strip():
            if self.queue_manager.add_queue(name.strip()):
                self._update_queue_list()
            else:
                QMessageBox.warning(self, "Duplicate", "A queue with this name already exists.")

    def _add_downloads(self) -> None:
        dialog = AddDownloadDialog(self.store.queues, self.queue_manager.current_index, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            urls = data.get("urls", [])
            if not urls:
                return
            queue_idx = data.get("queue", 0)
            options = {
                "dir": data.get("path", ""),
                "max-connection-per-server": str(data.get("connections", 8)),
                "split": str(data.get("connections", 8)),
            }
            self.download_controller.add_urls(urls, queue_idx, options)

    def _add_downloads_from_extension(self, urls: List[str]) -> None:
        if not urls:
            return
        queue_idx = self.queue_manager.current_index
        options = {
            "dir": "",
            "max-connection-per-server": str(self.store.settings.get("connections", 8)),
        }
        added = self.download_controller.add_urls(urls, queue_idx, options)
        if added:
            self.status_label.setText(f"Added {len(added)} download(s) from extension")

    def _start_selected(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        for idx in selected:
            row = idx.row()
            if row < len(self.model.rows):
                gid = self.model.data(idx, DownloadTableModel.GID_ROLE)
                if gid:
                    self.download_controller.start(gid)

    def _pause_selected(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        for idx in selected:
            row = idx.row()
            if row < len(self.model.rows):
                gid = self.model.data(idx, DownloadTableModel.GID_ROLE)
                if gid:
                    self.download_controller.pause(gid)

    def _remove_selected(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return
        if QMessageBox.question(self, "Remove Downloads",
                               f"Remove {len(selected)} download(s)?",
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            for idx in selected:
                row = idx.row()
                if row < len(self.model.rows):
                    gid = self.model.data(idx, DownloadTableModel.GID_ROLE)
                    if gid:
                        self.download_controller.remove(gid)

    def _show_settings(self) -> None:
        dialog = SettingsDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.aria2 = Aria2RPC(
                self.store.settings["aria2_host"],
                self.store.settings["aria2_port"],
                self.store.settings["aria2_secret"],
                verify_ssl=True
            )
            self.aria2.on_error = self._on_aria2_error
            self.download_controller = DownloadController(self.aria2, self.store)
            self._apply_global_speed_limit()

    def _on_aria2_error(self, msg: str) -> None:
        self.status_label.setText(f"⚠ {msg}")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Delete:
            self._remove_selected()
        elif event.key() == Qt.Key.Key_N and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._add_downloads()
        elif event.key() == Qt.Key.Key_Q and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._quit_application()
        else:
            super().keyPressEvent(event)

    def _quit_application(self) -> None:
        self.local_server.stop()
        if hasattr(self, 'worker'):
            self.worker.stop()
        QApplication.quit()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            self._quit_application()
            event.accept()
