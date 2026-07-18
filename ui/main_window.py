# ui/main_window.py

import os
import time
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Any, Set, Tuple
from pathlib import Path

from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

import re

from core import Aria2RPC, DataStore, Queue, BackendWorker, TempDB
from ui.dialogs import *
from ui.update_dialog import UpdateDialog
from ui.table_model import DownloadTableModel
from ui.delegates import ProgressDelegate
from utils.helpers import format_size, format_speed, get_category, get_icon
from core.local_server import LocalServer
from utils.helpers import get_resource_path
from utils.style import setup_style
from ui.splash import SplashScreen
from core.proxy_manager import ProxyManager, ProxyConfig


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.store = DataStore()
        self.temp_db = TempDB()
        self._pending_size_fetch: Dict[str, float] = {}
        self._shutdown_timer: Optional[QTimer] = None
        self._shutdown_countdown: int = 20
        self._shutdown_dialog: Optional[QDialog] = None
        self._shutdown_dialog_shown: bool = False

        theme_setting: str = self.store.settings.get("theme", "auto")
        is_dark: bool = self._detect_theme(theme_setting)

        self.splash = SplashScreen(is_dark=is_dark)
        self.splash.update_status("Loading FelfelDM...", 5)
        QApplication.processEvents()

        self.setWindowTitle("FelfelDM")
        self.setMinimumSize(1050, 680)

        self._pending_pause: Set[str] = set()
        self._current_queue_idx: int = 0
        self._all_downloads: Dict[str, Dict[str, Any]] = {}
        self._last_calculated_global_speed: int = 0
        self._cleared_gids: Set[str] = set()
        self._progress_dialog: Optional[QDialog] = None
        self._youtube_dialog: Optional[QDialog] = None
        self.worker: Optional[BackendWorker] = None
        self.local_server: Optional[LocalServer] = None

        self.splash.update_status("Loading data from storage...", 10)
        QApplication.processEvents()

        self.splash.update_status("Setting up queues...", 25)
        QApplication.processEvents()
        self._ensure_default_queue()

        self.splash.update_status("Initializing aria2...", 35)
        QApplication.processEvents()

        self.aria2 = Aria2RPC(
            self.store.settings["aria2_host"],
            self.store.settings["aria2_port"],
            self.store.settings["aria2_secret"],
        )

        self.proxy_manager = ProxyManager(self.store)
        self._apply_proxy_to_aria2()
        self.aria2.on_error = self._on_aria2_error

        self.splash.update_status("Connecting to aria2...", 45)
        QApplication.processEvents()

        if not self.aria2.is_connected():
            self.splash.update_status("Starting aria2 daemon...", 55)
            self.aria2.start_aria2()
            QApplication.processEvents()

        self.splash.update_status("aria2 ready!", 60)
        QApplication.processEvents()

        self.splash.update_status("Building interface...", 70)
        QApplication.processEvents()
        self._build_ui()

        self.splash.update_status("Building tray...", 80)
        QApplication.processEvents()
        self._build_tray()

        self.splash.update_status("Applying settings...", 85)
        QApplication.processEvents()
        self._apply_global_speed_limit()

        self.splash.update_status("Starting services...", 90)
        QApplication.processEvents()
        self._start_backend()

        self._speed_samples = []
        self._max_samples = 8
        self._last_speed_update = time.time()
        self._smooth_speed = 0

        self.speed_update_timer = QTimer()
        self.speed_update_timer.timeout.connect(self._update_speed_display)
        self.speed_update_timer.start(100)

        self.splash.update_status("Waiting for aria2...", 92)
        QApplication.processEvents()

        wait_count = 0
        while not self.aria2.is_connected() and wait_count < 25:
            time.sleep(0.2)
            wait_count += 1

        self.splash.update_status("Restoring downloads...", 93)
        QApplication.processEvents()
        self._restore_downloads_with_progress()

        self.splash.update_status("Starting local server...", 95)
        QApplication.processEvents()
        self.local_server = LocalServer(main_window=self)
        self.local_server.start(8766)

        self.splash.update_status("Ready!", 100)
        QApplication.processEvents()

        QTimer.singleShot(800, self._close_splash)

    def _detect_theme(self, theme_setting: str) -> bool:
        if theme_setting == "light":
            return False
        if theme_setting == "dark":
            return True
        try:
            result = subprocess.run(
                [
                    "kreadconfig5",
                    "--group",
                    "Colors:Window",
                    "--key",
                    "BackgroundNormal",
                ],
                capture_output=True,
                text=True,
            )
            if result.stdout:
                color = result.stdout.strip()
                if color.startswith("#"):
                    r, g, b = (
                        int(color[1:3], 16),
                        int(color[3:5], 16),
                        int(color[5:7], 16),
                    )
                    brightness = (r * 299 + g * 587 + b * 114) / 1000
                    return brightness < 128
        except Exception:
            pass
        return True

    def _ensure_default_queue(self) -> None:
        if not self.store.queues:
            default_queue = Queue("Default", paused=True)
            self.store.queues.append(default_queue)
            self.store.save()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("splitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)

        sidebar = self._build_sidebar()
        main_area = self._build_main_area()

        splitter.addWidget(sidebar)
        splitter.addWidget(main_area)
        splitter.setSizes([210, 840])

        root.addWidget(splitter)

        self._build_menubar()

        self._refresh_queue_list()
        self._update_queue_buttons()

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(180)
        sidebar.setMaximumWidth(350)
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(10, 12, 10, 12)
        sb_lay.setSpacing(8)

        header_lay = QHBoxLayout()
        header_lay.addStretch()
        sb_lay.addLayout(header_lay)

        sb_lay.addWidget(QLabel("<b>Queues</b>"))
        sb_lay.addSpacing(4)

        self.queue_list = QListWidget()
        self.queue_list.currentRowChanged.connect(self._on_queue_changed)
        sb_lay.addWidget(self.queue_list)

        btn_layout = QHBoxLayout()
        self.start_queue_btn = QPushButton(get_icon("media-playback-start"), "Start")
        self.start_queue_btn.setObjectName("start_btn")
        self.start_queue_btn.clicked.connect(self._start_current_queue)
        btn_layout.addWidget(self.start_queue_btn)

        self.pause_queue_btn = QPushButton(get_icon("media-playback-pause"), "Pause")
        self.pause_queue_btn.setObjectName("pause_btn")
        self.pause_queue_btn.clicked.connect(self._pause_current_queue)
        btn_layout.addWidget(self.pause_queue_btn)
        sb_lay.addLayout(btn_layout)

        move_layout = QHBoxLayout()
        move_layout.setSpacing(4)

        self.move_up_btn = QPushButton()
        self.move_up_btn.setIcon(get_icon("go-up"))
        self.move_up_btn.setToolTip("Move queue up")
        self.move_up_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.move_up_btn.setFixedHeight(30)
        self.move_up_btn.setMinimumWidth(0)
        self.move_up_btn.clicked.connect(self._move_queue_up)
        move_layout.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton()
        self.move_down_btn.setIcon(get_icon("go-down"))
        self.move_down_btn.setToolTip("Move queue down")
        self.move_down_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.move_down_btn.setFixedHeight(30)
        self.move_down_btn.setMinimumWidth(0)
        self.move_down_btn.clicked.connect(self._move_queue_down)
        move_layout.addWidget(self.move_down_btn)

        sb_lay.addLayout(move_layout)

        mgmt_lay = QVBoxLayout()
        mgmt_lay.setSpacing(4)
        mgmt_lay.addWidget(
            QPushButton(get_icon("list-add"), "New Queue", clicked=self._add_queue)
        )
        mgmt_lay.addWidget(
            QPushButton(get_icon("configure"), "Settings", clicked=self._edit_queue)
        )
        mgmt_lay.addWidget(
            QPushButton(get_icon("list-remove"), "Delete", clicked=self._delete_queue)
        )
        sb_lay.addLayout(mgmt_lay)

        sb_lay.addSpacing(12)

        status_group = QGroupBox("Status")
        status_lay = QVBoxLayout(status_group)
        status_lay.setSpacing(4)

        self.queue_status_lbl = QLabel("⏸ Paused")
        self.queue_status_lbl.setStyleSheet("color: #f39c12; font-weight: bold;")
        status_lay.addWidget(self.queue_status_lbl)

        self.speed_limit_lbl = QLabel("")
        self.speed_limit_lbl.setStyleSheet("color: #f39c12; font-size: 11px;")
        status_lay.addWidget(self.speed_limit_lbl)

        self.status_lbl = QLabel("● Disconnected")
        self.status_lbl.setStyleSheet("color: #e74c3c; font-weight: bold;")
        status_lay.addWidget(self.status_lbl)

        self.schedule_status_lbl = QLabel("")
        self.schedule_status_lbl.setStyleSheet("color: #3498db; font-size: 11px;")
        self.schedule_status_lbl.setWordWrap(True)
        status_lay.addWidget(self.schedule_status_lbl)

        sb_lay.addWidget(status_group)
        sb_lay.addStretch()
        return sidebar

    def _build_main_area(self) -> QWidget:
        main_area = QWidget()
        ma_lay = QVBoxLayout(main_area)
        ma_lay.setContentsMargins(0, 0, 0, 0)
        ma_lay.setSpacing(0)

        toolbar = self._build_toolbar()
        ma_lay.addWidget(toolbar)

        self.table = QTableView()
        self.table.doubleClicked.connect(self._on_table_double_click)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(True)

        self.model = DownloadTableModel()
        self.progress_delegate = ProgressDelegate(self)
        self.table.setItemDelegateForColumn(2, self.progress_delegate)
        self.table.setModel(self.model)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setColumnWidth(2, 180)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(4, 100)
        self.table.horizontalHeader().setStretchLastSection(False)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        ma_lay.addWidget(self.table)

        if self.table.selectionModel():
            self.table.selectionModel().selectionChanged.connect(
                self._update_toggle_button
            )

        speed_widget = QWidget()
        speed_layout = QHBoxLayout(speed_widget)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(4)

        self.speed_icon_label = QLabel()
        self.speed_icon_label.setPixmap(get_icon("go-down").pixmap(16, 16))

        self.speed_status_label = QLabel("0 B/s")
        self.speed_status_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                color: #3daee9;
                min-width: 80px;
            }
        """)

        speed_layout.addWidget(self.speed_icon_label)
        speed_layout.addWidget(self.speed_status_label)

        self.statusBar().addPermanentWidget(speed_widget)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.statusBar().addPermanentWidget(self.progress_bar, 1)
        self.progress_bar.setTextVisible(True)
        self.statusBar().addPermanentWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        self.statusBar().addPermanentWidget(self.status_label)

        self.shutdown_cb = QCheckBox("Shutdown on Finish")
        self.shutdown_cb.setChecked(
            self.store.settings.get("shutdown_after_finish", False)
        )
        self.shutdown_cb.toggled.connect(self._toggle_shutdown)
        self.statusBar().addPermanentWidget(self.shutdown_cb)

        return main_area

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(8, 4, 8, 4)
        tb_lay.setSpacing(4)

        self.btn_add = QPushButton(get_icon("download"), "Download")
        self.btn_add.clicked.connect(self._quick_download)

        self.btn_add_queue = QPushButton(get_icon("list-add"), "Add to Queue")
        self.btn_add_queue.clicked.connect(self._add_download)
        tb_lay.addWidget(self.btn_add_queue)
        tb_lay.addWidget(self.btn_add)

        self.btn_toggle = QPushButton(get_icon("media-playback-pause"), "Pause")
        self.btn_toggle.clicked.connect(self._toggle_pause_resume)
        self.btn_toggle.setEnabled(False)
        tb_lay.addWidget(self.btn_toggle)

        self.btn_move_queue = QPushButton(get_icon("go-next"), "Move to Queue")
        self.btn_move_queue.clicked.connect(self._move_selected_to_queue)
        self.btn_move_queue.setEnabled(False)
        tb_lay.addWidget(self.btn_move_queue)

        self.btn_remove = QPushButton(get_icon("edit-delete"), "Remove")
        self.btn_remove.clicked.connect(self._remove_selected)
        tb_lay.addWidget(self.btn_remove)

        self.btn_clear_completed = QPushButton(
            get_icon("edit-clear"), "Clear Completed"
        )
        self.btn_clear_completed.clicked.connect(self._clear_completed_downloads)
        tb_lay.addWidget(self.btn_clear_completed)

        self.btn_youtube = QPushButton()
        self.btn_youtube.setIcon(get_icon("video-display"))
        self.btn_youtube.setText(" YouTube")
        self.btn_youtube.clicked.connect(self._youtube_download)
        tb_lay.addWidget(self.btn_youtube)

        tb_lay.addStretch()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search...")
        self.search_box.setMaximumWidth(180)
        self.search_box.textChanged.connect(self._filter_downloads)
        tb_lay.addWidget(self.search_box)

        self.btn_settings = QPushButton(get_icon("configure"), "")
        self.btn_settings.clicked.connect(self._open_settings)
        tb_lay.addWidget(self.btn_settings)

        return toolbar

    def _build_menubar(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        add_action = QAction(get_icon("list-add"), "Add Downloads", self)
        add_action.triggered.connect(self._add_download)
        add_action.setShortcut("Ctrl+N")
        file_menu.addAction(add_action)

        file_menu.addSeparator()

        settings_action = QAction(get_icon("configure"), "Settings", self)
        settings_action.triggered.connect(self._open_settings)
        settings_action.setShortcut("Ctrl+,")
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        quit_action = QAction(get_icon("application-exit"), "Quit", self)
        quit_action.triggered.connect(self.quit_app)
        quit_action.setShortcut("Ctrl+Q")
        file_menu.addAction(quit_action)

        queue_menu = mb.addMenu("&Queue")
        queue_menu.addAction(get_icon("list-add"), "New Queue", self._add_queue)
        queue_menu.addAction(get_icon("configure"), "Edit Queue", self._edit_queue)
        queue_menu.addAction(
            get_icon("list-remove"), "Delete Queue", self._delete_queue
        )

        view_menu = mb.addMenu("&View")
        refresh_action = QAction(get_icon("view-refresh"), "Refresh", self)
        refresh_action.triggered.connect(self._refresh_table)
        refresh_action.setShortcut("F5")
        view_menu.addAction(refresh_action)

        help_menu = mb.addMenu("&Help")
        help_menu.addAction("About", self._show_about)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)

        icon_paths = [get_resource_path("logo/icon512.png")]

        for path in icon_paths:
            if os.path.exists(path):
                self.tray.setIcon(QIcon(path))
                print(f"✅ Tray icon loaded from: {path}")
                break
        else:
            self.tray.setIcon(get_icon("download-manager"))
            print("⚠️ Tray icon: Using Papirus fallback")

        menu = QMenu()
        menu.addAction(get_icon("window"), "Show", self.show)
        menu.addAction(get_icon("application-exit"), "Quit", self.quit_app)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: (
                self.show()
                if r == QSystemTrayIcon.ActivationReason.DoubleClick
                else None
            )
        )
        self.tray.show()

    def closeEvent(self, event: QCloseEvent) -> None:
        has_active = False
        for q in self.store.queues:
            for gid in q.downloads:
                if gid in self._all_downloads:
                    status = self._all_downloads[gid].get("status", "")
                    if status in ["active", "waiting", "downloading"]:
                        has_active = True
                        break
            if has_active:
                break

        if has_active:
            reply = QMessageBox.question(
                self,
                "Downloads in Progress",
                "There are active downloads. Closing the main window will "
                "keep downloads running in the background.\n\n"
                "Do you want to close the main window?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.hide()
                self.tray.showMessage(
                    "FelfelDM",
                    "Downloads are running in the background.\n"
                    "Right-click the tray icon to show the main window.",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
                event.ignore()
                return

        if hasattr(self, "tray") and self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            self.quit_app()
            event.accept()

    def quit_app(self) -> None:
        print("🛑 Shutting down...")

        print("⏸️ Pausing all downloads and saving session...")

        if hasattr(self, "speed_update_timer"):
            self.speed_update_timer.stop()
            print("⏹️ Speed update timer stopped")

        try:
            self.aria2.save_session()
            print("💾 Session saved")
        except Exception as e:
            print(f"⚠️ Could not save session: {e}")

        for q in self.store.queues:
            for gid in q.downloads:
                try:
                    if gid in self._all_downloads:
                        status = self._all_downloads[gid].get("status", "")
                        if status in ["active", "waiting", "downloading"]:
                            self.aria2.pause(gid)
                            self._all_downloads[gid]["status"] = "paused"
                            self._all_downloads[gid]["downloadSpeed"] = 0
                except Exception as e:
                    print(f"⚠️ Could not pause {gid}: {e}")

            q.paused = True
            q.manually_paused = True
            print(f"⏸️ Queue '{q.name}' set to paused")

        self._save_downloads_info()
        self.store.save()
        print("💾 Data saved with paused status")

        if self._progress_dialog is not None:
            try:
                self._progress_dialog.close()
            except Exception:
                pass
            self._progress_dialog = None

        if self._youtube_dialog is not None:
            try:
                self._youtube_dialog.close()
            except Exception:
                pass
            self._youtube_dialog = None

        if hasattr(self, "worker"):
            self.worker.terminate()

        # ===== Shutdown DataStore to flush pending writes =====
        if hasattr(self.store, "shutdown"):
            self.store.shutdown()

        try:
            self.aria2.shutdown()
        except Exception:
            pass

        if hasattr(self, "tray"):
            self.tray.hide()

        import sys

        sys.exit(0)

    def _save_downloads_info(self) -> None:
        """Save download info from _all_downloads to queue downloads_info"""
        for q in self.store.queues:
            for gid in q.downloads:
                if gid in self._all_downloads:
                    dl = self._all_downloads[gid]
                    if gid not in q.downloads_info:
                        q.downloads_info[gid] = {}

                    q.downloads_info[gid].update(
                        {
                            "url": q.downloads_info[gid].get("url", ""),
                            "name": dl.get("name", "Unknown"),
                            "totalLength": dl.get("totalLength", 0),
                            "completedLength": dl.get("completedLength", 0),
                            "status": dl.get("status", "unknown"),
                            "files": dl.get("files", []),
                            "category": dl.get("category", "📁 Other"),
                            "error_count": dl.get("error_count", 0),
                            "errorMessage": dl.get("errorMessage", ""),
                            "download_type": dl.get("download_type", "normal"),
                        }
                    )

                    if not q.downloads_info[gid].get("files") and dl.get("files"):
                        q.downloads_info[gid]["files"] = dl.get("files")

                    print(
                        f"💾 Saved: {dl.get('name')} - total: {dl.get('totalLength', 0)}, completed: {dl.get('completedLength', 0)}"
                    )

    def _restore_downloads_with_progress(self) -> None:
        """Restore downloads from storage - use stored info first, then aria2"""
        print("🔄 Loading downloads from storage...")

        if not self.aria2.is_connected():
            print("⏳ Waiting for aria2 to connect...")
            for attempt in range(15):
                time.sleep(0.5)
                if self.aria2.is_connected():
                    print(f"✅ aria2 connected after {attempt+1} attempts")
                    break
            else:
                print("⚠️ aria2 still not connected, loading from storage anyway...")

        restored_count = 0

        for q in self.store.queues:
            for gid in q.downloads[:]:
                info = q.downloads_info.get(gid, {})

                name = info.get("name", "Unknown")

                total_length = int(info.get("totalLength", 0))
                completed_length = int(info.get("completedLength", 0))
                category = info.get("category", "📁 Other")
                download_type = info.get("download_type", "normal")
                files = info.get("files", [])

                if total_length == 0:
                    status_data = self.aria2.get_status(gid)
                    if status_data and isinstance(status_data, dict):
                        aria2_total = int(status_data.get("totalLength", 0))
                        aria2_completed = int(status_data.get("completedLength", 0))
                        if aria2_total > 0:
                            total_length = aria2_total
                            completed_length = aria2_completed
                            print(f"📁 Got size from aria2: {total_length}")
                        else:

                            aria2_file_info = self.aria2.get_download_info_from_file(
                                gid
                            )
                            if aria2_file_info:
                                file_total = aria2_file_info.get("totalLength", 0)
                                file_completed = aria2_file_info.get(
                                    "completedLength", 0
                                )
                                if file_total > 0:
                                    total_length = file_total
                                    completed_length = file_completed
                                    print(
                                        f"📁 Got size from .aria2 file: {total_length}"
                                    )

                status_data = self.aria2.get_status(gid)
                if status_data and isinstance(status_data, dict):
                    status = status_data.get("status", "paused")
                    speed = int(status_data.get("downloadSpeed", 0))
                    files = status_data.get("files", files)
                else:
                    status = info.get("status", "paused")
                    speed = 0

                print(
                    f"📁 Loaded: {name} - {status} - total: {total_length}, completed: {completed_length}"
                )

                self._all_downloads[gid] = {
                    "gid": gid,
                    "name": name,
                    "status": status,
                    "totalLength": total_length,
                    "completedLength": completed_length,
                    "downloadSpeed": speed,
                    "connections": 0,
                    "files": files,
                    "errorMessage": "",
                    "category": category,
                    "size_fetch_attempts": 0,
                    "error_count": 0,
                    "download_type": download_type,
                }

                q.downloads_info[gid]["status"] = status
                q.downloads_info[gid]["totalLength"] = total_length
                q.downloads_info[gid]["completedLength"] = completed_length
                q.downloads_info[gid]["files"] = files

                restored_count += 1

        self.store.save()

        if restored_count > 0:
            print(f"✅ Loaded {restored_count} download(s)")
        else:
            print("📁 No downloads to load")

        if self.splash is not None:
            self.splash.update_status("Ready!", 100)
            QApplication.processEvents()

    def _try_pause_download(self, gid: str, name: str) -> None:
        try:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                if status not in ["complete", "error", "removed"]:
                    self.aria2.pause(gid)
                    print(f"⏸️ Paused: {name}")
                else:
                    print(f"ℹ️ Skipping pause (status: {status}): {name}")
        except Exception as e:
            print(f"ℹ️ Could not pause (ignored): {name}")

    def _delayed_restore(self) -> None:
        if self.splash is None:
            print("⚠️ Splash is None, restoring without progress")
            self._restore_downloads_with_progress()
            return

        if self.aria2.is_connected():
            if self.splash is not None:
                self.splash.update_status("Restoring downloads...", 93)
                QApplication.processEvents()
            self._restore_downloads_with_progress()
        else:
            QTimer.singleShot(200, self._delayed_restore)

    def _on_queue_changed(self, idx: int) -> None:
        if idx >= 0:
            self._current_queue_idx = idx
            self._update_queue_status()
            self._update_queue_buttons()
            self._update_shutdown_button_state()
            self._refresh_table()

    def _current_queue(self) -> Optional[Queue]:
        if 0 <= self._current_queue_idx < len(self.store.queues):
            return self.store.queues[self._current_queue_idx]
        return None

    def _update_queue_buttons(self) -> None:
        q = self._current_queue()

        current_row = self.queue_list.currentRow()
        total_queues = len(self.store.queues)

        self.move_up_btn.setEnabled(current_row > 0)
        self.move_down_btn.setEnabled(0 <= current_row < total_queues - 1)

        if not q or len(q.downloads) == 0 or q.name == "__direct__":
            self.start_queue_btn.setEnabled(False)
            self.pause_queue_btn.setEnabled(False)
            return

        has_downloading = False
        has_paused = False
        has_waiting = False
        has_pending = False
        has_getting_size = False
        has_error = False

        for gid in q.downloads:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                total = self._all_downloads[gid].get("totalLength", 0)

                if total == 0 and status in ["waiting", "paused"]:
                    has_getting_size = True
                elif status in ["active", "waiting", "downloading"]:
                    has_downloading = True
                elif status == "pending":
                    has_pending = True
                elif status == "paused":
                    has_paused = True
                elif status == "waiting":
                    has_waiting = True
                elif status == "error":
                    has_error = True

        all_done = all(
            self._all_downloads.get(gid, {}).get("status", "")
            in ["complete", "completed", "error", "removed"]
            for gid in q.downloads
            if gid in self._all_downloads
        )

        if all_done and len(q.downloads) > 0:
            self.start_queue_btn.setEnabled(False)
            self.pause_queue_btn.setEnabled(False)
            return

        if has_downloading:
            self.start_queue_btn.setEnabled(False)
            self.pause_queue_btn.setEnabled(True)
        else:
            if has_getting_size:
                self.start_queue_btn.setEnabled(False)
                self.start_queue_btn.setToolTip("Waiting for file size...")
            else:
                has_resumable = has_pending or has_paused or has_waiting or has_error
                self.start_queue_btn.setEnabled(has_resumable)
                self.start_queue_btn.setToolTip("")
            self.pause_queue_btn.setEnabled(False)

    def _refresh_queue_list(self) -> None:
        self.queue_list.blockSignals(True)
        self.queue_list.clear()

        something_changed = False

        for q in self.store.queues:
            if len(q.downloads) == 0:
                # Only mark as changed if it wasn't already empty
                if q.paused != True or q.manually_paused != False:
                    something_changed = True
                q.paused = True
                q.manually_paused = False
                self._cleared_gids.clear()
                for gid in q.downloads[:]:
                    if gid in self._all_downloads:
                        del self._all_downloads[gid]
                q.downloads.clear()

            if q.name == "__direct__":
                item = QListWidgetItem(
                    get_icon("media-playback-start"), "Direct Downloads"
                )
                item.setForeground(QColor("#3498db"))
            else:
                item = QListWidgetItem(q.name)

            if q.paused:
                item.setIcon(get_icon("media-playback-pause"))
                item.setForeground(QColor("#f39c12"))
            else:
                item.setIcon(get_icon("media-playback-start"))
                item.setForeground(QColor("#27ae60"))

            self.queue_list.addItem(item)

        if self.store.queues:
            self._current_queue_idx = min(
                self._current_queue_idx, len(self.store.queues) - 1
            )
            self.queue_list.setCurrentRow(self._current_queue_idx)

        self.queue_list.blockSignals(False)
        self._update_queue_status()
        self._update_queue_buttons()

        # Only save if something changed
        if something_changed:
            self.store.save()

    def _update_queue_status(self) -> None:
        q = self._current_queue()
        if not q:
            self.queue_status_lbl.setText("⏸ No Queue")
            self.queue_status_lbl.setStyleSheet("color: #95a5a6; font-weight: bold;")
            self.schedule_status_lbl.setText("")
            self.status_label.setText("Ready")
            return

        if q.name == "__direct__":
            self.queue_status_lbl.setText("Direct Downloads")
            self.queue_status_lbl.setStyleSheet("color: #3498db; font-weight: bold;")
            self.schedule_status_lbl.setText("")
            self.status_label.setText("Direct Downloads")
            return

        if len(q.downloads) == 0:
            self.queue_status_lbl.setText("📭 Empty")
            self.queue_status_lbl.setStyleSheet("color: #95a5a6; font-weight: bold;")
            self.schedule_status_lbl.setText("Add downloads to start")
            self.status_label.setText("📭 Empty queue")
            return

        speed_limit_text = ""
        if getattr(q, "speed_limit", 0) > 0:
            self.speed_limit_lbl.setText(f"Speed Limit: {q.speed_limit} KB/s")
            self.speed_limit_lbl.setStyleSheet("color: #f39c12; font-size: 11px;")
        else:
            self.speed_limit_lbl.setText("")

        all_complete = True
        has_any_download = False
        for gid in q.downloads:
            has_any_download = True
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                if status not in ["complete", "error", "removed"]:
                    all_complete = False
                    break
            else:
                all_complete = False
                break

        if all_complete and has_any_download:
            self.queue_status_lbl.setText("✅ Complete")
            self.queue_status_lbl.setStyleSheet("color: #27ae60; font-weight: bold;")
            self.schedule_status_lbl.setText("")
            self.status_label.setText("✅ All downloads complete")
            return

        if q.schedule_enabled:
            self._update_scheduled_queue_status(q, speed_limit_text)
        else:
            self._update_regular_queue_status(q, speed_limit_text)

    def _update_scheduled_queue_status(self, q: Queue, speed_limit_text: str) -> None:
        if q.is_scheduled_now():
            if not q.paused:
                has_active = any(
                    gid in self._all_downloads
                    and self._all_downloads[gid].get("status", "")
                    in ["active", "waiting", "downloading"]
                    for gid in q.downloads
                )
                if has_active:
                    self.queue_status_lbl.setText(
                        f"▶ Running (🕐 Scheduled){speed_limit_text}"
                    )
                    self.queue_status_lbl.setStyleSheet(
                        "color: #27ae60; font-weight: bold;"
                    )
                else:
                    self.queue_status_lbl.setText(
                        f"⏳ Waiting (🕐 Scheduled){speed_limit_text}"
                    )
                    self.queue_status_lbl.setStyleSheet(
                        "color: #3498db; font-weight: bold;"
                    )
                self.schedule_status_lbl.setText("🕐 Schedule time is active ✓")
                self.schedule_status_lbl.setStyleSheet(
                    "color: #27ae60; font-weight: bold;"
                )
                self.status_label.setText("🕐 Scheduled time is active")
            else:
                self.queue_status_lbl.setText(
                    f"⏸ Paused (🕐 Scheduled){speed_limit_text}"
                )
                self.queue_status_lbl.setStyleSheet(
                    "color: #f39c12; font-weight: bold;"
                )
                self.schedule_status_lbl.setText(
                    "🕐 Click 'Start' to begin downloads now"
                )
                self.schedule_status_lbl.setStyleSheet(
                    "color: #3498db; font-weight: bold;"
                )
                self.status_label.setText("⏸ Paused - Schedule active")
        else:
            days_text = ", ".join(
                ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i] for i in q.days
            )
            next_time = q.get_next_schedule_time()
            if next_time:
                self.schedule_status_lbl.setText(
                    f"⏰ Next: {next_time.strftime('%H:%M on %A')}"
                )
            else:
                self.schedule_status_lbl.setText(
                    f"⏰ Next: {q.schedule_start.strftime('%H:%M')}-{q.schedule_end.strftime('%H:%M')} {days_text}"
                )
            self.schedule_status_lbl.setStyleSheet("color: #3498db; font-size: 11px;")

            if q.paused:
                self.queue_status_lbl.setText(
                    f"⏸ Paused (⏰ Waiting){speed_limit_text}"
                )
                self.queue_status_lbl.setStyleSheet(
                    "color: #f39c12; font-weight: bold;"
                )
                self.status_label.setText(
                    f"⏸ Paused - Next: {q.schedule_start.strftime('%H:%M')}"
                )
            else:
                self.queue_status_lbl.setText(
                    f"⏰ Waiting for Schedule{speed_limit_text}"
                )
                self.queue_status_lbl.setStyleSheet(
                    "color: #3498db; font-weight: bold;"
                )
                self.status_label.setText(
                    f"⏰ Waiting: {q.schedule_start.strftime('%H:%M')}"
                )

    def _update_regular_queue_status(self, q: Queue, speed_limit_text: str) -> None:
        if q.paused:
            has_resumable = any(
                gid in self._all_downloads
                and self._all_downloads[gid].get("status", "") in ["paused", "waiting"]
                for gid in q.downloads
            )
            if has_resumable:
                self.queue_status_lbl.setText(f"⏸ Paused{speed_limit_text}")
                self.queue_status_lbl.setStyleSheet(
                    "color: #f39c12; font-weight: bold;"
                )
                self.schedule_status_lbl.setText("Click 'Start' to resume downloads")
                self.status_label.setText("⏸ Paused")
            else:
                self.queue_status_lbl.setText(f"⏸ Paused{speed_limit_text}")
                self.queue_status_lbl.setStyleSheet(
                    "color: #95a5a6; font-weight: bold;"
                )
                self.schedule_status_lbl.setText("")
                self.status_label.setText("⏸ Paused")
        else:
            has_active = any(
                gid in self._all_downloads
                and self._all_downloads[gid].get("status", "")
                in ["active", "waiting", "downloading"]
                for gid in q.downloads
            )
            if has_active:
                self.queue_status_lbl.setText(f"▶ Running{speed_limit_text}")
                self.queue_status_lbl.setStyleSheet(
                    "color: #27ae60; font-weight: bold;"
                )
            else:
                self.queue_status_lbl.setText(f"⏳ Idle{speed_limit_text}")
                self.queue_status_lbl.setStyleSheet(
                    "color: #95a5a6; font-weight: bold;"
                )
            self.schedule_status_lbl.setText("")
            self.status_label.setText("▶ Running")

    def _start_current_queue(self) -> None:
        q = self._current_queue()
        if not q:
            return
        if q.name == "__direct__":
            return

        if q.schedule_enabled and not q.is_scheduled_now():
            next_time = q.get_next_schedule_time()
            if next_time:
                time_str = next_time.strftime("%H:%M on %A")
                QMessageBox.information(
                    self,
                    "Queue Scheduled",
                    f"This queue is scheduled to start at {time_str}.\n\n"
                    f"It will start automatically at that time.\n"
                    f"You don't need to start it manually.",
                    QMessageBox.StandardButton.Ok,
                )
            else:
                QMessageBox.information(
                    self,
                    "Queue Scheduled",
                    "This queue is scheduled but no upcoming time found.",
                    QMessageBox.StandardButton.Ok,
                )
            return

        # ===== Validation phase (no mutations) =====
        for gid in q.downloads:
            if gid in self._all_downloads:
                total = self._all_downloads[gid].get("totalLength", 0)
                status = self._all_downloads[gid].get("status", "")
                if total == 0 and status in ["waiting", "paused"]:
                    QMessageBox.warning(
                        self,
                        "Getting Size",
                        "Some downloads are still fetching file size.\n"
                        "Please wait until size is fetched before starting the queue.",
                        QMessageBox.StandardButton.Ok,
                    )
                    return

        # ===== Mutation phase =====
        q.manually_paused = False
        self._apply_settings_to_aria2()
        q.paused = False
        self.store.save()
        self._refresh_queue_list()

        resumed = 0
        for gid in q.downloads:
            download_type = "normal"
            if gid in self._all_downloads:
                download_type = self._all_downloads[gid].get("download_type", "normal")
                # Reset error count now that we're committed
                self._all_downloads[gid]["error_count"] = 0

            if download_type == "youtube":
                real_status = self._all_downloads[gid].get("status", "")
                if real_status in ["paused"]:
                    self._start_youtube_download(gid)
                    self._all_downloads[gid]["status"] = "downloading"
                    resumed += 1
            else:

                status_data = self.aria2.get_status(gid)

                if not status_data:

                    self._re_add_download(gid)
                    resumed += 1
                    continue

                if gid in self._all_downloads:
                    real_status = self._all_downloads[gid].get("status", "")
                else:
                    real_status = "waiting"

                if real_status in ["paused", "waiting", "error"]:
                    if q and getattr(q, "speed_limit", 0) > 0:
                        time.sleep(0.3)
                        self.aria2.set_download_speed_limit(gid, q.speed_limit)

                    result = self.aria2.resume(gid)
                    if result is not None:
                        resumed += 1
                        if gid in self._all_downloads:
                            self._all_downloads[gid]["status"] = "active"
                        if gid in q.downloads_info:
                            q.downloads_info[gid]["status"] = "active"
                        print(f"✅ Resumed: {gid}")
                    else:
                        print(f"❌ Failed to resume: {gid}")
                elif real_status in ["active"]:
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = real_status
                    if gid in q.downloads_info:
                        q.downloads_info[gid]["status"] = real_status
                    resumed += 1
                    print(f"⏩ Already active: {gid}")
                else:
                    print(f"⚠️ Unknown status for {gid}: {real_status}")

        self.store.save()
        self._refresh_table()
        self._update_queue_status()
        self._update_queue_buttons()
        self._update_shutdown_button_state()
        self._apply_queue_speed_limit(q)

        if resumed > 0:
            self.tray.showMessage(
                "FelfelDM",
                f"▶️ Resumed {resumed} download(s)",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
        elif len(q.downloads) > 0:
            statuses = []
            for gid in q.downloads:
                if gid in self._all_downloads:
                    statuses.append(self._all_downloads[gid].get("status", "unknown"))
            self.tray.showMessage(
                "FelfelDM",
                f"⏳ No downloads to resume. Statuses: {', '.join(set(statuses))}",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

    def _pause_current_queue(self) -> None:
        q = self._current_queue()
        if not q or q.name == "__direct__":
            return

        if q.schedule_enabled:
            q.schedule_enabled = False
            q.manually_paused = True
            print(f"⏰ Schedule disabled for '{q.name}' due to manual pause")

            self.tray.showMessage(
                "FelfelDM",
                f"⏸️ Queue '{q.name}' paused manually.\n⏰ Schedule has been disabled.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

        q.paused = True
        q.manually_paused = True
        self.store.save()

        paused = 0
        for gid in q.downloads:
            download_type = "normal"
            if gid in self._all_downloads:
                download_type = self._all_downloads[gid].get("download_type", "normal")

            if download_type == "youtube":
                if gid in self._all_downloads:
                    status = self._all_downloads[gid].get("status", "")
                    if status in ["downloading", "pending"]:
                        self._pause_youtube_download(gid)
                        paused += 1
                        self._all_downloads[gid]["status"] = "paused"
                        self._all_downloads[gid]["downloadSpeed"] = 0
            else:
                if gid in self._all_downloads:
                    real_status = self._all_downloads[gid].get("status", "")
                else:
                    real_status = ""

                if real_status in ["active", "waiting"]:
                    self.aria2.pause(gid)
                    paused += 1

                if gid in self._all_downloads:
                    self._all_downloads[gid]["status"] = "paused"
                    self._all_downloads[gid]["downloadSpeed"] = 0
                if gid in q.downloads_info:
                    q.downloads_info[gid]["status"] = "paused"

        self._last_calculated_global_speed = 0
        self.speed_status_label.setText("0 B/s")
        self.tray.setToolTip("FelfelDM — ⬇ 0 B/s")

        self.store.save()
        self._refresh_table()
        self._refresh_queue_list()
        self._update_queue_status()
        self._update_queue_buttons()
        self._update_shutdown_button_state()

        if paused > 0:
            self.tray.showMessage(
                "FelfelDM",
                f"⏸️ Paused {paused} download(s)",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
        else:
            self.tray.showMessage(
                "FelfelDM",
                "Queue paused (no active downloads)",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    def _clear_completed_downloads(self) -> None:
        q = self._current_queue()
        if not q:
            return

        completed_gids = [
            gid
            for gid in q.downloads
            if gid in self._all_downloads
            and self._all_downloads[gid].get("status", "")
            in ["complete", "completed", "✅ Complete"]
        ]

        if not completed_gids:
            QMessageBox.information(self, "Info", "No completed downloads to clear.")
            return

        reply = QMessageBox.question(
            self,
            "Clear Completed",
            f"Remove {len(completed_gids)} completed download(s) from queue and aria2?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.No:
            return

        removed = 0
        for gid in completed_gids:
            download_type = self._all_downloads.get(gid, {}).get(
                "download_type", "normal"
            )

            if download_type == "youtube":
                self.store.delete_youtube_download(gid)
                if gid in self._all_downloads:
                    del self._all_downloads[gid]
                if gid in q.downloads:
                    q.downloads.remove(gid)
                if gid in q.downloads_info:
                    del q.downloads_info[gid]
                removed += 1
                print(f"🗑️ Removed completed YouTube download: {gid}")
            else:
                try:
                    self.aria2.remove(gid)
                    print(f"🗑 Removed GID {gid} from aria2")
                except Exception as e:
                    print(f"⚠ Could not remove GID {gid} from aria2: {e}")

                if gid in q.downloads:
                    q.downloads.remove(gid)
                if gid in self._all_downloads:
                    del self._all_downloads[gid]
                self._cleared_gids.add(gid)
                removed += 1

        self.store.save()
        self._refresh_queue_list()
        self._refresh_table()
        self._update_progress_bar()
        self._update_shutdown_button_state()

        self.tray.showMessage(
            "FelfelDM",
            f"Removed {removed} completed download(s)",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _update_progress_bar(self) -> None:
        q = self._current_queue()
        total_size = 0
        completed_size = 0

        if not q or q.name == "__direct__":
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Direct Downloads — no queue")
            return

        for gid in q.downloads:
            if gid in self._all_downloads:
                row = self._all_downloads[gid]
                total_size += int(row.get("totalLength", 0))
                completed_size += int(row.get("completedLength", 0))

        speed_texts = []
        global_limit = self.store.settings.get("speed_limit", 0)
        if global_limit > 0:
            speed_texts.append(
                f"Global: {global_limit//1024} MB/s"
                if global_limit >= 1024
                else f"Global: {global_limit} KB/s"
            )

        if q and getattr(q, "speed_limit", 0) > 0:
            q_limit = q.speed_limit
            speed_texts.append(
                f"Queue: {q_limit//1024} MB/s"
                if q_limit >= 1024
                else f"Queue: {q_limit} KB/s"
            )

        speed_part = " | " + " | ".join(speed_texts) if speed_texts else ""

        if total_size > 0:
            progress = int((completed_size / total_size) * 100)
            self.progress_bar.setValue(min(progress, 100))
            self.progress_bar.setFormat(
                f"{format_size(completed_size)} / {format_size(total_size)} ({progress}%){speed_part}"
            )
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat(f"No active downloads{speed_part}")

    def _add_queue(self) -> None:
        name, ok = QInputDialog.getText(self, "New Queue", "Queue name:")
        if ok and name.strip():
            if name.strip() == "Default":
                QMessageBox.warning(self, "Error", "Queue name 'Default' is reserved.")
                return
            new_queue = Queue(name.strip(), paused=True, proxy_config=None)
            self.store.queues.append(new_queue)
            self.store.save()
            self._refresh_queue_list()
            self._update_queue_buttons()

    def _edit_queue(self) -> None:
        q = self._current_queue()
        if not q:
            return
        if q.name == "__direct__":
            QMessageBox.information(
                self, "Info", "Quick Downloads queue has no settings."
            )
            return

        dlg = QueueSettingsDialog(q, self)
        if dlg.exec():
            d = dlg.get_queue_data()
            q.name = d["name"]
            q.save_path = d["save_path"]
            q.max_concurrent = d["max_concurrent"]
            self.store.settings["max_concurrent"] = d["max_concurrent"]
            q.schedule_enabled = d["schedule_enabled"]
            q.schedule_start = d["schedule_start"]
            q.schedule_end = d["schedule_end"]
            q.days = d["days"]
            q.speed_limit = d.get("speed_limit", 0)
            q.proxy_config = d.get("proxy_config")
            q.manually_paused = False

            if q.proxy_config:
                self.proxy_manager.set_queue_proxy(q.name, q.proxy_config)
            else:
                self.proxy_manager.remove_queue_proxy(q.name)

            self.store.save()
            self._refresh_queue_list()
            self._update_queue_buttons()
            self._apply_settings_to_aria2()
            self._apply_queue_speed_limit(q)

    def _delete_queue(self) -> None:
        q = self._current_queue()
        if not q or len(self.store.queues) <= 1:
            QMessageBox.warning(self, "Error", "Cannot delete the last queue.")
            return

        if (
            QMessageBox.question(self, "Delete", f"Delete queue '{q.name}'?")
            == QMessageBox.StandardButton.Yes
        ):
            self.store.queues.pop(self._current_queue_idx)
            self._current_queue_idx = 0
            self.store.save()
            self._refresh_queue_list()
            self._update_queue_buttons()

    @pyqtSlot(list)
    def _add_downloads_from_extension(self, urls: List[str]) -> None:
        if not urls:
            return

        if len(urls) == 1:
            self._add_single_url_from_extension(urls[0])
        else:
            self._add_multiple_urls_from_extension(urls)

    def _add_single_url_from_extension(self, url: str) -> None:
        all_queues = self.store.queues
        dlg = QuickDownloadDialog(all_queues, self)
        dlg.url_edit.setPlainText(url)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)

        if dlg.exec():
            d = dlg.get_data()
            if not d["urls"]:
                return

            queue_name = d.get("queue_name", "__direct__")
            target_queue = self._get_or_create_queue(queue_name)

            options = {
                "dir": d["path"],
                "split": str(d["connections"]),
                "max-connection-per-server": str(d["connections"]),
                "min-split-size": "1M",
                "continue": "true",
                "always-resume": "true",
                "header": [
                    "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
                ],
            }

            added_gids = []
            for url in d["urls"]:
                options_with_pause = options.copy()
                options_with_pause["pause"] = "true"
                gid = self.aria2.add_url(url, options_with_pause)

                if gid:
                    target_queue.downloads.append(gid)
                    clean_name = self._extract_filename(url)
                    full_path = os.path.join(d["path"], clean_name)

                    target_queue.downloads_info[gid] = {
                        "url": url,
                        "name": clean_name,
                        "totalLength": 0,
                        "completedLength": 0,
                        "status": "waiting",
                        "files": [
                            {
                                "path": full_path,
                                "length": "0",
                                "completedLength": "0",
                                "selected": "true",
                                "uris": [],
                            }
                        ],
                        "category": "📁 Other",
                    }

                    self._all_downloads[gid] = {
                        "gid": gid,
                        "name": clean_name,
                        "status": "waiting",
                        "totalLength": 0,
                        "completedLength": 0,
                        "downloadSpeed": 0,
                        "connections": 0,
                        "files": [{"path": full_path}],
                        "errorMessage": "",
                        "category": "📁 Other",
                        "size_fetch_attempts": 0,
                    }

                    if queue_name == "__direct__":
                        self.aria2.resume(gid)
                        if gid in self._all_downloads:
                            self._all_downloads[gid]["status"] = "active"
                    else:
                        if gid in self._all_downloads:
                            self._all_downloads[gid]["status"] = "paused"
                            self._all_downloads[gid]["downloadSpeed"] = 0

                    added_gids.append(gid)

            self.store.save()
            self._refresh_queue_list()
            self._refresh_table()
            self._update_shutdown_button_state()

            if len(added_gids) == 1 and queue_name == "__direct__":
                QTimer.singleShot(
                    500, lambda: self._open_progress_dialog(added_gids[0])
                )

    def _add_multiple_urls_from_extension(self, urls: List[str]) -> None:
        visible_queues = [q for q in self.store.queues if q.name != "__direct__"]
        default_idx = next(
            (i for i, q in enumerate(visible_queues) if q.name == "Default"), 0
        )

        dlg = AddDownloadDialog(visible_queues, default_idx, self)
        dlg.url_edit.setPlainText("\n".join(urls))

        if dlg.exec():
            d = dlg.get_data()
            if not d["urls"]:
                return

            queue_index = d["queue"]
            if queue_index < 0 or queue_index >= len(visible_queues):
                QMessageBox.warning(self, "Error", "Selected queue does not exist.")
                return

            q = visible_queues[queue_index]
            self._apply_settings_to_aria2()

            options = {
                "dir": d["path"],
                "split": str(d["connections"]),
                "max-connection-per-server": str(d["connections"]),
                "min-split-size": "1M",
                "stream-piece-selector": "geom",
                "continue": "true",
                "always-resume": "true",
                "header": [
                    "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
                ],
            }

            added = 0
            new_gids = []

            for url in d["urls"]:
                options_with_pause = options.copy()
                options_with_pause["pause"] = "true"
                gid = self.aria2.add_url(url, options_with_pause)

                if gid:
                    if gid in self._cleared_gids:
                        self._cleared_gids.remove(gid)
                    q.downloads.append(gid)

                    clean_name = self._extract_filename(url)
                    full_path = os.path.join(d["path"], clean_name)

                    q.downloads_info[gid] = {
                        "url": url,
                        "name": clean_name,
                        "totalLength": 0,
                        "completedLength": 0,
                        "status": "waiting",
                        "files": [
                            {
                                "path": full_path,
                                "length": "0",
                                "completedLength": "0",
                                "selected": "true",
                                "uris": [],
                            }
                        ],
                        "category": "📁 Other",
                    }

                    new_gids.append(gid)
                    added += 1

                    self._all_downloads[gid] = {
                        "gid": gid,
                        "name": clean_name,
                        "status": "waiting",
                        "totalLength": 0,
                        "completedLength": 0,
                        "downloadSpeed": 0,
                        "connections": 0,
                        "files": [{"path": full_path}],
                        "errorMessage": "",
                        "category": "📁 Other",
                        "size_fetch_attempts": 0,
                    }

            self.store.save()
            self._refresh_queue_list()
            self._update_queue_buttons()
            self._refresh_table()

            if q.name == "__direct__":
                for gid in new_gids:
                    self.aria2.resume(gid)
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "active"
                self._refresh_table()
                self.tray.showMessage(
                    "FelfelDM",
                    f"✅ Added {added} download(s) to 'Direct Downloads' (started)",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )
            elif q and q.paused:
                for gid in new_gids:
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "paused"
                        self._all_downloads[gid]["downloadSpeed"] = 0
                self.tray.showMessage(
                    "FelfelDM",
                    f"✅ Added {added} download(s) to '{q.name}' (paused)",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )
            else:
                for gid in new_gids:
                    self.aria2.resume(gid)
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "active"
                self._refresh_table()
                self.tray.showMessage(
                    "FelfelDM",
                    f"✅ Added {added} download(s) to '{q.name}' (downloading)",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )

    def _get_or_create_queue(self, queue_name: str) -> Queue:
        for q in self.store.queues:
            if q.name == queue_name:
                return q

        target_queue = Queue(queue_name, paused=False)
        if queue_name == "__direct__":
            target_queue.max_concurrent = 99
        self.store.queues.insert(0, target_queue)
        self.store.save()
        return target_queue

    def _extract_filename(self, url: str) -> str:
        raw_name = url.split("/")[-1]
        clean_name = raw_name.split("?")[0] if "?" in raw_name else raw_name
        return clean_name if clean_name else "Unknown"

    def _add_download(self) -> None:
        visible_queues = [q for q in self.store.queues if q.name != "__direct__"]

        current_idx = 0
        current_q = self._current_queue()
        if current_q and current_q.name != "__direct__":
            for i, q in enumerate(visible_queues):
                if q.name == current_q.name:
                    current_idx = i
                    break

        dlg = AddDownloadDialog(visible_queues, current_idx, self)

        clip = QApplication.clipboard().text().strip()
        if clip:
            valid_lines = [
                line.strip()
                for line in clip.split("\n")
                if line.strip().startswith(("http", "magnet:", "ftp"))
            ]
            if valid_lines:
                dlg.url_edit.setPlainText("\n".join(valid_lines))

        if dlg.exec():
            d = dlg.get_data()
            if not d["urls"]:
                return

            queue_index = d["queue"]
            if queue_index < 0 or queue_index >= len(visible_queues):
                QMessageBox.warning(self, "Error", "Selected queue does not exist.")
                return

            q = visible_queues[queue_index]
            self._apply_settings_to_aria2()

            proxy_mode = d.get("proxy_mode", 0)
            options = {
                "dir": d["path"],
                "split": str(d["connections"]),
                "max-connection-per-server": str(d["connections"]),
                "min-split-size": "1M",
                "stream-piece-selector": "geom",
                "continue": "true",
                "always-resume": "true",
                "header": [
                    "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
                ],
            }

            if proxy_mode == 0:
                proxy = self.proxy_manager.get_proxy_for_queue(q.name)
                if proxy and proxy.is_valid():
                    options["all-proxy"] = proxy._build_proxy_url()
            elif proxy_mode == 1:
                custom_proxy = d.get("custom_proxy")
                if custom_proxy and custom_proxy.is_valid():
                    options["all-proxy"] = custom_proxy._build_proxy_url()
            elif proxy_mode == 2:
                options["all-proxy"] = ""

            added = 0
            new_gids = []

            for url in d["urls"]:

                options_with_pause = options.copy()
                options_with_pause["pause"] = "true"
                gid = self.aria2.add_url(url, options_with_pause)

                if gid:
                    if gid in self._cleared_gids:
                        self._cleared_gids.remove(gid)
                    q.downloads.append(gid)

                    clean_name = self._extract_filename(url)
                    full_path = os.path.join(d["path"], clean_name)

                    q.downloads_info[gid] = {
                        "url": url,
                        "name": clean_name,
                        "totalLength": 0,
                        "completedLength": 0,
                        "status": "waiting",
                        "files": [
                            {
                                "path": full_path,
                                "length": "0",
                                "completedLength": "0",
                                "selected": "true",
                                "uris": [],
                            }
                        ],
                        "category": "📁 Other",
                    }

                    new_gids.append(gid)
                    added += 1

                    self._all_downloads[gid] = {
                        "gid": gid,
                        "name": clean_name,
                        "status": "waiting",
                        "totalLength": 0,
                        "completedLength": 0,
                        "downloadSpeed": 0,
                        "connections": 0,
                        "files": [{"path": full_path}],
                        "errorMessage": "",
                        "category": "📁 Other",
                        "size_fetch_attempts": 0,
                    }

                    if q and getattr(q, "speed_limit", 0) > 0:
                        self.aria2.set_download_speed_limit(gid, q.speed_limit)

            self.store.save()
            self._refresh_queue_list()
            self._refresh_table()
            self._update_queue_buttons()
            self._update_shutdown_button_state()

            if q.name == "__direct__":
                for gid in new_gids:
                    self.aria2.resume(gid)
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "active"
                self._refresh_table()
                self.tray.showMessage(
                    "FelfelDM",
                    f"✅ Added {added} download(s) to 'Direct Downloads' (started)",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )
            elif q.paused:
                for gid in new_gids:
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "paused"
                        self._all_downloads[gid]["downloadSpeed"] = 0
                self.tray.showMessage(
                    "FelfelDM",
                    f"✅ Added {added} download(s) to '{q.name}' (paused)",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )
            else:
                for gid in new_gids:
                    self.aria2.resume(gid)
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "active"
                self._refresh_table()
                self.tray.showMessage(
                    "FelfelDM",
                    f"✅ Added {added} download(s) to '{q.name}' (downloading)",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )

            self._refresh_table()

    def _pause_download_with_retry(self, gid: str) -> None:
        for attempt in range(5):
            time.sleep(0.15)
            try:
                if gid in self._all_downloads:
                    real_status = self._all_downloads[gid].get("status", "")
                    if real_status != "paused":
                        result = self.aria2.pause(gid)
                        if result is not None:
                            print(
                                f"⏸️ Paused successfully after {attempt+1} attempts: {gid}"
                            )
                            break
                    else:
                        print(f"⏸️ Already paused: {gid}")
                        break
            except Exception as e:
                print(f"⚠️ Error on attempt {attempt+1} for {gid}: {e}")

        if gid in self._pending_pause:
            self._pending_pause.remove(gid)

    def _add_single_download(self) -> None:
        dlg = SingleDownloadDialog(self)
        clip = QApplication.clipboard().text().strip()
        if clip and clip.startswith(("http", "magnet:", "ftp")):
            dlg.url_edit.setText(clip)

        if dlg.exec():
            data = dlg.get_data()
            if not data["url"]:
                QMessageBox.warning(self, "Error", "URL cannot be empty.")
                return

            self._apply_settings_to_aria2()

            options = {
                "dir": data["path"],
                "split": str(data["connections"]),
                "max-connection-per-server": str(data["connections"]),
                "continue": "true",
                "always-resume": "true",
                "header": [
                    "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
                ],
            }

            proxy_mode = data.get("proxy_mode", 0)
            if proxy_mode == 0:
                proxy = self.proxy_manager.get_proxy_for_queue("Single Downloads")
                if proxy and proxy.is_valid():
                    options["all-proxy"] = proxy._build_proxy_url()
            elif proxy_mode == 1:
                custom_proxy = data.get("custom_proxy")
                if custom_proxy and custom_proxy.is_valid():
                    options["all-proxy"] = custom_proxy._build_proxy_url()

            gid = self.aria2.add_url(data["url"], options)

            if gid:
                single_queue = self._get_or_create_queue("Single Downloads")
                single_queue.downloads.append(gid)

                if data["start_immediately"]:
                    self.aria2.resume(gid)
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "active"
                else:
                    self.aria2.pause(gid)
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "paused"

                self.store.save()
                self._refresh_queue_list()
                self._refresh_table()
                self._update_queue_buttons()

                QMessageBox.information(
                    self,
                    "Success",
                    f"Download added to 'Single Downloads' queue.\n"
                    f"Status: {'Downloading' if data['start_immediately'] else 'Paused'}",
                )
            else:
                QMessageBox.warning(
                    self, "Error", "Could not add download. Is aria2 running?"
                )

    def _pause_selected(self) -> None:
        gid = self._selected_gid()
        if not gid:
            return

        if gid in self._all_downloads:
            real_status = self._all_downloads[gid].get("status", "")
        else:
            real_status = ""

        if real_status in ["active", "waiting", "downloading"]:
            self.aria2.pause(gid)
            if gid in self._all_downloads:
                self._all_downloads[gid]["status"] = "paused"
                self._all_downloads[gid]["downloadSpeed"] = 0

            q = self._current_queue()
            if q and gid in q.downloads_info:
                q.downloads_info[gid]["status"] = "paused"
                self.store.save()

            if q and q.name != "__direct__":
                has_active = any(
                    other_gid in self._all_downloads
                    and self._all_downloads[other_gid].get("status", "")
                    in ["active", "waiting"]
                    for other_gid in q.downloads
                    if other_gid != gid
                )
                if not has_active:
                    q.paused = True
                    self.store.save()
                    print(f"⏸️ Queue '{q.name}' auto-paused (no active downloads)")

            self._refresh_table()
            self._refresh_queue_list()
            self._update_queue_status()
            self._update_queue_buttons()
            self._update_toggle_button()
            self.tray.showMessage(
                "FelfelDM",
                "⏸️ Download paused",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    def _resume_selected(self) -> None:
        gid = self._selected_gid()
        if not gid:
            return

        q = self._current_queue()
        if q and q.paused and q.name != "__direct__":
            QMessageBox.warning(
                self,
                "Queue is Paused",
                f"The queue '{q.name}' is currently paused.\n\n"
                "To resume this download, you need to:\n"
                "Click the 'Start' button for this queue in the sidebar\n",
                QMessageBox.StandardButton.Ok,
            )
            return

        status_data = self.aria2.get_status(gid)
        if not status_data:

            self._re_add_download(gid)
            return

        if gid in self._all_downloads:
            real_status = self._all_downloads[gid].get("status", "")
        else:
            real_status = ""

        if real_status == "paused":
            self.aria2.resume(gid)
            if gid in self._all_downloads:
                self._all_downloads[gid]["status"] = "active"

                QTimer.singleShot(2000, lambda: self._update_download_size(gid))

            if q and gid in q.downloads_info:
                q.downloads_info[gid]["status"] = "active"
                self.store.save()

            if q and q.speed_limit > 0:
                self.aria2.set_download_speed_limit(gid, q.speed_limit)
                print(f"⚡ Queue speed limit {q.speed_limit}KB/s applied to {gid}")

            self._refresh_table()
            self._refresh_queue_list()
            self._update_queue_status()
            self._update_queue_buttons()
            self._update_toggle_button()
            self.tray.showMessage(
                "FelfelDM",
                "▶️ Download resumed",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

    def _re_add_download(self, gid: str) -> Optional[str]:
        """Re-add a download to aria2 if it was lost, returns new gid or None"""
        print(f"🔄 Re-adding download to aria2: {gid}")

        url = None
        save_path = None
        q = None

        for queue in self.store.queues:
            if gid in queue.downloads_info:
                info = queue.downloads_info[gid]
                url = info.get("url")
                save_path = queue.save_path
                q = queue
                break

        if not url or not save_path:
            print(f"❌ Cannot re-add: missing url or save_path for {gid}")
            return None

        options = {
            "dir": save_path,
            "split": "8",
            "max-connection-per-server": "8",
            "continue": "true",
            "always-resume": "true",
        }

        if q and q.speed_limit > 0:
            options["max-download-limit"] = f"{q.speed_limit}K"

        new_gid = self.aria2.add_url(url, options)

        if new_gid:
            print(f"✅ Re-added download: {new_gid}")

            for queue in self.store.queues:
                if gid in queue.downloads:
                    idx = queue.downloads.index(gid)
                    queue.downloads[idx] = new_gid
                if gid in queue.downloads_info:
                    queue.downloads_info[new_gid] = queue.downloads_info.pop(gid)

            if gid in self._all_downloads:
                self._all_downloads[new_gid] = self._all_downloads.pop(gid)
                self._all_downloads[new_gid]["gid"] = new_gid
                self._all_downloads[new_gid]["status"] = "waiting"

            self.aria2.resume(new_gid)
            if new_gid in self._all_downloads:
                self._all_downloads[new_gid]["status"] = "active"

            self.store.save()
            self._refresh_table()
            self._refresh_queue_list()
            self._update_queue_buttons()
            return new_gid
        else:
            return None

    def _remove_selected(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "Info", "No downloads selected.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Remove Downloads")
        dlg.setMinimumWidth(500)
        dlg.setModal(True)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        layout.addWidget(QLabel(f"Remove {len(selected)} download(s)?"))
        layout.addWidget(QLabel("Choose what to do with the downloaded files:"))
        layout.addSpacing(10)

        btn_layout = QHBoxLayout()
        btn_remove_only = QPushButton("Remove from List Only")
        btn_remove_files = QPushButton("Remove & Delete Files")
        btn_cancel = QPushButton("Cancel")
        btn_remove_only.setMinimumWidth(150)
        btn_remove_files.setMinimumWidth(150)
        btn_cancel.setMinimumWidth(100)
        btn_layout.addWidget(btn_remove_only)
        btn_layout.addWidget(btn_remove_files)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        result = None

        def on_remove_only():
            nonlocal result
            result = "remove_only"
            dlg.accept()

        def on_remove_files():
            nonlocal result
            result = "remove_files"
            dlg.accept()

        def on_cancel():
            nonlocal result
            result = "cancel"
            dlg.reject()

        btn_remove_only.clicked.connect(on_remove_only)
        btn_remove_files.clicked.connect(on_remove_files)
        btn_cancel.clicked.connect(on_cancel)
        btn_remove_only.setDefault(True)

        dlg.exec()

        if result == "cancel" or result is None:
            return

        delete_files = result == "remove_files"
        gids_to_remove = [
            self.model.get_gid(idx.row())
            for idx in selected
            if self.model.get_gid(idx.row())
        ]

        removed = 0

        for gid in gids_to_remove:
            # ===== First remove from aria2 =====
            try:
                self.aria2.remove(gid)
                print(f"🗑 Removed GID {gid} from aria2")
            except Exception as e:
                print(f"⚠ Could not remove GID {gid} from aria2: {e}")

            try:
                self.aria2._call("aria2.removeDownloadResult", [gid])
            except Exception:
                pass

            # ===== Remove from queues =====
            for q in self.store.queues:
                if gid in q.downloads:
                    q.downloads.remove(gid)
                if gid in q.downloads_info:
                    # Store path before deleting info
                    if delete_files:
                        info = q.downloads_info[gid]
                        save_path = q.save_path
                        name = info.get("name", "")
                        file_path = None
                        
                        # Try to get file path from info
                        files = info.get("files", [])
                        if files and files[0].get("path"):
                            file_path = files[0]["path"]
                        
                        # Fallback: construct from save_path and name
                        if not file_path and name and save_path:
                            file_path = os.path.join(save_path, name)
                        
                        # Fallback: search in save_path by GID
                        if not file_path and save_path and os.path.exists(save_path):
                            for f in os.listdir(save_path):
                                if gid in f:
                                    file_path = os.path.join(save_path, f)
                                    break
                        
                        if file_path and os.path.exists(file_path):
                            try:
                                os.remove(file_path)
                                print(f"🗑️ DELETED FILE: {file_path}")
                            except Exception as e:
                                print(f"⚠️ Could not delete file {file_path}: {e}")
                            
                            # Delete .aria2 file
                            aria2_file = file_path + ".aria2"
                            if os.path.exists(aria2_file):
                                try:
                                    os.remove(aria2_file)
                                    print(f"🗑️ DELETED .aria2: {aria2_file}")
                                except Exception as e:
                                    print(f"⚠️ Could not delete .aria2: {e}")
                    
                    del q.downloads_info[gid]

            # ===== Remove from _all_downloads =====
            if gid in self._all_downloads:
                del self._all_downloads[gid]

            removed += 1

        self.store.save()
        self._refresh_table()
        self._refresh_queue_list()
        self._update_queue_buttons()

        if removed > 0:
            msg_text = f"Removed {removed} download(s)"
            if delete_files:
                msg_text += " (files deleted)"
            self.tray.showMessage(
                "FelfelDM", msg_text, QSystemTrayIcon.MessageIcon.Information, 2000
            )
    def _delete_download_files(self, gid: str) -> None:
        file_paths = []
        save_path = None
        name = None
        aria2_temp_files = []

        print(f"🔍 [REMOVE START] GID: {gid}")

        for q in self.store.queues:
            if gid in q.downloads_info:
                info = q.downloads_info[gid]
                save_path = q.save_path
                name = info.get("name", "").strip()
                print(
                    f"✅ Found in downloads_info → save_path: {save_path} | name: {name}"
                )

                files = info.get("files", [])
                for f in files:
                    if f.get("path"):
                        file_paths.append(f["path"])
                        print(f"✅ Found file path from files: {f['path']}")
                break

        if not file_paths and gid in self._all_downloads:
            dl = self._all_downloads[gid]
            name = dl.get("name", name)
            files = dl.get("files", [])
            for f in files:
                if f.get("path"):
                    file_paths.append(f["path"])
                    print(f"✅ Found file path from _all_downloads: {f['path']}")

            if not save_path:
                for q in self.store.queues:
                    if gid in q.downloads:
                        save_path = q.save_path
                        print(f"✅ Found save_path from queue: {save_path}")
                        break

        if not save_path:
            for q in self.store.queues:
                if gid in q.downloads:
                    save_path = q.save_path
                    print(f"✅ Found save_path from queue (fallback): {save_path}")
                    break

        if not save_path or not os.path.exists(save_path):
            save_path = os.path.expanduser("~/Downloads")
            print(f"📁 Using default Downloads folder: {save_path}")

        if not name:
            for q in self.store.queues:
                if gid in q.downloads_info:
                    info = q.downloads_info[gid]
                    url = info.get("url", "")
                    if url:
                        name = url.split("/")[-1].split("?")[0]
                        print(f"✅ Extracted name from URL: {name}")
                    break

        if save_path and os.path.exists(save_path):
            print(f"🔎 Searching all files in: {save_path}")
            try:
                for file in os.listdir(save_path):
                    full_path = os.path.join(save_path, file)
                    lower = file.lower()

                    if name and name.lower() in lower:
                        if not any(
                            x in lower
                            for x in [".aria2", ".part", ".f", ".temp", ".ytdl"]
                        ):
                            file_paths.append(full_path)
                            print(f"✅ Found main file by name: {file}")

                    if gid in file:
                        if not any(
                            x in lower
                            for x in [".aria2", ".part", ".f", ".temp", ".ytdl"]
                        ):
                            file_paths.append(full_path)
                            print(f"✅ Found main file by GID: {file}")

                    if any(
                        x in lower for x in [".aria2", ".part", ".f", ".temp", ".ytdl"]
                    ):
                        aria2_temp_files.append(full_path)
                        print(f"✅ Found temp file: {file}")
            except Exception as e:
                print(f"⚠️ Dir list error: {e}")

        if not file_paths and aria2_temp_files:
            for temp_path in aria2_temp_files:
                temp_name = os.path.basename(temp_path)

                base_name = temp_name
                for ext in [".aria2", ".part", ".f", ".temp", ".ytdl"]:
                    if ext in base_name:
                        base_name = base_name.replace(ext, "")

                if base_name:
                    possible_path = os.path.join(save_path, base_name)
                    if os.path.exists(possible_path):
                        file_paths.append(possible_path)
                        print(f"✅ Found main file from temp name: {possible_path}")
                    else:
                        extensions = [
                            "",
                            ".mp4",
                            ".mkv",
                            ".webm",
                            ".mp3",
                            ".m4a",
                            ".zip",
                            ".rar",
                            ".7z",
                            ".tar.gz",
                            ".tgz",
                            ".txt",
                            ".pdf",
                            ".jpg",
                            ".png",
                        ]
                        for ext in extensions:
                            test_path = os.path.join(save_path, f"{base_name}{ext}")
                            if os.path.exists(test_path):
                                file_paths.append(test_path)
                                print(f"✅ Found main file with extension: {test_path}")
                                break

        print(f"📊 Total main files to delete: {len(set(file_paths))}")
        print(f"📊 Total temp files to delete: {len(set(aria2_temp_files))}")

        deleted_count = 0
        for path in set(file_paths):
            try:
                if os.path.exists(path):
                    if os.path.isfile(path):
                        os.remove(path)
                        deleted_count += 1
                        print(f"🗑️ DELETED FILE: {os.path.basename(path)}")
                    elif os.path.isdir(path):
                        import shutil

                        shutil.rmtree(path)
                        deleted_count += 1
                        print(f"🗑️ DELETED FOLDER: {path}")
            except Exception as e:
                print(f"⚠️ Delete failed {path}: {e}")

        for path in set(aria2_temp_files):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    print(f"🗑️ DELETED TEMP: {os.path.basename(path)}")
            except Exception as e:
                print(f"⚠️ Delete temp failed {path}: {e}")

        print(f"✅ Deleted {deleted_count} file(s)")

        if not file_paths:
            print(
                f"⚠️ No main file found for GID: {gid}, name: {name}, path: {save_path}"
            )

    def _selected_gid(self) -> Optional[str]:
        idx = self.table.currentIndex()
        return self.model.get_gid(idx.row()) if idx.isValid() else None

    def _context_menu(self, pos: QPoint) -> None:
        gid = self._selected_gid()
        if not gid:
            menu = QMenu(self)
            menu.addAction(
                "Sort by Name",
                lambda: self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder),
            )
            menu.addAction(
                "Sort by Size",
                lambda: self.table.sortByColumn(1, Qt.SortOrder.DescendingOrder),
            )
            menu.addAction(
                "Sort by Progress",
                lambda: self.table.sortByColumn(2, Qt.SortOrder.DescendingOrder),
            )
            menu.addAction(
                "Sort by Speed",
                lambda: self.table.sortByColumn(3, Qt.SortOrder.DescendingOrder),
            )
            menu.addAction(
                "Sort by Status",
                lambda: self.table.sortByColumn(5, Qt.SortOrder.AscendingOrder),
            )
            menu.addSeparator()
            menu.addAction("Clear Completed", self._clear_completed_downloads)
            menu.exec(self.table.viewport().mapToGlobal(pos))
            return

        dl_data = self._all_downloads.get(gid, {})
        download_type = dl_data.get("download_type", "normal")

        # Unified status - both branches were identical
        real_status = dl_data.get("status", "")

        menu = QMenu(self)

        if real_status in ["active", "waiting", "downloading"]:
            menu.addAction(
                get_icon("media-playback-pause"),
                "Pause",
                lambda: (
                    self._pause_youtube_download(gid)
                    if download_type == "youtube"
                    else self._pause_selected()
                ),
            )
        elif real_status == "paused":
            menu.addAction(
                get_icon("media-playback-start"),
                "Resume",
                lambda: (
                    self._resume_youtube_download(gid)
                    if download_type == "youtube"
                    else self._resume_selected()
                ),
            )

        menu.addSeparator()
        menu.addAction(
            get_icon("folder"), "Open Folder", lambda: self._open_folder(gid)
        )
        menu.addAction(get_icon("edit-copy"), "Copy URL", lambda: self._copy_link(gid))
        menu.addSeparator()
        menu.addAction(get_icon("edit-delete"), "Remove", self._remove_selected)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _open_folder(self, gid: str) -> None:
        try:
            folder_path = self._find_download_folder(gid)
            if folder_path and os.path.exists(folder_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))
            else:
                QMessageBox.warning(self, "Error", f"Folder not found:\n{folder_path}")
        except Exception as e:
            print(f"❌ [OpenFolder] Error: {e}")
            QMessageBox.warning(self, "Error", f"Could not open folder:\n{str(e)}")

    def _find_download_folder(self, gid: str) -> Optional[str]:
        if gid in self._all_downloads:
            files = self._all_downloads[gid].get("files", [])
            if files and files[0].get("path"):
                return os.path.dirname(files[0]["path"])

        for q in self.store.queues:
            if gid in q.downloads_info:
                info = q.downloads_info[gid]
                files = info.get("files", [])
                if files and files[0].get("path"):
                    return os.path.dirname(files[0]["path"])
                if q.save_path and os.path.exists(q.save_path):
                    return q.save_path

        saved_data = self.store.get_youtube_download(gid)
        if saved_data:
            folder_path = saved_data.get("save_path", "")
            if folder_path and os.path.exists(folder_path):
                return folder_path

        return os.path.expanduser("~/Downloads")

    def _copy_link(self, gid: str) -> None:
        saved_data = self.store.get_youtube_download(gid)
        if saved_data:
            QApplication.clipboard().setText(saved_data.get("url", ""))
        else:
            files = self._all_downloads.get(gid, {}).get("files", [])
            if files and files[0].get("uris"):
                QApplication.clipboard().setText(files[0]["uris"][0]["uri"])

    def _filter_downloads(self, text: str) -> None:
        q = self._current_queue()
        if not q:
            self.model.update_rows([])
            return

        if not text.strip():
            self._refresh_table()
            return

        filtered = []
        for gid in q.downloads:
            if gid in self._all_downloads:
                row = self._all_downloads[gid]
                if text.lower() in row.get("name", "").lower():
                    filtered.append(row)

        self.model.update_rows(filtered)

    def _refresh_table(self) -> None:
        q = self._current_queue()
        if not q:
            self.model.update_rows([])
            return

        rows = []
        search_text = self.search_box.text().strip().lower()

        for gid in q.downloads:
            if gid in self._all_downloads:
                row = self._all_downloads[gid].copy()
            else:
                info = q.downloads_info.get(gid, {})
                row = {
                    "gid": gid,
                    "name": info.get("name", "Unknown"),
                    "status": info.get("status", "unknown"),
                    "progress": 0,
                    "downloadSpeed": 0,
                    "totalLength": info.get("totalLength", 0),
                    "completedLength": info.get("completedLength", 0),
                    "category": info.get("category", "📁 Other"),
                    "download_type": info.get("download_type", "normal"),
                    "files": info.get("files", []),
                    "size_fetch_attempts": 0,
                    "error_count": 0,
                }
                self._all_downloads[gid] = row.copy()

            if search_text and search_text not in row.get("name", "").lower():
                continue

            rows.append(row)

        self.model.update_rows(rows)

    def _update_toggle_button(self) -> None:
        if not hasattr(self, "table") or not self.table.selectionModel():
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
            self.btn_move_queue.setEnabled(False)
            return

        selected_indexes = self.table.selectionModel().selectedRows()
        if not selected_indexes:
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
            self.btn_move_queue.setEnabled(False)
            return

        idx = selected_indexes[0]
        if not idx.isValid():
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
            self.btn_move_queue.setEnabled(False)
            return

        self.btn_move_queue.setEnabled(True)

        gid = self.model.get_gid(idx.row())
        if not gid:
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
            return

        download_type = self._all_downloads.get(gid, {}).get("download_type", "normal")

        # Unified status - both branches were identical
        real_status = self._all_downloads.get(gid, {}).get("status", "")

        if not real_status:
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
            return

        if real_status in ["active", "waiting", "downloading"]:
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
        elif real_status == "paused":
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Resume")
            self.btn_toggle.setIcon(get_icon("media-playback-start"))
        else:
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))

    def _toggle_shutdown(self, checked: bool) -> None:
        self.store.settings["shutdown_after_finish"] = checked
        self.store.save()

        if not checked and self._shutdown_dialog:
            self._shutdown_dialog.reject()
            self._shutdown_dialog = None
            self._shutdown_dialog_shown = False
            if hasattr(self, "_shutdown_timer") and self._shutdown_timer:
                self._shutdown_timer.stop()
                self._shutdown_timer = None
            self.tray.showMessage(
                "FelfelDM",
                "✅ Shutdown cancelled.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
        elif checked:
            self.tray.showMessage(
                "FelfelDM",
                "🛑 Shutdown will trigger when all downloads complete.",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
            # Immediately check if all downloads are already complete
            self._check_already_complete()

    def _check_already_complete(self) -> None:
        """Check if all downloads are already complete when shutdown is enabled"""
        if not self.shutdown_cb.isChecked():
            return
        
        if self._shutdown_dialog_shown:
            return
        
        # Check aria2 active downloads
        try:
            stat = self.aria2.get_global_stat() or {}
            total_active = int(stat.get("numActive", 0))
            total_waiting = int(stat.get("numWaiting", 0))
            
            if total_active > 0 or total_waiting > 0:
                return
        except:
            pass
        
        # Check internal state
        has_active = False
        for q in self.store.queues:
            for gid in q.downloads:
                if gid in self._all_downloads:
                    status = self._all_downloads[gid].get("status", "")
                    if status in ["active", "waiting", "downloading"]:
                        has_active = True
                        break
            if has_active:
                break
        
        if has_active:
            return
        
        # Check if any downloads exist and all are complete
        has_any = False
        all_complete = True
        for q in self.store.queues:
            if q.downloads:
                has_any = True
                for gid in q.downloads:
                    if gid in self._all_downloads:
                        status = self._all_downloads[gid].get("status", "")
                        if status not in ["complete", "completed", "error", "removed"]:
                            all_complete = False
                            break
                    else:
                        all_complete = False
                        break
                if not all_complete:
                    break
        
        if has_any and all_complete and not self._shutdown_dialog_shown:
            self._shutdown_dialog_shown = True
            self.tray.showMessage(
                "🌶️ FelfelDM",
                "✅ All downloads completed!\n🛑 System will shut down in 20 seconds.",
                QSystemTrayIcon.MessageIcon.Information,
                5000,
            )
            self._show_shutdown_countdown()

    def _apply_global_speed_limit(self) -> None:
        limit = self.store.settings.get("speed_limit", 0)
        aria_limit = f"{limit}K" if limit > 0 else "0"
        self.aria2.change_global_option({"max-overall-download-limit": aria_limit})

    def _apply_settings_to_aria2(self) -> bool:
        try:
            max_concurrent = self.store.settings.get("max_concurrent", 5)
            max_tries = self.store.settings.get("max_tries", 0)
            self.aria2.change_global_option(
                {
                    "max-concurrent-downloads": str(max_concurrent),
                    "max-tries": str(max_tries),
                }
            )
            return True
        except Exception:
            return False

    def _restart_aria2(self) -> None:
        try:
            subprocess.run(["pkill", "-f", "aria2c"], capture_output=True)
            time.sleep(0.5)
        except Exception:
            pass

        self.aria2 = Aria2RPC(
            self.store.settings["aria2_host"],
            self.store.settings["aria2_port"],
            self.store.settings["aria2_secret"],
        )

        self._start_aria2_if_needed()
        self._apply_global_speed_limit()

        QMessageBox.information(
            self, "aria2 Restarted", "aria2 has been restarted with new settings."
        )

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.store.settings, self)
        if dlg.exec():
            s = dlg.get_settings()
            self.store.settings.update(s)
            self.store.save()

            theme = self.store.settings.get("theme", "auto")
            setup_style(QApplication.instance(), theme)

            if not self._apply_settings_to_aria2():
                self._restart_aria2()
            else:
                self.tray.showMessage(
                    "FelfelDM",
                    "Settings applied successfully",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )

            self._refresh_table()

    def _start_backend(self) -> None:
        print("🚀🚀🚀 _start_backend CALLED")

        if not self.aria2.is_connected():
            max_concurrent = self.store.settings.get("max_concurrent", 5)
            max_tries = self.store.settings.get("max_tries", 5)

            if not self.aria2.start_aria2(max_concurrent, max_tries):
                print("⚠️ Failed to start aria2 with session management")

        self.worker = BackendWorker(self.aria2, self.store)
        print("🚀🚀🚀 worker created")

        self.worker.stats_updated.connect(self._on_stats_received)
        self.worker.aria2_error.connect(self._on_aria2_error)
        self.worker.size_fetched.connect(self._on_size_fetched)

        self.worker.youtube_progress.connect(self._on_youtube_progress)
        self.worker.youtube_status.connect(self._on_youtube_status)
        self.worker.youtube_speed.connect(self._on_youtube_speed)
        self.worker.youtube_finished.connect(self._on_youtube_finished)
        self.worker.youtube_size_fetched.connect(self._on_youtube_size_fetched)

        print("🚀🚀🚀 signals connected")
        self.worker.start()
        print("🚀🚀🚀 worker.start() called")

    def _on_stats_received(self, result: Dict[str, Any]) -> None:
        if not isinstance(result, dict):
            print(f"⚠️ [Stats] Invalid result type: {type(result)}")
            return

        if not result.get("connected"):
            self.status_lbl.setText("● Disconnected")
            self.status_lbl.setStyleSheet("color: #e74c3c; font-weight: bold;")

            if hasattr(self, "speed_status_label"):
                self.speed_status_label.setText("0 B/s")
            if hasattr(self, "speed_icon_label"):
                self.speed_icon_label.setPixmap(
                    get_icon("media-playback-pause").pixmap(16, 16)
                )

            self._last_calculated_global_speed = 0
            return

        self.status_lbl.setText("● Connected")
        self.status_lbl.setStyleSheet("color: #27ae60; font-weight: bold;")
        stat = result.get("stat", {})

        self._apply_settings_to_aria2()

        if self.store.settings.get("auto_clear_completed", False):
            q = self._current_queue()
            if q:
                completed_gids = [
                    gid
                    for gid in q.downloads
                    if gid in self._all_downloads
                    and self._all_downloads[gid].get("status") == "complete"
                ]
                if completed_gids:
                    for gid in completed_gids:
                        q.downloads.remove(gid)
                        if gid in self._all_downloads:
                            del self._all_downloads[gid]
                    self._refresh_queue_list()

        self._update_progress_bar()

        if self.shutdown_cb.isChecked():
            total_active = int(stat.get("numActive", 0))
            total_waiting = int(stat.get("numWaiting", 0))

            if total_active == 0 and total_waiting == 0:
                has_any_download = any(q.downloads for q in self.store.queues)
                if has_any_download and not self._shutdown_dialog_shown:
                    self._shutdown_dialog_shown = True
                    self.tray.showMessage(
                        "🌶️ FelfelDM",
                        "✅ All downloads completed!\n🛑 System will shut down in 20 seconds.",
                        QSystemTrayIcon.MessageIcon.Information,
                        5000,
                    )
                    self._show_shutdown_countdown()

        downloads_list = result.get("downloads", [])

        backup_sizes = {}
        for gid, data in self._all_downloads.items():
            total = self._to_int(data.get("totalLength", 0))
            if total > 0:
                backup_sizes[gid] = {
                    "totalLength": total,
                    "completedLength": self._to_int(data.get("completedLength", 0)),
                }

        for dl in downloads_list:
            if not isinstance(dl, dict):
                continue
            gid = dl.get("gid")
            if not gid:
                continue

            dl_total = self._to_int(dl.get("totalLength", 0))
            dl_completed = self._to_int(dl.get("completedLength", 0))

            if gid in self._all_downloads:

                if dl_total == 0:

                    if gid in backup_sizes and backup_sizes[gid]["totalLength"] > 0:
                        dl["totalLength"] = backup_sizes[gid]["totalLength"]
                        dl["completedLength"] = backup_sizes[gid]["completedLength"]
                    else:

                        stored_total = 0
                        stored_completed = 0
                        for q in self.store.queues:
                            if gid in q.downloads_info:
                                stored_total = self._to_int(
                                    q.downloads_info[gid].get("totalLength", 0)
                                )
                                stored_completed = self._to_int(
                                    q.downloads_info[gid].get("completedLength", 0)
                                )
                                if stored_total > 0:
                                    break

                        if stored_total > 0:
                            dl["totalLength"] = stored_total
                            dl["completedLength"] = stored_completed

                self._all_downloads[gid].update(dl)
            else:

                self._all_downloads[gid] = dl

        current_gids = {dl.get("gid") for dl in downloads_list if dl.get("gid")}
        for gid in list(self._all_downloads.keys()):

            if self._all_downloads[gid].get("download_type") == "youtube":
                continue

            in_queue = any(gid in q.downloads for q in self.store.queues)
            if not in_queue and gid not in current_gids:
                del self._all_downloads[gid]

        for q in self.store.queues:
            for gid in q.downloads:
                if gid in self._all_downloads:
                    dl = self._all_downloads[gid]
                    if gid not in q.downloads_info:
                        q.downloads_info[gid] = {}
                    q.downloads_info[gid].update(
                        {
                            "totalLength": self._to_int(dl.get("totalLength", 0)),
                            "completedLength": self._to_int(
                                dl.get("completedLength", 0)
                            ),
                            "status": dl.get("status", "unknown"),
                            "name": dl.get("name", "Unknown"),
                            "files": dl.get("files", []),
                            "category": dl.get("category", "📁 Other"),
                            "error_count": self._to_int(dl.get("error_count", 0)),
                            "errorMessage": dl.get("errorMessage", ""),
                        }
                    )

        self.store.save()

        # Use max_tries from settings (not max_retries)
        max_retries = self.store.settings.get("max_tries", 5)
        for gid, data in self._all_downloads.items():
            if data.get("download_type") == "youtube":
                continue
            status = data.get("status", "")
            error_msg = data.get("errorMessage", "")
            if status in ["error", "stopped"] and error_msg:
                error_count = self._to_int(data.get("error_count", 0))
                if error_count < max_retries:
                    print(
                        f"🔄 [Retry] Retrying: {gid} (attempt {error_count + 1}/{max_retries})"
                    )
                    data["error_count"] = error_count + 1
                    data["status"] = "retrying"
                    self.aria2.resume(gid)
                else:
                    print(f"❌ [Retry] Max retries reached for: {gid}")
                    data["status"] = "error"

        for q in self.store.queues:
            if not q.paused and q.downloads:
                if all(
                    gid in self._all_downloads
                    and self._all_downloads[gid].get("status", "")
                    in ["complete", "error", "removed"]
                    for gid in q.downloads
                ):
                    q.paused = True
                    self.tray.showMessage(
                        "FelfelDM",
                        f"✅ Queue '{q.name}' finished!",
                        QSystemTrayIcon.MessageIcon.Information,
                        4000,
                    )
                    self.store.save()

        self._manage_schedules()
        self._update_progress_dialog()
        self._update_youtube_dialogs(result)
        self._refresh_table()
        self._update_queue_status()
        self._refresh_queue_list()
        self._update_queue_buttons()
        self._update_shutdown_button_state()
        self._update_toggle_button()

    def _update_speed_display(self):
        """Update speed with moving average (like IDM)"""
        now = time.time()

        self._last_speed_update = now

        total_speed = 0
        for gid, dl in self._all_downloads.items():
            if dl.get("status") == "active":
                try:
                    speed = int(dl.get("downloadSpeed", 0))
                    total_speed += speed
                except (ValueError, TypeError):
                    pass

        self._speed_samples.append(total_speed)
        if len(self._speed_samples) > self._max_samples:
            self._speed_samples.pop(0)

        if self._speed_samples:
            sorted_samples = sorted(self._speed_samples)
            trim_count = max(1, len(sorted_samples) // 5)
            trimmed = (
                sorted_samples[trim_count:-trim_count]
                if len(sorted_samples) > trim_count * 2
                else sorted_samples
            )

            if trimmed:
                avg_speed = sum(trimmed) // len(trimmed)
            else:
                avg_speed = sum(sorted_samples) // len(sorted_samples)
        else:
            avg_speed = total_speed

        if self._smooth_speed == 0:
            self._smooth_speed = avg_speed
        else:
            self._smooth_speed = int(self._smooth_speed * 0.7 + avg_speed * 0.3)

        speed_text = format_speed(self._smooth_speed)

        if hasattr(self, "speed_status_label"):
            self.speed_status_label.setText(speed_text)

        if hasattr(self, "speed_icon_label"):
            if self._smooth_speed > 0:
                self.speed_icon_label.setPixmap(get_icon("go-down").pixmap(16, 16))
            else:
                self.speed_icon_label.setPixmap(
                    get_icon("media-playback-pause").pixmap(16, 16)
                )

        self.tray.setToolTip(f"FelfelDM — ⬇ {speed_text}")

    def _manage_schedules(self) -> None:
        for q in self.store.queues:
            if not q.schedule_enabled:
                continue

            is_scheduled_time = q.is_scheduled_now()
            manually_paused = getattr(q, "manually_paused", False)

            if is_scheduled_time:

                if q.paused and not manually_paused:
                    print(f"🕐 [Schedule] Starting queue: {q.name}")
                    q.paused = False
                    q.manually_paused = False
                    self.store.save()
                    self._refresh_queue_list()

                    resumed_count = 0
                    for gid in q.downloads:
                        download_type = self._all_downloads.get(gid, {}).get(
                            "download_type", "normal"
                        )
                        if download_type == "youtube":
                            if (
                                self._all_downloads.get(gid, {}).get("status")
                                == "paused"
                            ):
                                self._start_youtube_download(gid)
                                self._all_downloads[gid]["status"] = "downloading"
                                if gid in q.downloads_info:
                                    q.downloads_info[gid]["status"] = "downloading"
                                resumed_count += 1
                        else:
                            if gid in self._all_downloads:
                                real_status = self._all_downloads[gid].get("status", "")
                                if real_status == "paused":
                                    if self.aria2.resume(gid) is not None:
                                        resumed_count += 1
                                        self._all_downloads[gid]["status"] = "active"
                                        if gid in q.downloads_info:
                                            q.downloads_info[gid]["status"] = "active"
                                        print(f"🕐 [Schedule] Resumed: {gid}")

                    if resumed_count > 0:
                        self.tray.showMessage(
                            "FelfelDM",
                            f"🕐 Scheduled queue '{q.name}' started automatically! ({resumed_count} downloads)",
                            QSystemTrayIcon.MessageIcon.Information,
                            3000,
                        )

                    self._refresh_table()
                    self._update_queue_status()
                    self._update_queue_buttons()
                else:

                    for gid in q.downloads:
                        download_type = self._all_downloads.get(gid, {}).get(
                            "download_type", "normal"
                        )
                        if download_type != "youtube":
                            if gid in self._all_downloads:
                                status = self._all_downloads[gid].get("status", "")
                                if status == "paused":
                                    self.aria2.resume(gid)
                                    self._all_downloads[gid]["status"] = "active"
                                    print(
                                        f"🕐 [Schedule] Resumed paused download: {gid}"
                                    )
            else:

                if not q.paused:
                    print(f"🕐 [Schedule] Stopping queue: {q.name}")
                    q.paused = True
                    q.manually_paused = False
                    self.store.save()
                    self._refresh_queue_list()

                    paused_count = 0
                    for gid in q.downloads:
                        download_type = self._all_downloads.get(gid, {}).get(
                            "download_type", "normal"
                        )

                        real_status = None
                        if download_type != "youtube":
                            status_data = self.aria2.get_status(gid)
                            if status_data and isinstance(status_data, dict):
                                real_status = status_data.get("status", "")

                        if download_type == "youtube":
                            if gid in self._all_downloads:
                                current_status = self._all_downloads[gid].get(
                                    "status", ""
                                )
                                if current_status in [
                                    "downloading",
                                    "active",
                                    "waiting",
                                ]:
                                    self._pause_youtube_download(gid)
                                    self._all_downloads[gid]["status"] = "paused"
                                    paused_count += 1
                                    print(f"🕐 [Schedule] Paused YouTube: {gid}")
                        else:

                            if real_status in ["active", "waiting"]:
                                result = self.aria2.pause(gid)
                                if result is not None:
                                    paused_count += 1
                                    self._all_downloads[gid]["status"] = "paused"
                                    self._all_downloads[gid]["downloadSpeed"] = 0
                                    if gid in q.downloads_info:
                                        q.downloads_info[gid]["status"] = "paused"
                                    print(f"🕐 [Schedule] Paused: {gid}")
                                else:
                                    print(f"⚠️ [Schedule] Failed to pause: {gid}")
                            elif real_status:
                                print(
                                    f"ℹ️ [Schedule] Download {gid} status: {real_status} (not paused)"
                                )
                            else:

                                if gid in self._all_downloads:
                                    current_status = self._all_downloads[gid].get(
                                        "status", ""
                                    )
                                    if current_status in ["active", "waiting"]:
                                        result = self.aria2.pause(gid)
                                        if result is not None:
                                            paused_count += 1
                                            self._all_downloads[gid][
                                                "status"
                                            ] = "paused"
                                            self._all_downloads[gid][
                                                "downloadSpeed"
                                            ] = 0
                                            print(
                                                f"🕐 [Schedule] Paused (fallback): {gid}"
                                            )

                    if paused_count > 0:
                        next_time = q.get_next_schedule_time()
                        if next_time:
                            self.tray.showMessage(
                                "FelfelDM",
                                f"⏰ Schedule ended for '{q.name}'. Paused {paused_count} download(s).\nNext schedule at {next_time.strftime('%H:%M')}.",
                                QSystemTrayIcon.MessageIcon.Information,
                                3000,
                            )
                        else:
                            self.tray.showMessage(
                                "FelfelDM",
                                f"⏰ Schedule ended for '{q.name}'. Paused {paused_count} download(s).",
                                QSystemTrayIcon.MessageIcon.Information,
                                3000,
                            )
                    else:
                        print(f"ℹ️ [Schedule] No active downloads to pause in {q.name}")

                    self._refresh_table()
                    self._update_queue_status()
                    self._update_queue_buttons()

    def _update_progress_dialog(self) -> None:
        try:
            if self._progress_dialog is not None:
                dialog = self._progress_dialog
                if dialog.isVisible():
                    gid = dialog.gid
                    if gid in self._all_downloads:
                        status = self._all_downloads[gid].get("status", "")
                        if status != "waiting":
                            dialog.update_data(self._all_downloads[gid])
                        else:
                            pass
        except Exception as e:
            print(f"Progress dialog update error: {e}")
            self._progress_dialog = None

    def _update_youtube_dialogs(self, result: Dict[str, Any]) -> None:
        youtube_downloads = result.get("youtube_downloads", [])
        if not isinstance(youtube_downloads, list):
            youtube_downloads = []

        for yt_data in youtube_downloads:
            if not isinstance(yt_data, dict):
                continue

            yt_id = yt_data.get("id")
            if not yt_id:
                continue

            saved_data = self.store.get_youtube_download(yt_id)
            status = yt_data.get("status", "pending")
            progress = yt_data.get("progress", 0)
            speed = yt_data.get("speed", "")
            eta = yt_data.get("eta", "")
            total_size = yt_data.get("total_size", 0)
            title = yt_data.get("title", "Unknown")

            if saved_data:
                title = saved_data.get("yt_options", {}).get("title", title)

            completed = int(total_size * progress / 100) if total_size > 0 else 0

            if yt_id in self._all_downloads:
                self._all_downloads[yt_id].update(
                    {
                        "name": title,
                        "status": status,
                        "progress": progress,
                        "speed": speed,
                        "eta": eta,
                        "totalLength": total_size,
                        "completedLength": completed,
                        "downloadSpeed": self._parse_speed(speed),
                        "download_type": "youtube",
                        "category": "🎬 YouTube",
                        "files": (
                            [{"path": saved_data.get("full_path", "")}]
                            if saved_data
                            else []
                        ),
                        "yt_options": (
                            saved_data.get("yt_options", {}) if saved_data else {}
                        ),
                    }
                )
            else:
                self._all_downloads[yt_id] = {
                    "gid": yt_id,
                    "name": title,
                    "status": status,
                    "progress": progress,
                    "speed": speed,
                    "eta": eta,
                    "totalLength": total_size,
                    "completedLength": completed,
                    "downloadSpeed": self._parse_speed(speed),
                    "connections": 0,
                    "files": (
                        [{"path": saved_data.get("full_path", "")}]
                        if saved_data
                        else []
                    ),
                    "errorMessage": "",
                    "category": "🎬 YouTube",
                    "download_type": "youtube",
                    "yt_options": (
                        saved_data.get("yt_options", {}) if saved_data else {}
                    ),
                }

            if saved_data and saved_data.get("status") != status:
                self.store.update_youtube_status(yt_id, status)

    def _start_aria2_if_needed(self) -> None:
        if self.aria2.is_connected():
            return
        try:
            port = self.store.settings["aria2_port"]
            max_tries = self.store.settings.get("max_tries", 5)
            max_concurrent = self.store.settings.get("max_concurrent", 5)

            session_file = os.path.join(
                os.path.expanduser("~/.config/felfelDM"), "aria2.session"
            )
            os.makedirs(os.path.dirname(session_file), exist_ok=True)
            if not os.path.exists(session_file):
                open(session_file, "w").close()

            cmd = [
                "aria2c",
                "--enable-rpc",
                "--rpc-listen-all",
                "--rpc-allow-origin-all",
                "--daemon",
                f"--rpc-listen-port={port}",
                f"--max-concurrent-downloads={max_concurrent}",
                f"--max-tries={max_tries}",
                "--max-connection-per-server=16",
                "--split=16",
                "--continue=true",
                "--always-resume=true",
                "--retry-wait=2",
                f"--save-session={session_file}",
                f"--input-file={session_file}",
                "--save-session-interval=60",
            ]

            if self.aria2.secret:
                cmd.append(f"--rpc-secret={self.aria2.secret}")

            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2.0)

        except FileNotFoundError:
            QMessageBox.critical(
                self,
                "aria2 Not Found",
                "aria2 is not installed.\nRun: sudo pacman -S aria2",
            )

    def _on_aria2_error(self, message: str) -> None:
        if any(
            x in message
            for x in [
                "disconnected",
                "cannot be paused now",
                "cannot be unpaused now",
                "is not found",
                "HTTP Error 400",
                "Bad Request",
            ]
        ):
            return
        self.tray.showMessage(
            "FelfelDM", message, QSystemTrayIcon.MessageIcon.Warning, 3000
        )
        self.status_label.setText(f"⚠ {message}")

    def _open_progress_dialog(self, gid: str) -> None:
        dl_data = self._all_downloads.get(gid, {})

        if self._progress_dialog is not None:
            try:
                self._progress_dialog.close()
            except Exception:
                pass
            self._progress_dialog = None

        self._progress_dialog = DownloadProgressDialog(gid, dl_data, None)

        self._progress_dialog.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        self._progress_dialog.setWindowModality(Qt.WindowModality.NonModal)

        self._progress_dialog.pause_requested.connect(self._pause_from_dialog)
        self._progress_dialog.resume_requested.connect(self._resume_from_dialog)
        self._progress_dialog.cancel_requested.connect(self._cancel_from_dialog)
        self._progress_dialog.cancel_with_delete_requested.connect(
            self._cancel_with_delete_from_dialog
        )
        self._progress_dialog.finished.connect(self._on_progress_dialog_closed)
        self._progress_dialog.show()
        self._center_dialog_on_screen(self._progress_dialog)

        if dl_data.get("totalLength", 0) == 0:
            self._progress_dialog.info_labels["size"].setText("Getting size...")

    def _center_dialog_on_screen(self, dialog: QDialog) -> None:
        screen = QApplication.primaryScreen().geometry()
        dialog.move(
            screen.center().x() - dialog.width() // 2,
            screen.center().y() - dialog.height() // 2,
        )

    def _on_progress_dialog_closed(self) -> None:
        self._progress_dialog = None

    def _pause_from_dialog(self, gid: str) -> None:
        print(f"⏸️ Pause requested for: {gid}")
        if not gid:
            return

        if gid in self._all_downloads:
            real_status = self._all_downloads[gid].get("status", "")
        else:
            real_status = ""

        if real_status in ["active", "waiting"]:
            try:
                if self.aria2.force_pause(gid) is not None:
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "paused"
                        self._all_downloads[gid]["downloadSpeed"] = 0

                    for q in self.store.queues:
                        if gid in q.downloads_info:
                            q.downloads_info[gid]["status"] = "paused"
                            break

                    self.store.save()

                    q = self._current_queue()
                    has_active = False
                    if q and q.name != "__direct__":
                        for other_gid in q.downloads:
                            if other_gid in self._all_downloads and self._all_downloads[
                                other_gid
                            ].get("status", "") in ["active", "waiting"]:
                                has_active = True
                                break

                        if not has_active:
                            q.paused = True
                            self.store.save()
                            print(
                                f"⏸️ Queue '{q.name}' auto-paused (no active downloads)"
                            )

                    self._refresh_table()
                    self._refresh_queue_list()
                    self._update_queue_status()
                    self._update_queue_buttons()
                    self._update_toggle_button()

                    if (
                        self._progress_dialog
                        and self._progress_dialog.isVisible()
                        and gid in self._all_downloads
                    ):
                        self._progress_dialog.update_data(self._all_downloads[gid])

                    self.tray.showMessage(
                        "FelfelDM",
                        (
                            f"⏸️ Queue '{q.name}' paused (no active downloads)"
                            if not has_active and q and q.name != "__direct__"
                            else "⏸️ Download paused"
                        ),
                        QSystemTrayIcon.MessageIcon.Information,
                        2000,
                    )
            except Exception as e:
                print(f"❌ Pause error: {e}")

    def _resume_from_dialog(self, gid: str) -> None:
        print(f"▶️ Resume requested for: {gid}")

        if not gid:
            return

        q = self._current_queue()
        if q and q.paused and q.name != "__direct__":
            QMessageBox.warning(
                self,
                "Queue is Paused",
                f"The queue '{q.name}' is currently paused.\n\n"
                "To start this download, you need to:\n"
                "Click the 'Start' option from the Queue menu\n",
                QMessageBox.StandardButton.Ok,
            )
            return

        if gid in self._all_downloads:
            real_status = self._all_downloads[gid].get("status", "")
        else:
            real_status = ""

        if real_status in ["paused", "error"]:
            try:
                if real_status == "error":
                    # Use the common re-add method
                    new_gid = self._re_add_download(gid)
                    if new_gid:
                        gid = new_gid
                    else:
                        return

                if self.aria2.resume(gid) is not None:
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "active"

                    for q in self.store.queues:
                        if gid in q.downloads_info:
                            q.downloads_info[gid]["status"] = "active"
                            break

                    self.store.save()

                    if q and q.speed_limit > 0:
                        self.aria2.set_download_speed_limit(gid, q.speed_limit)

                    self.tray.showMessage(
                        "FelfelDM",
                        "▶️ Download resumed",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000,
                    )

                    self._refresh_table()
                    self._update_progress_bar()
                    self._update_toggle_button()

                    if (
                        self._progress_dialog
                        and self._progress_dialog.isVisible()
                        and gid in self._all_downloads
                    ):
                        self._progress_dialog.update_data(self._all_downloads[gid])
            except Exception as e:
                print(f"❌ Resume error: {e}")

    def _cancel_from_dialog(self, gid: str) -> None:
        try:
            self.aria2.remove(gid)
        except Exception as e:
            print(f"⚠ Could not remove GID {gid} from aria2: {e}")

        for q in self.store.queues:
            if gid in q.downloads:
                q.downloads.remove(gid)

        if gid in self._all_downloads:
            del self._all_downloads[gid]

        self.store.save()
        self._refresh_table()
        self._refresh_queue_list()
        self._update_progress_bar()
        self._progress_dialog = None
        self.tray.showMessage(
            "FelfelDM",
            "Download cancelled.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _cancel_with_delete_from_dialog(self, gid: str) -> None:
        print(f"🗑️ Cancel with delete requested for: {gid}")

        try:
            self.aria2.remove(gid)
            print(f"⏹️ Removed from aria2: {gid}")
        except Exception as e:
            print(f"⚠️ Could not remove from aria2: {e}")

        QApplication.processEvents()
        time.sleep(0.5)

        file_paths = []
        aria2_files = []

        if gid in self._all_downloads:
            files = self._all_downloads[gid].get("files", [])
            for f in files:
                path = f.get("path")
                if path and os.path.exists(path):
                    file_paths.append(path)

                    aria2_path = path + ".aria2"
                    if os.path.exists(aria2_path):
                        aria2_files.append(aria2_path)

            if not file_paths:
                for q in self.store.queues:
                    if gid in q.downloads_info:
                        info = q.downloads_info[gid]
                        name = info.get("name", "")
                        save_path = q.save_path
                        if name and save_path:
                            possible_path = os.path.join(save_path, name)
                            if os.path.exists(possible_path):
                                file_paths.append(possible_path)
                                aria2_path = possible_path + ".aria2"
                                if os.path.exists(aria2_path):
                                    aria2_files.append(aria2_path)
                        break

        for q in self.store.queues:
            if gid in q.downloads:
                q.downloads.remove(gid)
            if gid in q.downloads_info:
                del q.downloads_info[gid]

        if gid in self._all_downloads:
            del self._all_downloads[gid]

        def delete_with_retry(path, max_attempts=5):
            for attempt in range(max_attempts):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                        print(f"🗑️ DELETED: {os.path.basename(path)}")
                        return True
                except PermissionError:
                    print(
                        f"⏳ File in use, retrying {attempt+1}/{max_attempts}: {os.path.basename(path)}"
                    )
                    time.sleep(0.3)
                except Exception as e:
                    print(f"⚠️ Delete failed {path}: {e}")
                    return False
            return False

        for path in file_paths:
            delete_with_retry(path)

        for path in aria2_files:
            delete_with_retry(path)

        for path in aria2_files:
            if os.path.exists(path):
                print(f"⚠️ Temp file still exists: {path}, trying force delete...")
                try:
                    subprocess.run(["pkill", "-9", "aria2c"], capture_output=True)
                    time.sleep(0.5)
                    os.remove(path)
                    print(f"🗑️ FORCE DELETED: {os.path.basename(path)}")
                except Exception as e:
                    print(f"⚠️ Could not force delete {path}: {e}")

        self.store.save()
        self._refresh_table()
        self._refresh_queue_list()
        self._update_progress_bar()
        self._progress_dialog = None

        self.tray.showMessage(
            "FelfelDM",
            "Download cancelled and files deleted.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _quick_download(self) -> None:
        all_queues = self.store.queues
        dlg = QuickDownloadDialog(all_queues, self)

        clip = QApplication.clipboard().text().strip()
        if clip and clip.startswith(("http", "magnet:", "ftp")):
            dlg.url_edit.setText(clip)

        if dlg.exec():
            d = dlg.get_data()
            if not d["urls"]:
                return

            queue_name = d.get("queue_name", "__direct__")
            target_queue = self._get_or_create_queue(queue_name)

            options = {
                "dir": d["path"],
                "split": str(d["connections"]),
                "max-connection-per-server": str(d["connections"]),
                "min-split-size": "1M",
                "continue": "true",
                "always-resume": "true",
                "header": [
                    "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
                ],
            }

            proxy_mode = d.get("proxy_mode", 0)
            if proxy_mode == 0:
                proxy = self.proxy_manager.get_proxy_for_queue(target_queue.name)
                if proxy and proxy.is_valid():
                    options["all-proxy"] = proxy._build_proxy_url()
            elif proxy_mode == 1:
                custom_proxy = d.get("custom_proxy")
                if custom_proxy and custom_proxy.is_valid():
                    options["all-proxy"] = custom_proxy._build_proxy_url()
            elif proxy_mode == 2:
                options["all-proxy"] = ""

            added_gids = []
            for url in d["urls"]:

                options_with_pause = options.copy()
                options_with_pause["pause"] = "true"
                gid = self.aria2.add_url(url, options_with_pause)

                if gid:
                    target_queue.downloads.append(gid)
                    clean_name = self._extract_filename(url)
                    full_path = os.path.join(d["path"], clean_name)

                    target_queue.downloads_info[gid] = {
                        "url": url,
                        "name": clean_name,
                        "totalLength": 0,
                        "completedLength": 0,
                        "status": "waiting",
                        "files": [
                            {
                                "path": full_path,
                                "length": "0",
                                "completedLength": "0",
                                "selected": "true",
                                "uris": [],
                            }
                        ],
                        "category": "📁 Other",
                    }

                    self._all_downloads[gid] = {
                        "gid": gid,
                        "name": clean_name,
                        "status": "waiting",
                        "totalLength": 0,
                        "completedLength": 0,
                        "downloadSpeed": 0,
                        "connections": 0,
                        "files": [{"path": full_path}],
                        "errorMessage": "",
                        "category": "📁 Other",
                        "size_fetch_attempts": 0,
                    }

                    added_gids.append(gid)

            self.store.save()
            self._refresh_queue_list()
            self._refresh_table()
            self._update_shutdown_button_state()

            if queue_name == "__direct__":
                target_queue.paused = False
                for gid in added_gids:

                    def start_direct_download(gid=gid):
                        try:
                            self.aria2.resume(gid)
                            self._all_downloads[gid]["status"] = "active"
                            if gid in target_queue.downloads_info:
                                target_queue.downloads_info[gid]["status"] = "active"
                            print(
                                f"▶️ Started Direct: {self._all_downloads[gid].get('name', 'Unknown')}"
                            )
                        except Exception as e:
                            print(f"⚠️ Could not resume: {e}")
                        self._open_progress_dialog(gid)

                    QTimer.singleShot(500, lambda gid=gid: start_direct_download(gid))
            else:
                if target_queue.paused:
                    for gid in added_gids:
                        try:
                            self.aria2.pause(gid)
                            if gid in self._all_downloads:
                                self._all_downloads[gid]["status"] = "paused"
                                self._all_downloads[gid]["downloadSpeed"] = 0
                            if gid in target_queue.downloads_info:
                                target_queue.downloads_info[gid]["status"] = "paused"
                        except Exception as e:
                            print(f"⚠️ Could not pause {gid}: {e}")

                    self.tray.showMessage(
                        "FelfelDM",
                        f"✅ Added {len(added_gids)} download(s) to '{target_queue.name}' (paused)",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000,
                    )
                else:
                    self.tray.showMessage(
                        "FelfelDM",
                        f"✅ Added {len(added_gids)} download(s) to '{target_queue.name}' (downloading)",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000,
                    )

    def _on_table_double_click(self, index: QModelIndex) -> None:
        gid = self.model.get_gid(index.row())
        if not gid:
            return

        download_type = self._all_downloads.get(gid, {}).get("download_type", "normal")
        if download_type == "youtube":
            self._open_youtube_progress_dialog(gid)
        else:
            self._open_progress_dialog(gid)

    def _close_splash(self) -> None:
        if hasattr(self, "splash") and self.splash:
            self.splash.close()
            self.splash = None

    def _youtube_download(self) -> None:
        queues = [q for q in self.store.queues if q.name != "__direct__"]
        default_idx = 0
        current_q = self._current_queue()
        if current_q and current_q.name != "__direct__":
            for i, q in enumerate(queues):
                if q.name == current_q.name:
                    default_idx = i
                    break

        dlg = YouTubeDownloadDialog(
            parent=self, queues=queues, default_queue=default_idx
        )
        dlg.youtube_download_requested.connect(self._add_youtube_to_queue)

        clip = QApplication.clipboard().text().strip()
        if clip and ("youtube.com" in clip or "youtu.be" in clip):
            dlg.url_edit.setText(clip)

        dlg.exec()

    def _add_youtube_to_queue(self, download_data: Dict[str, Any]) -> None:
        print("🎯🎯🎯 _add_youtube_to_queue CALLED")

        queue_name = download_data.get("queue_id", "Default")
        target_queue = None
        for q in self.store.queues:
            if q.name == queue_name:
                target_queue = q
                break

        if not target_queue:
            target_queue = Queue(queue_name, paused=True)
            self.store.queues.append(target_queue)
            self.store.save()

        import uuid

        download_id = str(uuid.uuid4())

        yt_options = download_data.get("yt_options", {})
        video_info = download_data.get("video_info", {})
        title = video_info.get("title", "Unknown Video")

        format_type = yt_options.get("format", "video")
        ext = "mp4" if format_type == "video" else "mp3"
        filename = re.sub(r'[<>:"/\\|?*]', "_", f"{title}.{ext}")
        full_path = os.path.join(download_data["save_path"], filename)

        youtube_data = {
            "id": download_id,
            "url": download_data["url"],
            "save_path": download_data["save_path"],
            "queue_id": queue_name,
            "download_type": "youtube",
            "status": "paused",
            "progress": 0,
            "speed": "",
            "eta": "",
            "yt_options": {
                "title": title,
                "quality": yt_options.get("quality", "best"),
                "format": format_type,
                "cookies_path": yt_options.get("cookies_path"),
                "format_id": yt_options.get("format_id"),
                "format_info": yt_options.get("format_info", {}),
            },
            "proxy": download_data.get("proxy"),
            "video_info": video_info,
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
            "error_message": "",
            "filename": filename,
            "full_path": full_path,
        }

        self.store.add_youtube_download(youtube_data)

        self._all_downloads[download_id] = {
            "gid": download_id,
            "name": title,
            "status": "paused",
            "totalLength": 0,
            "completedLength": 0,
            "downloadSpeed": 0,
            "connections": 0,
            "files": [{"path": full_path}],
            "errorMessage": "",
            "category": "🎬 YouTube",
            "download_type": "youtube",
            "real_path": full_path,
            "yt_options": youtube_data["yt_options"],
        }

        if download_id not in target_queue.downloads:
            target_queue.downloads.append(download_id)

        target_queue.downloads_info[download_id] = {
            "url": download_data["url"],
            "name": title,
            "totalLength": 0,
            "completedLength": 0,
            "status": "paused",
            "category": "🎬 YouTube",
            "download_type": "youtube",
            "files": [{"path": full_path}],
            "real_path": full_path,
        }

        self.store.save()

        if self.worker:
            self.worker.add_youtube_download(
                {
                    "id": download_id,
                    "url": download_data["url"],
                    "save_path": download_data["save_path"],
                    "yt_options": youtube_data["yt_options"],
                    "proxy": download_data.get("proxy"),
                    "queue_id": queue_name,
                }
            )

        self._refresh_queue_list()
        self._refresh_table()
        self._update_queue_buttons()
        self._update_shutdown_button_state()

        self.tray.showMessage(
            "FelfelDM",
            f"✅ Added YouTube download to '{queue_name}': {title[:50]}...",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    def _start_youtube_download(self, download_id: str) -> None:
        if not hasattr(self, "worker") or not self.worker:
            print("❌ Worker not available")
            return

        data = self.store.get_youtube_download(download_id)
        if not data:
            print(f"❌ Download {download_id} not found")
            return

        self.worker.add_youtube_download(
            {
                "id": download_id,
                "url": data["url"],
                "save_path": data["save_path"],
                "yt_options": data.get("yt_options", {}),
                "proxy": data.get("proxy"),
                "queue_id": data.get("queue_id"),
            }
        )

    def _pause_youtube_download(self, download_id: str) -> None:
        if not hasattr(self, "worker"):
            return

        print(f"⏸️ [UI] Pausing YouTube: {download_id}")
        self.worker.pause_youtube_download(download_id)

        if download_id in self._all_downloads:
            self._all_downloads[download_id]["status"] = "paused"

        q = self._current_queue()
        if q and q.name != "__direct__":
            has_active = any(
                gid in self._all_downloads
                and self._all_downloads[gid].get("status", "")
                in ["active", "waiting", "downloading"]
                for gid in q.downloads
            )
            if not has_active:
                q.paused = True
                self.store.save()
                print(f"⏸️ [UI] Queue '{q.name}' auto-paused (no active downloads)")

        self._update_queue_buttons()
        self._refresh_table()

    def _resume_youtube_download(self, download_id: str) -> None:
        if not hasattr(self, "worker"):
            return

        q = self._current_queue()
        if q and q.paused and q.name != "__direct__":
            QMessageBox.warning(
                self,
                "Queue is Paused",
                f"The queue '{q.name}' is currently paused.\n\n"
                "Please click the 'Start' button for this queue in the sidebar first.",
                QMessageBox.StandardButton.Ok,
            )
            return

        print(f"▶️ [UI] Resuming YouTube: {download_id}")
        self.worker.resume_youtube_download(download_id)

        if download_id in self._all_downloads:
            self._all_downloads[download_id]["status"] = "downloading"

        self._update_queue_buttons()
        self._refresh_table()

    def _cancel_youtube_download(self, download_id: str) -> None:
        if not hasattr(self, "worker"):
            print("❌ Worker not available")
            return

        print(f"🗑️ Cancelling YouTube download from UI: {download_id}")

        if self._youtube_dialog is not None:
            try:
                self._youtube_dialog.close()
            except Exception:
                pass
            self._youtube_dialog = None

        self.worker.cancel_youtube_download(download_id)

        if download_id in self._all_downloads:
            del self._all_downloads[download_id]

        for q in self.store.queues:
            if download_id in q.downloads:
                q.downloads.remove(download_id)
            if download_id in q.downloads_info:
                del q.downloads_info[download_id]

        self.store.delete_youtube_download(download_id)
        self.store.save()

        self._refresh_table()
        self._refresh_queue_list()
        self._update_queue_buttons()

        self.tray.showMessage(
            "FelfelDM",
            "🗑 YouTube download cancelled and files deleted",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _on_youtube_finished(self, success: bool, message: str) -> None:
        if success:
            self.tray.showMessage(
                "FelfelDM",
                "✅ YouTube download completed!",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        elif "cancelled" not in message.lower():
            self.tray.showMessage(
                "FelfelDM",
                f"❌ YouTube download failed: {message}",
                QSystemTrayIcon.MessageIcon.Warning,
                3000,
            )

    def _apply_proxy_to_aria2(self) -> None:
        proxy = self.proxy_manager.get_proxy_for_queue(None)
        if proxy and proxy.enabled and proxy.is_valid():
            if self.aria2.set_global_proxy(proxy) is not None:
                print(f"✅ Global proxy applied: {proxy.get_display_string()}")
            else:
                print("⚠️ Failed to apply proxy")
        else:
            self.aria2.change_global_option({"all-proxy": ""})
            print("✅ Proxy disabled")

    def _toggle_pause_resume(self) -> None:
        gid = self._selected_gid()
        if not gid:
            return

        download_type = self._all_downloads.get(gid, {}).get("download_type", "normal")

        if download_type == "youtube":
            real_status = self._all_downloads.get(gid, {}).get("status", "")
        else:
            real_status = self._all_downloads.get(gid, {}).get("status", "")

        if not real_status:
            return

        if real_status in ["active", "waiting", "downloading"]:
            if download_type == "youtube":
                self._pause_youtube_download(gid)
            else:
                self._pause_selected()

        elif real_status == "paused":
            if download_type == "youtube":
                self._resume_youtube_download(gid)
            else:
                self._resume_selected()

    def _set_download_proxy(self, gid: str, download_name: str) -> None:
        from ui.download_proxy_dialog import DownloadProxyDialog

        current = self.proxy_manager.get_proxy_for_download(gid)
        dlg = DownloadProxyDialog(download_name, current, self)

        if dlg.exec():
            data = dlg.get_data()
            if data["use_custom"]:
                self.proxy_manager.set_download_proxy(gid, data["config"])
                self.tray.showMessage(
                    "FelfelDM",
                    f"✅ Custom proxy set for: {download_name}",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )
            else:
                self.proxy_manager.set_download_proxy(gid, None)
                self.tray.showMessage(
                    "FelfelDM",
                    f"ℹ️ Proxy cleared for: {download_name}",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )
            self._refresh_table()

    def _clear_download_proxy(self, gid: str) -> None:
        self.proxy_manager.set_download_proxy(gid, None)
        name = self._all_downloads.get(gid, {}).get("name", "Unknown")
        self.tray.showMessage(
            "FelfelDM",
            f"🗑 Proxy cleared for: {name}",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )
        self._refresh_table()

    def _move_selected_to_queue(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "Info", "No downloads selected.")
            return

        gids_to_move = [
            self.model.get_gid(idx.row())
            for idx in selected
            if self.model.get_gid(idx.row())
        ]
        if not gids_to_move:
            QMessageBox.warning(self, "Error", "No valid downloads selected.")
            return

        source_queue = self._current_queue()
        if not source_queue:
            QMessageBox.warning(self, "Error", "No source queue selected.")
            return

        target_queues = [
            q
            for q in self.store.queues
            if q.name != source_queue.name and q.name != "__direct__"
        ]
        if not target_queues:
            QMessageBox.warning(self, "Error", "No other queues available to move to.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Move to Queue")
        dlg.setMinimumWidth(400)

        layout = QVBoxLayout(dlg)
        layout.addWidget(
            QLabel(
                f"Move {len(gids_to_move)} download(s) from '{source_queue.name}' to:"
            )
        )
        queue_combo = QComboBox()
        for q in target_queues:
            queue_combo.addItem(q.name, q)
        layout.addWidget(queue_combo)

        btn_layout = QHBoxLayout()
        btn_move = QPushButton("Move")
        btn_move.setIcon(get_icon("go-next"))
        btn_cancel = QPushButton("Cancel")
        btn_layout.addStretch()
        btn_layout.addWidget(btn_move)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        result = None

        def on_move():
            nonlocal result
            result = queue_combo.currentData()
            dlg.accept()

        def on_cancel():
            nonlocal result
            result = None
            dlg.reject()

        btn_move.clicked.connect(on_move)
        btn_cancel.clicked.connect(on_cancel)

        dlg.exec()

        if result is None:
            return

        target_queue = result

        self.btn_move_queue.setEnabled(False)
        self.btn_move_queue.setText("Moving...")
        QApplication.processEvents()

        moved_count = 0
        total = len(gids_to_move)

        statuses = {}
        for gid in gids_to_move:
            status_data = self.aria2.get_status(gid)
            if status_data and isinstance(status_data, dict):
                statuses[gid] = status_data.get("status", "")
            elif gid in self._all_downloads:
                statuses[gid] = self._all_downloads[gid].get("status", "")

        for i, gid in enumerate(gids_to_move):

            if i % 5 == 0:
                QApplication.processEvents()
                self.btn_move_queue.setText(f"Moving... {i+1}/{total}")

            real_status = statuses.get(gid, "")

            if gid in source_queue.downloads:
                source_queue.downloads.remove(gid)

            if gid not in target_queue.downloads:
                target_queue.downloads.append(gid)

                if gid in source_queue.downloads_info:
                    info = source_queue.downloads_info.pop(gid)
                    if real_status:
                        info["status"] = real_status
                    target_queue.downloads_info[gid] = info

                if gid in self._all_downloads:
                    if real_status:
                        self._all_downloads[gid]["status"] = real_status

                    if target_queue.paused:
                        self._all_downloads[gid]["status"] = "paused"
                        self._all_downloads[gid]["downloadSpeed"] = 0
                    else:
                        self._all_downloads[gid]["status"] = "active"

                moved_count += 1

        if target_queue.paused:
            for gid in gids_to_move:
                try:
                    self.aria2.pause(gid)
                except:
                    pass
        else:
            for gid in gids_to_move:
                try:
                    self.aria2.resume(gid)
                except:
                    pass

        self.btn_move_queue.setEnabled(True)
        self.btn_move_queue.setText("Move to Queue")

        self.store.save()
        self._refresh_queue_list()
        self._refresh_table()
        self._update_queue_buttons()
        self._update_toggle_button()

        if len(source_queue.downloads) == 0:
            source_queue.paused = True
            self.store.save()
            self._refresh_queue_list()

        self.tray.showMessage(
            "FelfelDM",
            f"✅ Moved {moved_count} download(s) to '{target_queue.name}'",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _process_move_item(self) -> None:
        """This method is no longer used - kept for compatibility"""
        pass

    def _on_queues_reordered(self, parent, start, end, destination, row) -> None:
        """This method is no longer used - kept for compatibility"""
        pass

    def _on_size_fetched(self, gid: str, size: int, category: str = "📁 Other") -> None:

        if size < 0:
            size = size & 0xFFFFFFFF
            print(f"🔄 [Size] Converted negative to unsigned: {size}")

        if size <= 0:
            print(f"⚠️ [Size] Invalid size for {gid}: {size}")
            return

        if gid in self._all_downloads:

            self._all_downloads[gid]["totalLength"] = size
            self._all_downloads[gid]["category"] = category

            self._refresh_table()

            print(
                f"✅ [MainWindow] Size updated for {gid}: {size} bytes ({size/1024/1024/1024:.2f} GB)"
            )
        else:
            print(f"⚠️ [MainWindow] GID {gid} not found in _all_downloads")

    def _show_shutdown_countdown(self) -> None:
        if self._shutdown_dialog:
            self._shutdown_dialog.close()
            self._shutdown_dialog = None

        dialog = ShutdownCountdownDialog(self)
        dialog.accepted.connect(self._shutdown_system)
        dialog.rejected.connect(self._cancel_shutdown)
        dialog.start_countdown()

        self._shutdown_dialog = dialog
        self._center_dialog_on_screen(dialog)

    def _shutdown_system(self) -> None:
        self._shutdown_dialog = None
        self._shutdown_dialog_shown = False
        self.tray.showMessage(
            "FelfelDM",
            "🛑 Shutting down system...",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )
        os.system("systemctl poweroff")

    def _cancel_shutdown(self) -> None:
        self._shutdown_dialog = None
        self._shutdown_dialog_shown = False
        self.shutdown_cb.setChecked(False)
        self.store.settings["shutdown_after_finish"] = False
        self.store.save()
        self.tray.showMessage(
            "FelfelDM",
            "✅ Shutdown cancelled.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _update_shutdown_button_state(self) -> None:
        q = self._current_queue()
        if not q or q.name == "__direct__" or len(q.downloads) == 0:
            self.shutdown_cb.setEnabled(False)
            return

        all_complete = all(
            gid in self._all_downloads
            and self._all_downloads[gid].get("status", "")
            in ["complete", "error", "removed"]
            for gid in q.downloads
        )

        if all_complete:
            self.shutdown_cb.setEnabled(False)
            if self.shutdown_cb.isChecked():
                self.shutdown_cb.setChecked(False)
                self.store.settings["shutdown_after_finish"] = False
                self.store.save()
            return

        self.shutdown_cb.setEnabled(True)

    def _has_active_downloads(self, q: Optional[Queue]) -> bool:
        if not q:
            return False
        return any(
            gid in self._all_downloads
            and self._all_downloads[gid].get("status", "") in ["active", "waiting"]
            for gid in q.downloads
        )

    def _has_resumable_downloads(self, q: Optional[Queue]) -> bool:
        if not q:
            return False
        return any(
            gid in self._all_downloads
            and self._all_downloads[gid].get("status", "") in ["paused", "waiting"]
            for gid in q.downloads
        )

    def _apply_queue_speed_limit(self, q: Optional[Queue]) -> None:
        if not q or not self.aria2:
            return

        for gid in q.downloads:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                if status in ["active", "waiting"]:
                    if q.speed_limit > 0:
                        self.aria2.set_download_speed_limit(gid, q.speed_limit)
                        print(
                            f"⚡ Queue speed limit {q.speed_limit}KB/s applied to {gid}"
                        )
                    else:
                        global_limit = self.store.settings.get("speed_limit", 0)
                        self.aria2.set_download_speed_limit(
                            gid, global_limit if global_limit > 0 else 0
                        )

    def _parse_speed(self, speed_str: str) -> int:
        if not speed_str:
            return 0
        try:
            speed_str = speed_str.strip()
            if "KiB/s" in speed_str:
                return int(float(speed_str.replace("KiB/s", "").strip()) * 1024)
            if "MiB/s" in speed_str:
                return int(float(speed_str.replace("MiB/s", "").strip()) * 1024 * 1024)
            if "KB/s" in speed_str:
                return int(float(speed_str.replace("KB/s", "").strip()) * 1000)
            if "MB/s" in speed_str:
                return int(float(speed_str.replace("MB/s", "").strip()) * 1000 * 1000)
            if speed_str.isdigit():
                return int(speed_str)
            return 0
        except Exception:
            return 0

    def _on_youtube_progress(self, download_id: str, progress: int) -> None:
        if download_id in self._all_downloads:
            old_progress = self._all_downloads[download_id].get("progress", 0)
            if progress < old_progress:
                print(
                    f"⏭️ [Progress] Skipping backwards progress: {old_progress} -> {progress}"
                )
                return

            self._all_downloads[download_id]["progress"] = progress
            self._all_downloads[download_id]["status"] = "downloading"
            self._update_youtube_dialog(download_id, progress=progress)
            self._refresh_table()

    def _on_youtube_status(self, download_id: str, status: str) -> None:
        print(f"📢 [UI] _on_youtube_status: {download_id} -> {status}")

        if download_id in self._all_downloads:
            self._all_downloads[download_id]["status"] = status
            self._all_downloads[download_id]["status_text"] = status

            if status == "paused":
                self._update_youtube_dialog(download_id, status="⏸ Paused")
                self._update_youtube_dialog_pause_state(download_id, is_paused=True)
            elif status == "downloading":
                self._update_youtube_dialog(download_id, status="⬇ Downloading...")
                self._update_youtube_dialog_pause_state(download_id, is_paused=False)
            elif status == "completed":
                self._update_youtube_dialog(download_id, status="✅ Complete")
                self._update_youtube_dialog_finished(
                    download_id, True, "Download completed!"
                )
            elif status == "error":
                self._update_youtube_dialog(download_id, status="❌ Error")
                self._update_youtube_dialog_finished(
                    download_id, False, "Download failed"
                )

            self._update_queue_buttons()
            self._refresh_table()

    def _on_youtube_speed(self, download_id: str, speed: str, eta: str) -> None:
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["speed"] = speed
            self._all_downloads[download_id]["eta"] = eta
            self._all_downloads[download_id]["downloadSpeed"] = self._parse_speed(speed)
            self._refresh_table()

    def _on_youtube_size_fetched(self, download_id: str, size: int) -> None:
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["totalLength"] = size
            self._all_downloads[download_id]["total_size"] = size
            print(f"📏 YouTube size updated for {download_id}: {size} bytes")
            self._refresh_table()

    def _open_youtube_progress_dialog(self, download_id: str) -> None:
        try:
            from ui.youtube_progress import YouTubeProgressDialog

            if not download_id:
                return

            if self._youtube_dialog is not None:
                try:
                    self._youtube_dialog.close()
                    self._youtube_dialog.deleteLater()
                except Exception:
                    pass
                self._youtube_dialog = None

            data = self.store.get_youtube_download(download_id)
            if not data:
                QMessageBox.warning(self, "Error", "Download not found")
                return

            self._youtube_dialog = YouTubeProgressDialog(
                url=data["url"],
                output_path=data["save_path"],
                format_type=data.get("yt_options", {}).get("format", "mp4"),
                cookie_file=data.get("yt_options", {}).get("cookies_path"),
                video_info=data.get("video_info", {}),
                parent=None,
                proxy_url=data.get("proxy"),
                download_id=download_id,
            )

            self._youtube_dialog.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.WindowCloseButtonHint
                | Qt.WindowType.WindowMinimizeButtonHint
            )
            self._youtube_dialog.setWindowModality(Qt.WindowModality.NonModal)

            self._youtube_dialog.pause_requested.connect(self._pause_youtube_download)
            self._youtube_dialog.resume_requested.connect(self._resume_youtube_download)
            self._youtube_dialog.cancel_requested.connect(self._cancel_youtube_download)

            self._youtube_dialog.show()
            self._center_dialog_on_screen(self._youtube_dialog)
            self._youtube_dialog.raise_()
            self._youtube_dialog.activateWindow()

            if download_id in self._all_downloads:
                dl_data = self._all_downloads[download_id]
                status = dl_data.get("status", "pending")
                progress = dl_data.get("progress", 0)
                speed = dl_data.get("speed", "")
                eta = dl_data.get("eta", "")

                self._youtube_dialog.update_progress(progress, speed, eta)

                if status == "paused":
                    self._youtube_dialog.update_pause_state(True)
                elif status == "downloading":
                    self._youtube_dialog.update_pause_state(False)
                elif status == "completed":
                    self._youtube_dialog.update_finished(True, "Download completed!")
                elif status == "error":
                    self._youtube_dialog.update_status("❌ Error")
                else:
                    self._youtube_dialog.update_status("⏳ Pending...")

                if status in ["paused", "downloading", "completed"]:
                    self._youtube_dialog.set_action_button_enabled(True)
                else:
                    self._youtube_dialog.set_action_button_enabled(False)

        except Exception as e:
            print(f"❌ Error opening YouTube dialog: {e}")
            QMessageBox.warning(self, "Error", f"Failed to open dialog: {e}")

    def _update_youtube_dialog(
        self,
        download_id: str,
        progress: Optional[int] = None,
        speed: Optional[str] = None,
        eta: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        if not self._youtube_dialog or not self._youtube_dialog.isVisible():
            return

        try:
            if (
                hasattr(self._youtube_dialog, "download_id")
                and self._youtube_dialog.download_id != download_id
            ):
                return

            if progress is not None and hasattr(
                self._youtube_dialog, "update_progress"
            ):
                current_speed = speed or getattr(
                    self._youtube_dialog, "_speed_text", ""
                )
                current_eta = eta or getattr(self._youtube_dialog, "_eta_text", "")
                self._youtube_dialog.update_progress(
                    progress, current_speed, current_eta
                )

            if status is not None and hasattr(self._youtube_dialog, "update_status"):
                self._youtube_dialog.update_status(status)

        except Exception as e:
            print(f"⚠️ Error updating YouTube dialog: {e}")

    def _update_youtube_dialog_pause_state(
        self, download_id: str, is_paused: bool
    ) -> None:
        if not self._youtube_dialog or not self._youtube_dialog.isVisible():
            return

        try:
            if (
                hasattr(self._youtube_dialog, "download_id")
                and self._youtube_dialog.download_id != download_id
            ):
                return

            if hasattr(self._youtube_dialog, "update_pause_state"):
                self._youtube_dialog.update_pause_state(is_paused)

        except Exception as e:
            print(f"⚠️ Error updating YouTube dialog pause state: {e}")

    def _update_youtube_dialog_finished(
        self, download_id: str, success: bool, message: str
    ) -> None:
        if not self._youtube_dialog or not self._youtube_dialog.isVisible():
            return

        try:
            if (
                hasattr(self._youtube_dialog, "download_id")
                and self._youtube_dialog.download_id != download_id
            ):
                return

            if hasattr(self._youtube_dialog, "update_finished"):
                self._youtube_dialog.update_finished(success, message)

        except Exception as e:
            print(f"⚠️ Error updating YouTube dialog finished: {e}")

    def _update_youtube_dialog_to_completed(self, download_id: str) -> None:
        if not self._youtube_dialog or not self._youtube_dialog.isVisible():
            return

        try:
            dialog = self._youtube_dialog
            if hasattr(dialog, "download_id") and dialog.download_id != download_id:
                return

            from utils.helpers import get_icon

            dialog._is_complete = True
            dialog.title_label.setText("✅ Download completed!")
            dialog.title_label.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #27ae60;"
            )
            dialog.status_label.setText("Download completed successfully!")
            dialog.status_label.setStyleSheet("color: #27ae60;")
            dialog.speed_eta_label.setText("")
            dialog.progress_bar.setValue(100)
            dialog.progress_bar.setFormat("100%")

            dialog.action_btn.setIcon(get_icon("folder"))
            dialog.action_btn.setText(" Open Folder")
            dialog.action_btn.setEnabled(True)
            try:
                dialog.action_btn.clicked.disconnect()
            except Exception:
                pass
            dialog.action_btn.clicked.connect(dialog._open_folder)

            dialog.cancel_btn.setText(" Close")
            dialog.cancel_btn.setIcon(get_icon("window-close"))
            try:
                dialog.cancel_btn.clicked.disconnect()
            except Exception:
                pass
            dialog.cancel_btn.clicked.connect(dialog.accept)

            print(f"✅ [UI] YouTube dialog updated to completed: {download_id}")

        except Exception as e:
            print(f"⚠️ Error updating YouTube dialog to completed: {e}")

    def _delete_youtube_files(self, file_path: str, save_path: str, title: str) -> None:
        try:
            import glob
            import re

            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"🗑️ Deleted: {file_path}")

            base_name = os.path.splitext(os.path.basename(file_path))[0]
            patterns = [
                f"{base_name}.*.part",
                f"{base_name}.*.ytdl",
                f"{base_name}.*.f*",
                f"{base_name}.*.temp",
                f"{base_name}.*.download",
            ]

            for pattern in patterns:
                full_pattern = os.path.join(save_path, pattern)
                for f in glob.glob(full_pattern):
                    try:
                        os.remove(f)
                        print(f"🗑️ Deleted partial: {f}")
                    except Exception:
                        pass

            safe_title = re.sub(r'[<>:"/\\|?*]', "_", title)
            partial_patterns = [
                f"{safe_title}.*.part",
                f"{safe_title}.*.ytdl",
                f"{safe_title}.*.f*",
                f"{safe_title}.*.temp",
                f"{safe_title}.*.download",
            ]

            for pattern in partial_patterns:
                full_pattern = os.path.join(save_path, pattern)
                for f in glob.glob(full_pattern):
                    try:
                        os.remove(f)
                        print(f"🗑️ Deleted partial (title): {f}")
                    except Exception:
                        pass

        except Exception as e:
            print(f"⚠️ Error deleting files: {e}")

    def _show_about(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("About FelfelDM")
        dialog.setMinimumWidth(420)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.setContentsMargins(25, 25, 25, 20)

        icon_label = QLabel()
        icon_path = get_resource_path("logo/icon512.png")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                icon_label.setPixmap(
                    pixmap.scaled(
                        80,
                        80,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon_label)

        title = QLabel("<h1 style='color: #e74c3c;'>🌶️ FelfelDM</h1>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        desc = QLabel(
            "<p style='font-size: 14px;'>A modern download manager</p>"
            "<p style='font-size: 12px; color: #888;'>Built with PyQt6 and aria2</p>"
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        layout.addSpacing(10)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        update_btn = QPushButton(" Update")
        update_btn.setIcon(get_icon("system-software-update"))
        update_btn.setMinimumWidth(120)
        update_btn.clicked.connect(lambda: self._show_update_dialog(dialog))

        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(dialog.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(update_btn)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        dialog.exec()

    def _show_update_dialog(self, parent_dialog: Optional[QDialog] = None) -> None:
        if parent_dialog:
            parent_dialog.accept()

        update_dialog = UpdateDialog(self)
        update_dialog.exec()

    def _pause_all_downloads(self) -> None:
        for q in self.store.queues:
            for gid in q.downloads:
                try:
                    if gid in self._all_downloads:
                        status = self._all_downloads[gid].get("status", "")
                        if status in ["active", "waiting"]:
                            self.aria2.pause(gid)
                            self._all_downloads[gid]["status"] = "paused"
                            self._all_downloads[gid]["downloadSpeed"] = 0
                except Exception:
                    pass

    def _move_queue_up(self) -> None:
        current_row = self.queue_list.currentRow()
        if current_row <= 0:
            return

        self.store.queues.insert(current_row - 1, self.store.queues.pop(current_row))
        self._current_queue_idx = current_row - 1

        self.store.save()
        self._refresh_queue_list()
        self.queue_list.setCurrentRow(self._current_queue_idx)
        self._on_queue_changed(self._current_queue_idx)

    def _move_queue_down(self) -> None:
        current_row = self.queue_list.currentRow()
        if current_row < 0 or current_row >= len(self.store.queues) - 1:
            return

        self.store.queues.insert(current_row + 1, self.store.queues.pop(current_row))
        self._current_queue_idx = current_row + 1

        self.store.save()
        self._refresh_queue_list()
        self.queue_list.setCurrentRow(self._current_queue_idx)
        self._on_queue_changed(self._current_queue_idx)

    def _update_download_size(self, gid: str) -> None:
        """Update download size after resume"""
        status_data = self.aria2.get_status(gid)
        if status_data and isinstance(status_data, dict):
            total = int(status_data.get("totalLength", 0))
            if total > 0 and gid in self._all_downloads:
                self._all_downloads[gid]["totalLength"] = total

                for q in self.store.queues:
                    if gid in q.downloads_info:
                        q.downloads_info[gid]["totalLength"] = total
                        break
                self.store.save()
                self._refresh_table()
                print(f"📏 Updated size for {gid}: {total} bytes")

    def _to_int(self, value: Any) -> int:
        """Convert any value to int safely"""
        try:
            if value is None:
                return 0
            if isinstance(value, str):
                return int(value) if value.strip() else 0
            return int(value) if value else 0
        except (ValueError, TypeError):
            return 0