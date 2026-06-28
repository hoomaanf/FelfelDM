# Requires: PyQt6>=6.4.0
"""Main window with search, progress, context menu, and auto-update."""

import logging
from typing import Optional, Dict, Any

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QToolBar, QTableView,
    QAbstractItemView, QMenu, QMessageBox, QDialog, QLabel,
    QStatusBar, QHeaderView, QLineEdit, QHBoxLayout,
)
from PyQt6.QtCore import Qt, QSize, QSortFilterProxyModel, pyqtSignal
from PyQt6.QtGui import QAction

from core.data_store import DataStore
from core.aria2_rpc import Aria2RPC
from core.aria2_manager import Aria2Manager
from core.worker import BackendWorker
from core.session_manager import SessionManager
from core.updater import Updater
from ui.dialogs import (
    AddDownloadDialog, SingleDownloadDialog, QuickDownloadDialog,
    SettingsDialog, DownloadProgressDialog,
)
from ui.table_model import DownloadTableModel
from ui.delegates import ProgressDelegate, StatusDelegate
from ui.icons import get_icon
from utils.helpers import format_speed

from main import __version__

logger: logging.Logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    update_available = pyqtSignal(str)

    def __init__(self, aria2_manager: Aria2Manager, store: DataStore, session_mgr: SessionManager) -> None:
        super().__init__()
        self.aria2_manager = aria2_manager
        self.store = store
        self.session_mgr = session_mgr

        self.setWindowTitle(f"FelfelDM v{__version__}")
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

        self._restore_session()
        self.updater = Updater(__version__)
        self._check_updates()

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

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

        add_action = QAction(get_icon("list-add"), "Add Downloads", self)
        add_action.triggered.connect(self._add_downloads)
        toolbar.addAction(add_action)

        single_action = QAction(get_icon("document-new"), "Single Download", self)
        single_action.triggered.connect(self._single_download)
        toolbar.addAction(single_action)

        quick_action = QAction(get_icon("insert-link"), "Quick Download", self)
        quick_action.triggered.connect(self._quick_download)
        toolbar.addAction(quick_action)

        toolbar.addSeparator()

        pause_action = QAction(get_icon("media-playback-pause"), "Pause All", self)
        pause_action.triggered.connect(self._pause_all)
        toolbar.addAction(pause_action)

        resume_action = QAction(get_icon("media-playback-start"), "Resume All", self)
        resume_action.triggered.connect(self._resume_all)
        toolbar.addAction(resume_action)

        toolbar.addSeparator()

        settings_action = QAction(get_icon("preferences-system"), "Settings", self)
        settings_action.triggered.connect(self._show_settings)
        toolbar.addAction(settings_action)

        self.table_view = QTableView()
        self.table_model = DownloadTableModel(self.store, self.aria2)
        self.proxy_model = QSortFilterProxyModel()
        self.proxy_model.setSourceModel(self.table_model)
        self.proxy_model.setFilterKeyColumn(-1)
        self.proxy_model.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        self.table_view.setModel(self.proxy_model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSortingEnabled(True)
        self.table_view.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        self.table_view.setItemDelegateForColumn(3, ProgressDelegate(self.table_view))
        self.table_view.setItemDelegateForColumn(4, StatusDelegate(self.table_view))

        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self._show_context_menu)

        main_layout.addWidget(self.table_view)

    def _setup_menu(self) -> None:
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        add_action = file_menu.addAction("Add Downloads...")
        add_action.triggered.connect(self._add_downloads)
        file_menu.addSeparator()
        file_menu.addAction("Exit").triggered.connect(self.close)

        download_menu = menubar.addMenu("Download")
        download_menu.addAction("Pause All").triggered.connect(self._pause_all)
        download_menu.addAction("Resume All").triggered.connect(self._resume_all)

        tools_menu = menubar.addMenu("Tools")
        tools_menu.addAction("Settings...").triggered.connect(self._show_settings)
        tools_menu.addSeparator()
        tools_menu.addAction("Check for Updates...").triggered.connect(self._check_updates)

        help_menu = menubar.addMenu("Help")
        help_menu.addAction("About").triggered.connect(self._show_about)

    def _setup_statusbar(self) -> None:
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("Ready")
        self.status_bar.addWidget(self.status_label)
        self.speed_label = QLabel("Speed: 0 B/s")
        self.status_bar.addPermanentWidget(self.speed_label)
        self.download_count_label = QLabel("Downloads: 0")
        self.status_bar.addPermanentWidget(self.download_count_label)

    def _setup_connections(self) -> None:
        self.table_model.dataChanged.connect(lambda: None)

    def _start_backend(self) -> None:
        self.worker = BackendWorker(self.aria2, self.store, self.session_mgr, self.aria2_manager)
        self.worker.stats_updated.connect(self._on_stats_updated)
        self.worker.connection_changed.connect(self._on_connection_changed)
        self.worker.start()

    def _restore_session(self) -> None:
        gids = self.session_mgr.load_session()
        if gids:
            logger.info("Restoring %d downloads", len(gids))
            self._refresh_table()

    def _check_updates(self) -> None:
        import threading

        def check_thread() -> None:
            new_version = self.updater.check_for_updates()
            if new_version:
                self.update_available.emit(new_version)

        thread = threading.Thread(target=check_thread, daemon=True)
        thread.start()
        self.update_available.connect(self._on_update_available)

    def _on_update_available(self, new_version: str) -> None:
        reply = QMessageBox.question(
            self,
            "Update Available",
            f"Version {new_version} is available. Download now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._download_update(new_version)

    def _download_update(self, new_version: str) -> None:
        download_url = f"https://felfeldm.example.com/download/FelfelDM-{new_version}.exe"
        if self.updater.download_update(new_version, download_url):
            QMessageBox.information(self, "Update Downloaded", "Update verified. Installing...")
            self.updater.install_update()
            self.close()
        else:
            QMessageBox.critical(self, "Update Failed", "Download or verification failed.")

    def _on_stats_updated(self, data: Dict[str, Any]) -> None:
        self.table_model.refresh()
        if "global_stat" in data:
            stat = data["global_stat"]
            speed = int(stat.get("downloadSpeed", 0))
            self.speed_label.setText(f"Speed: {format_speed(speed)}")
            count = int(stat.get("numActive", 0))
            self.download_count_label.setText(f"Downloads: {count}")

    def _on_connection_changed(self, connected: bool) -> None:
        if connected:
            self.status_label.setText("Connected to aria2")
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setText("Disconnected - reconnecting...")
            self.status_label.setStyleSheet("color: red;")

    def _filter_table(self, text: str) -> None:
        self.proxy_model.setFilterFixedString(text)

    def _refresh_table(self) -> None:
        self.table_model.refresh()

    def _add_downloads(self) -> None:
        dialog = AddDownloadDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            urls = dialog.get_urls()
            options = dialog.get_options()
            queue_name = dialog.get_queue()
            start_immediately = dialog.start_immediately()

            for url in urls:
                gid = self.aria2.add_url([url], options)
                if gid:
                    self.store.add_gid_to_queue(queue_name, gid)
                    if start_immediately:
                        self.aria2.unpause(gid)
            self._refresh_table()

    def _single_download(self) -> None:
        dialog = SingleDownloadDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            url = dialog.get_url()
            if url:
                gid = self.aria2.add_url([url], dialog.get_options())
                if gid:
                    self.store.add_gid_to_queue("default", gid)
                    self._refresh_table()

    def _quick_download(self) -> None:
        dialog = QuickDownloadDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            url = dialog.get_url()
            if url:
                gid = self.aria2.add_url([url], {})
                if gid:
                    self.store.add_gid_to_queue("default", gid)
                    self._refresh_table()

    def _pause_all(self) -> None:
        self.aria2.pause_all()
        self._refresh_table()

    def _resume_all(self) -> None:
        self.aria2.unpause_all()
        self._refresh_table()

    def _show_settings(self) -> None:
        dialog = SettingsDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.store.reload()
            self._refresh_table()

    def _show_context_menu(self, pos) -> None:
        index = self.table_view.indexAt(pos)
        if not index.isValid():
            return
        source_index = self.proxy_model.mapToSource(index)
        row = source_index.row()
        gid = self.table_model.get_gid(row)
        if not gid:
            return

        menu = QMenu(self)
        menu.addAction("Pause").triggered.connect(lambda: self._pause_download(gid))
        menu.addAction("Resume").triggered.connect(lambda: self._resume_download(gid))
        menu.addSeparator()
        menu.addAction("Remove").triggered.connect(lambda: self._remove_download(gid))
        menu.addAction("Force Remove").triggered.connect(lambda: self._force_remove_download(gid))
        menu.addSeparator()
        menu.addAction("Show Details").triggered.connect(lambda: self._show_download_details(gid))
        menu.exec(self.table_view.viewport().mapToGlobal(pos))

    def _pause_download(self, gid: str) -> None:
        self.aria2.pause(gid)
        self._refresh_table()

    def _resume_download(self, gid: str) -> None:
        self.aria2.unpause(gid)
        self._refresh_table()

    def _remove_download(self, gid: str) -> None:
        reply = QMessageBox.question(self, "Remove", "Are you sure?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.aria2.remove(gid)
            self.store.remove_gid(gid)
            self._refresh_table()

    def _force_remove_download(self, gid: str) -> None:
        reply = QMessageBox.question(self, "Force Remove", "Are you sure?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.aria2.force_remove(gid)
            self.store.remove_gid(gid)
            self._refresh_table()

    def _show_download_details(self, gid: str) -> None:
        if gid not in self.progress_dialogs:
            self.progress_dialogs[gid] = DownloadProgressDialog(gid, self.aria2, self)
        self.progress_dialogs[gid].show()
        self.progress_dialogs[gid].raise_()

    def _show_about(self) -> None:
        QMessageBox.about(self, "About FelfelDM", f"FelfelDM v{__version__}\n\nA modern download manager.")

    def closeEvent(self, event) -> None:
        gids = self.store.get_all_gids()
        self.session_mgr.save_session(gids)
        if self.worker:
            self.worker.stop()
        self.aria2_manager.stop()
        event.accept()
