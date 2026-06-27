# Requires: PyQt6>=6.4.0

"""
Main application window with enhanced UI: search, progress, context menu, auto-update.
"""

import os
import logging
from typing import Optional, Dict, Any, List, cast

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QToolBar, QTableView,
    QAbstractItemView, QMenu, QMessageBox, QDialog, QLabel,
    QStatusBar, QHeaderView, QLineEdit, QHBoxLayout, QPushButton,
)
from PyQt6.QtCore import Qt, QSize, QModelIndex, pyqtSlot, QSortFilterProxyModel, pyqtSignal
from PyQt6.QtGui import QAction, QIcon

from core.data_store import DataStore
from core.aria2_rpc import Aria2RPC
from core.aria2_manager import Aria2Manager
from core.worker import BackendWorker
from core.session_manager import SessionManager
from core.updater import Updater
from ui.dialogs import (
    AddDownloadDialog, SingleDownloadDialog, QuickDownloadDialog,
    SettingsDialog, DownloadProgressDialog, TorrentDialog,
)
from ui.table_model import DownloadTableModel
from ui.delegates import ProgressDelegate, StatusDelegate
from ui.icons import get_icon
from utils.helpers import format_speed, check_disk_space

logger: logging.Logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main window for FelfelDM download manager."""

    update_available = pyqtSignal(str)  # Signal for update availability

    def __init__(self, aria2_manager: Aria2Manager, store: DataStore, session_mgr: SessionManager) -> None:
        super().__init__()
        self.aria2_manager = aria2_manager
        self.store = store
        self.session_mgr = session_mgr
        self.setWindowTitle("FelfelDM")
        self.setMinimumSize(1000, 600)

        self.aria2 = Aria2RPC(
            self.store.settings["aria2_host"],
            self.store.settings["aria2_port"],
            self.store.get_aria2_secret(),
            timeout=self.store.settings.get("aria2_timeout", 5),
            fingerprint=self.aria2_manager.get_certificate_fingerprint(),
            cert_file=self.aria2_manager.get_certificate_path(),
        )

        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()
        self._setup_connections()

        self.worker: Optional[BackendWorker] = None
        self._start_backend()

        self.progress_dialogs: Dict[str, DownloadProgressDialog] = {}

        # Restore session on startup
        self._restore_session()

        # Auto-update check (daily)
        self.updater = Updater("1.0.0")  # version should be defined centrally
        self._check_updates()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # Search bar
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter by filename, URL, or GID...")
        self.search_edit.textChanged.connect(self._filter_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_edit)
        main_layout.addLayout(search_layout)

        toolbar = QToolBar()
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        add_action = QAction(get_icon('list-add'), "Add Downloads", self)
        add_action.triggered.connect(self._add_downloads)
        toolbar.addAction(add_action)

        single_action = QAction(get_icon('document-new'), "Single Download", self)
        single_action.triggered.connect(self._single_download)
        toolbar.addAction(single_action)

        torrent_action = QAction(get_icon('torrent'), "Add Torrent", self)
        torrent_action.triggered.connect(self._add_torrent)
        toolbar.addAction(torrent_action)

        quick_action = QAction(get_icon('insert-link'), "Quick Download", self)
        quick_action.triggered.connect(self._quick_download)
        toolbar.addAction(quick_action)

        toolbar.addSeparator()

        pause_all = QAction(get_icon('media-playback-pause'), "Pause All", self)
        pause_all.triggered.connect(self._pause_all)
        toolbar.addAction(pause_all)

        resume_all = QAction(get_icon('media-playback-start'), "Resume All", self)
        resume_all.triggered.connect(self._resume_all)
        toolbar.addAction(resume_all)

        toolbar.addSeparator()

        settings_action = QAction(get_icon('preferences-system'), "Settings", self)
        settings_action.triggered.connect(self._open_settings)
        toolbar.addAction(settings_action)

        self.table = QTableView()
        self.model = DownloadTableModel(self.store)
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setFilterKeyColumn(-1)  # all columns
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.table.setModel(self.proxy_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)

        self.table.setItemDelegateForColumn(3, ProgressDelegate(self.table))
        self.table.setItemDelegateForColumn(4, StatusDelegate(self.table))

        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 200)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 80)
        self.table.setColumnWidth(6, 80)
        self.table.setColumnWidth(7, 80)
        self.table.setColumnWidth(8, 100)

        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)

        main_layout.addWidget(self.table)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        self.table.doubleClicked.connect(self._show_progress_dialog)

    def _setup_menu(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        download_menu = menubar.addMenu("Download")
        add_action = QAction("Add Downloads", self)
        add_action.triggered.connect(self._add_downloads)
        download_menu.addAction(add_action)
        single_action = QAction("Single Download", self)
        single_action.triggered.connect(self._single_download)
        download_menu.addAction(single_action)
        torrent_action = QAction("Add Torrent", self)
        torrent_action.triggered.connect(self._add_torrent)
        download_menu.addAction(torrent_action)
        quick_action = QAction("Quick Download", self)
        quick_action.triggered.connect(self._quick_download)
        download_menu.addAction(quick_action)
        download_menu.addSeparator()
        pause_all = QAction("Pause All", self)
        pause_all.triggered.connect(self._pause_all)
        download_menu.addAction(pause_all)
        resume_all = QAction("Resume All", self)
        resume_all.triggered.connect(self._resume_all)
        download_menu.addAction(resume_all)

        view_menu = menubar.addMenu("View")
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self._refresh)
        view_menu.addAction(refresh_action)

        settings_menu = menubar.addMenu("Settings")
        settings_action = QAction("Preferences", self)
        settings_action.triggered.connect(self._open_settings)
        settings_menu.addAction(settings_action)

        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        update_action = QAction("Check for Updates", self)
        update_action.triggered.connect(self._check_updates_manual)
        help_menu.addAction(update_action)

    def _setup_statusbar(self) -> None:
        self.statusbar = self.statusBar()

        self.status_lbl = QLabel("● Connected")
        self.status_lbl.setStyleSheet("color: #2ecc71; font-weight: bold;")
        self.statusbar.addWidget(self.status_lbl)

        self.statusbar.addPermanentWidget(QLabel("   "))

        self.download_count_lbl = QLabel("0 active")
        self.statusbar.addPermanentWidget(self.download_count_lbl)

        self.speed_lbl = QLabel("0 B/s")
        self.statusbar.addPermanentWidget(self.speed_lbl)

    def _setup_connections(self) -> None:
        self.aria2.error_occurred.connect(self._on_aria2_error)
        self.aria2.connection_changed.connect(self._on_connection_changed)

    def _start_backend(self) -> None:
        if self.worker:
            self.worker.stop()
            self.worker.wait()
        self.worker = BackendWorker(self.aria2, self.store, self.session_mgr, self.aria2_manager)
        self.worker.stats_updated.connect(self._on_stats_updated)
        self.worker.connection_changed.connect(self._on_connection_changed)
        self.worker.start()

    @pyqtSlot(dict)
    def _on_stats_updated(self, data: Dict[str, Any]) -> None:
        if not data.get("connected", False):
            return
        stat = data.get("stat", {})
        active = data.get("active", [])
        waiting = data.get("waiting", [])
        stopped = data.get("stopped", [])

        active_count = len(active)
        self.download_count_lbl.setText(f"{active_count} active")

        speed = int(stat.get("downloadSpeed", 0))
        self.speed_lbl.setText(format_speed(speed))

        self.model.update_downloads(active, waiting, stopped)

        all_downloads = {dl.get("gid"): dl for dl in active + waiting + stopped}
        for gid, dlg in list(self.progress_dialogs.items()):
            if gid in all_downloads:
                dlg.update_status(all_downloads[gid])
            else:
                dlg.update_status({"status": "removed"})

    @pyqtSlot(str)
    def _on_aria2_error(self, msg: str) -> None:
        display_msg = msg[:50] + "..." if len(msg) > 50 else msg
        self.status_lbl.setText(f"⚠ {display_msg}")
        self.status_lbl.setStyleSheet("color: #e74c3c; font-weight: bold;")
        if any(k in msg for k in ["اتصال", "aria2 را اجرا", "احراز هویت", "فضای کافی"]):
            QMessageBox.critical(self, "Error", msg)

    @pyqtSlot(bool)
    def _on_connection_changed(self, connected: bool) -> None:
        if connected:
            self.status_lbl.setText("● Connected")
            self.status_lbl.setStyleSheet("color: #2ecc71; font-weight: bold;")
        else:
            self.status_lbl.setText("● Disconnected")
            self.status_lbl.setStyleSheet("color: #e74c3c; font-weight: bold;")

    def _filter_table(self, text: str) -> None:
        # Use filterRegularExpression instead of deprecated setFilterFixedString
        self.proxy_model.setFilterRegularExpression(text)

    def _add_downloads(self) -> None:
        queues = [q for q in self.store.queues if q.name != "__direct__"]
        dlg = AddDownloadDialog(queues, self.store, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data:
                self._perform_add_urls(data)

    def _single_download(self) -> None:
        queues = [q for q in self.store.queues if q.name != "__direct__"]
        dlg = SingleDownloadDialog(queues, self.store, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data:
                self._perform_add_urls(data, single=True)

    def _quick_download(self) -> None:
        queues = [q for q in self.store.queues if q.name != "__direct__"]
        dlg = QuickDownloadDialog(queues, self.store, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data:
                self._perform_add_urls(data)

    def _add_torrent(self) -> None:
        queues = [q for q in self.store.queues if q.name != "__direct__"]
        dlg = TorrentDialog(queues, self.store, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            data = dlg.get_data()
            if data:
                self._perform_add_torrent(data)

    def _perform_add_urls(self, data: Dict[str, Any], single: bool = False) -> None:
        urls = data.get("urls", [])
        if not urls:
            return
        start_immediately = data.get("start_immediately", False)
        path = data["path"]
        if not check_disk_space(path, 0):
            QMessageBox.warning(self, "Disk Space", "Not enough free disk space.")
            return
        opts = {
            "dir": path,
            "max-connection-per-server": str(data.get("connections", 16)),
            "pause": not start_immediately,
            "min-split-size": "1M",
            "split": str(data.get("connections", 16)),
        }
        cookies = self.store.get_cookies()
        headers = self.store.get_headers()
        if cookies:
            opts["cookie"] = cookies
        if headers:
            opts["header"] = [h.strip() for h in headers.split('\n') if h.strip()]
        queue_name = "Default"
        if "queue" in data:
            q_idx = data["queue"]
            if q_idx < len(self.store.queues):
                queue_name = self.store.queues[q_idx].name
        if single:
            gid = self.aria2.add_url(urls[0], opts)
            if gid:
                self.store.add_gid_to_queue(queue_name, gid)
                if start_immediately:
                    self.aria2.resume(gid)
        else:
            gids = self.aria2.add_urls(urls, opts)
            for gid in gids:
                if gid:  # Check for None
                    self.store.add_gid_to_queue(queue_name, gid)
                    if start_immediately:
                        self.aria2.resume(gid)

    def _perform_add_torrent(self, data: Dict[str, Any]) -> None:
        torrent_file = data.get("torrent_file")
        magnet = data.get("magnet")
        start_immediately = data.get("start_immediately", False)
        path = data["path"]
        if not check_disk_space(path, 0):
            QMessageBox.warning(self, "Disk Space", "Not enough free disk space.")
            return
        opts = {
            "dir": path,
            "pause": not start_immediately,
        }
        if torrent_file:
            gid = self.aria2.add_torrent(torrent_file, opts)
        elif magnet:
            gid = self.aria2.add_magnet(magnet, opts)
        else:
            QMessageBox.warning(self, "Error", "No torrent source provided.")
            return
        if gid:
            queue_name = "Default"
            if "queue" in data:
                q_idx = data["queue"]
                if q_idx < len(self.store.queues):
                    queue_name = self.store.queues[q_idx].name
            self.store.add_gid_to_queue(queue_name, gid)
            if start_immediately:
                self.aria2.resume(gid)

    def _pause_all(self) -> None:
        active = self.aria2.tell_active()
        for dl in active:
            gid = dl.get("gid")
            if gid:
                self.aria2.pause(gid)

    def _resume_all(self) -> None:
        waiting = self.aria2.tell_waiting()
        for dl in waiting:
            gid = dl.get("gid")
            if gid:
                self.aria2.resume(gid)

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.store, self.aria2, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            dlg.save_settings()
            # Restart backend to apply new settings
            self._start_backend()

    def _refresh(self) -> None:
        self.model.refresh()

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About FelfelDM",
            "FelfelDM - Download Manager\n\n"
            "Built with PyQt6 and aria2.\n"
            "Licensed under MIT License.\n"
            "Version 1.0.0"
        )

    def _show_context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        source_index = self.proxy_model.mapToSource(index)
        gid = self.model.data(self.model.index(source_index.row(), 0), Qt.ItemDataRole.UserRole)
        if not gid:
            return
        menu = QMenu(self)
        resume_action = QAction("Resume", self)
        resume_action.triggered.connect(lambda: self.aria2.resume(gid))
        menu.addAction(resume_action)
        pause_action = QAction("Pause", self)
        pause_action.triggered.connect(lambda: self.aria2.pause(gid))
        menu.addAction(pause_action)
        menu.addSeparator()
        remove_action = QAction("Remove (keep files)", self)
        remove_action.triggered.connect(lambda: self.aria2.remove(gid, delete_files=False))
        menu.addAction(remove_action)
        remove_files_action = QAction("Remove and delete files", self)
        remove_files_action.triggered.connect(lambda: self.aria2.remove(gid, delete_files=True))
        menu.addAction(remove_files_action)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _show_progress_dialog(self, index: QModelIndex) -> None:
        source_index = self.proxy_model.mapToSource(index)
        gid = self.model.data(self.model.index(source_index.row(), 0), Qt.ItemDataRole.UserRole)
        if not gid:
            return
        url = self.model.data(self.model.index(source_index.row(), 1), Qt.ItemDataRole.DisplayRole) or ""
        if gid in self.progress_dialogs:
            dlg = self.progress_dialogs[gid]
            dlg.raise_()
            dlg.activateWindow()
            return
        dlg = DownloadProgressDialog(gid, url, self)
        dlg.pause_requested.connect(self._on_progress_pause)
        dlg.cancel_requested.connect(self._on_progress_cancel)
        dlg.finished.connect(lambda: self._on_progress_closed(gid))
        self.progress_dialogs[gid] = dlg
        dlg.show()

    @pyqtSlot(str, bool)
    def _on_progress_pause(self, gid: str, pause: bool) -> None:
        if pause:
            self.aria2.pause(gid)
        else:
            self.aria2.resume(gid)

    @pyqtSlot(str)
    def _on_progress_cancel(self, gid: str) -> None:
        self.aria2.remove(gid, delete_files=True)

    @pyqtSlot(str)
    def _on_progress_closed(self, gid: str) -> None:
        if gid in self.progress_dialogs:
            del self.progress_dialogs[gid]

    def _restore_session(self) -> None:
        gids = self.session_mgr.load_session()
        if gids:
            logger.info("Restoring session with %d downloads", len(gids))
            for gid in gids:
                # Check if GID exists in aria2 before resuming
                status = self.aria2.tell_status(gid, ["gid"])
                if status and status.get("gid"):
                    self.aria2.resume(gid)
                else:
                    logger.warning("GID %s not found in aria2, skipping", gid)

    def _check_updates(self) -> None:
        """Check for updates silently (e.g., on startup)."""
        new_version = self.updater.check_for_updates()
        if new_version:
            self.update_available.emit(new_version)
            reply = QMessageBox.question(
                self,
                "Update Available",
                f"Version {new_version} is available. Do you want to download and install it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # For demo, we just show a message
                QMessageBox.information(self, "Update", "Update download would start. (Not implemented)")

    def _check_updates_manual(self) -> None:
        """Check for updates on user request."""
        new_version = self.updater.check_for_updates()
        if new_version:
            QMessageBox.information(self, "Update Available", f"Version {new_version} is available.")
        else:
            QMessageBox.information(self, "No Updates", "You are running the latest version.")

    def closeEvent(self, event) -> None:
        # Save active GIDs
        active = self.aria2.tell_active()
        active_gids = [dl.get("gid") for dl in active if dl.get("gid")]
        self.session_mgr.save_session(active_gids)

        if self.worker:
            self.worker.stop()
            self.worker.wait()
        self.aria2.close()
        self.aria2_manager.stop()
        for dlg in list(self.progress_dialogs.values()):
            dlg.close()
        event.accept()
