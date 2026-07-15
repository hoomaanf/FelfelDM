# ui/main_window.py

import os
import time
import subprocess
import tempfile
import threading


from datetime import datetime
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

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
    def __init__(self):
        super().__init__()

        self.store = DataStore()
        self.temp_db = TempDB()
        self._pending_size_fetch = {}
        self._shutdown_timer = None
        self._shutdown_countdown = 20
        self._shutdown_dialog = None
        self._shutdown_dialog_shown = False

        theme_setting = self.store.settings.get("theme", "auto")
        is_dark = True

        if theme_setting == "light":
            is_dark = False
        elif theme_setting == "dark":
            is_dark = True
        elif theme_setting == "auto":

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
                        is_dark = brightness < 128
            except:
                is_dark = True

        from ui.splash import SplashScreen

        self.splash = SplashScreen(is_dark=is_dark)
        self.splash.update_status("Loading FelfelDM...", 5)
        QApplication.processEvents()

        self.setWindowTitle("FelfelDM")
        self.setMinimumSize(1050, 680)

        self.splash.update_status("Loading data...", 15)
        QApplication.processEvents()

        self._pending_pause = set()

        self.splash.update_status("Setting up queues...", 25)
        QApplication.processEvents()

        default_exists = False
        for q in self.store.queues:
            if q.name == "Default":
                default_exists = True
                break

        if not default_exists:
            default_queue = Queue("Default", paused=True)
            self.store.queues.insert(0, default_queue)
            self.store.save()

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

        self._current_queue_idx = 0
        self._all_downloads = {}
        self._last_calculated_global_speed = 0
        self._cleared_gids = set()

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

        self.splash.update_status("Waiting for aria2...", 92)
        QApplication.processEvents()
        QTimer.singleShot(500, self._delayed_restore)

        self.splash.update_status("Starting local server...", 95)
        QApplication.processEvents()
        self.local_server = LocalServer(main_window=self)
        self.local_server.start(8766)

        self.splash.update_status("Ready!", 100)
        QApplication.processEvents()

        QTimer.singleShot(800, self._close_splash)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("splitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(4)

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

        self.speed_lbl = QLabel("↓ 0 B/s")
        status_lay.addWidget(self.speed_lbl)

        self.schedule_status_lbl = QLabel("")
        self.schedule_status_lbl.setStyleSheet("color: #3498db; font-size: 11px;")
        self.schedule_status_lbl.setWordWrap(True)
        status_lay.addWidget(self.schedule_status_lbl)

        sb_lay.addWidget(status_group)
        sb_lay.addStretch()

        main_area = QWidget()
        ma_lay = QVBoxLayout(main_area)
        ma_lay.setContentsMargins(0, 0, 0, 0)
        ma_lay.setSpacing(0)

        toolbar = QWidget()
        tb_lay = QHBoxLayout(toolbar)
        toolbar.setObjectName("toolbar")
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
        self.btn_toggle.setEnabled(False)  # Disabled initially
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

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        # self.progress_bar.setFixedWidth(500)
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

        splitter.addWidget(sidebar)
        splitter.addWidget(main_area)
        splitter.setSizes([210, 840])

        root.addWidget(splitter)

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

        self._refresh_queue_list()
        self._update_queue_buttons()

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self)

        icon_paths = [
            get_resource_path("logo/icon512.png"),
        ]

        icon_set = False
        for path in icon_paths:
            if os.path.exists(path):
                self.tray.setIcon(QIcon(path))
                icon_set = True
                print(f"✅ Tray icon loaded from: {path}")
                break

        if not icon_set:

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

    def closeEvent(self, event):
        """Handle close event - allow closing main window while downloads continue"""
        has_active = False

        for q in self.store.queues:
            for gid in q.downloads:
                real_status = self.aria2.get_status(gid)

                if not real_status:
                    if gid in self._all_downloads:
                        real_status = self._all_downloads[gid].get("status")
                    else:
                        continue

                if real_status in ["active", "waiting"]:
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
                self._pause_all_downloads()

                self.hide()
                self.tray.showMessage(
                    "FelfelDM",
                    "Downloads are running in the background.\n"
                    "Double-click the tray icon to show the main window.",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
                event.ignore()
                return

        # If no active downloads or user said close
        if hasattr(self, "tray") and self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            self.quit_app()
            event.accept()

    def quit_app(self):
        """Quit application and close all windows"""
        print("🛑 Shutting down...")

        print("⏸️ Pausing all downloads...")
        for q in self.store.queues:
            for gid in q.downloads:
                try:
                    real_status = self.aria2.get_status(gid)
                    if real_status in ["active", "waiting"]:
                        self.aria2.pause(gid)
                        print(f"⏸️ Paused: {gid}")
                        if gid in self._all_downloads:
                            self._all_downloads[gid]["status"] = "paused"
                            self._all_downloads[gid]["downloadSpeed"] = 0
                        if gid in q.downloads_info:
                            q.downloads_info[gid]["status"] = "paused"
                except Exception as e:
                    print(f"⚠️ Could not pause {gid}: {e}")

        self.store.save()
        print("💾 Data saved with paused status")

        if hasattr(self, "_progress_dialog") and self._progress_dialog is not None:
            try:
                self._progress_dialog.close()
            except:
                pass
            self._progress_dialog = None

        if hasattr(self, "_youtube_dialog") and self._youtube_dialog is not None:
            try:
                self._youtube_dialog.close()
            except:
                pass
            self._youtube_dialog = None

        # Kill all background
        if hasattr(self, "worker"):
            self.worker.terminate()

        try:
            subprocess.run(["pkill", "-9", "aria2c"], capture_output=True)
        except:
            pass

        if hasattr(self, "tray"):
            self.tray.hide()

        import sys

        sys.exit(0)

    def _restore_downloads_with_progress(self):
        """Restore downloads with progress updates"""
        print("🔄 Restoring downloads...")
        restored_count = 0
        total_downloads = sum(len(q.downloads) for q in self.store.queues)

        if total_downloads == 0:
            if self.splash is not None:
                self.splash.update_status("No downloads to restore", 95)
                QApplication.processEvents()
            return

        wait_count = 0
        while not self.aria2.is_connected() and wait_count < 25:
            time.sleep(0.2)
            wait_count += 1

        if not self.aria2.is_connected():
            print("⚠️ aria2 not ready, skipping restore")
            if self.splash is not None:
                self.splash.update_status("aria2 not ready, skipping restore", 95)
                QApplication.processEvents()
            return

        processed = 0
        for q in self.store.queues:
            for gid in q.downloads[:]:
                processed += 1
                progress = 92 + int((processed / total_downloads) * 8)

                if self.splash is not None:
                    self.splash.update_status(
                        f"Restoring... ({processed}/{total_downloads})", progress
                    )
                    QApplication.processEvents()

                if gid in self._all_downloads:
                    download_type = self._all_downloads[gid].get(
                        "download_type", "normal"
                    )
                    if download_type == "youtube":
                        print(f"⏭️ Skipping YouTube download restore: {gid}")
                        continue

                try:
                    status = self.aria2.get_status(gid)
                except:
                    status = None

                if not status:
                    info = q.downloads_info.get(gid, {})
                    url = info.get("url")

                    if url:
                        print(f"🔄 Restoring: {info.get('name', url)}")

                        options = {
                            "dir": q.save_path,
                            "split": "8",
                            "max-connection-per-server": "8",
                            "continue": "true",
                            "always-resume": "true",
                        }

                        try:
                            new_gid = self.aria2.add_url(url, options)
                        except:
                            new_gid = None

                        if new_gid:
                            idx = q.downloads.index(gid)
                            q.downloads[idx] = new_gid

                            old_info = info.copy()
                            if gid in q.downloads_info:
                                q.downloads_info.pop(gid, None)
                            q.downloads_info[new_gid] = old_info

                            self._all_downloads[new_gid] = {
                                "gid": new_gid,
                                "name": old_info.get(
                                    "name", url.split("/")[-1] or "Unknown"
                                ),
                                "status": "paused",
                                "totalLength": old_info.get("totalLength", 0),
                                "completedLength": old_info.get("completedLength", 0),
                                "downloadSpeed": 0,
                                "connections": 0,
                                "files": old_info.get("files", []),
                                "errorMessage": "",
                                "category": old_info.get("category", "📁 Other"),
                            }

                            try:
                                self.aria2.pause(new_gid)
                                print(
                                    f"⏸️ Restored as paused: {old_info.get('name', url)}"
                                )
                            except:
                                pass

                            restored_count += 1
                        else:
                            print(f"⚠️ Failed to restore: {url}")
                            q.downloads.remove(gid)
                            if gid in q.downloads_info:
                                del q.downloads_info[gid]
                    else:
                        print(f"⚠️ No URL for GID {gid}, removing...")
                        q.downloads.remove(gid)
                        if gid in q.downloads_info:
                            del q.downloads_info[gid]

        if restored_count > 0:
            self.store.save()
            print(f"✅ Restored {restored_count} download(s)")

        if self.splash is not None:
            self.splash.update_status("Ready!", 100)
            QApplication.processEvents()

    def _delayed_restore(self):
        """Delay restore until aria2 is fully ready"""
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

    def _on_queue_changed(self, idx):
        if idx >= 0:
            self._current_queue_idx = idx
            self._update_queue_status()
            self._update_queue_buttons()
            self._update_shutdown_button_state()
            self._refresh_table()

    def _current_queue(self):
        if 0 <= self._current_queue_idx < len(self.store.queues):
            return self.store.queues[self._current_queue_idx]
        return None

    def _update_queue_buttons(self):
        q = self._current_queue()

        if not q or len(q.downloads) == 0:
            self.start_queue_btn.setEnabled(False)
            self.pause_queue_btn.setEnabled(False)
            return

        if q.name == "__direct__":
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

                if status in ["active", "waiting", "downloading"]:
                    has_downloading = True
                elif status == "pending":
                    has_pending = True
                elif status == "paused":
                    has_paused = True
                elif status == "waiting":
                    has_waiting = True
                elif status == "error":
                    has_error = True

        all_done = True
        for gid in q.downloads:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                if status not in ["complete", "completed", "error", "removed"]:
                    all_done = False
                    break
            else:
                all_done = False
                break

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

    def _refresh_queue_list(self):
        self.queue_list.blockSignals(True)
        self.queue_list.clear()
        for q in self.store.queues:
            if len(q.downloads) == 0:
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
        self.store.save()

    def _update_queue_status(self):
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
            self.queue_status_lbl.setText(f"✅ Complete")
            self.queue_status_lbl.setStyleSheet("color: #27ae60; font-weight: bold;")
            self.schedule_status_lbl.setText("")
            self.status_label.setText("✅ All downloads complete")
            return

        if q.schedule_enabled:
            if q.is_scheduled_now():
                if not q.paused:
                    has_active = False
                    for gid in q.downloads:
                        if gid in self._all_downloads:
                            status = self._all_downloads[gid].get("status", "")
                            if status in ["active", "waiting", "downloading"]:
                                has_active = True
                                break
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
                    time_str = next_time.strftime("%H:%M on %A")
                    self.schedule_status_lbl.setText(f"⏰ Next: {time_str}")
                else:
                    self.schedule_status_lbl.setText(
                        f"⏰ Next: {q.schedule_start.strftime('%H:%M')}-{q.schedule_end.strftime('%H:%M')} {days_text}"
                    )
                self.schedule_status_lbl.setStyleSheet(
                    "color: #3498db; font-size: 11px;"
                )

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
        else:
            if q.paused:
                has_resumable = False
                for gid in q.downloads:
                    if gid in self._all_downloads:
                        status = self._all_downloads[gid].get("status", "")
                        if status in ["paused", "waiting"]:
                            has_resumable = True
                            break

                if has_resumable:
                    self.queue_status_lbl.setText(f"⏸ Paused{speed_limit_text}")
                    self.queue_status_lbl.setStyleSheet(
                        "color: #f39c12; font-weight: bold;"
                    )
                    self.schedule_status_lbl.setText(
                        "Click 'Start' to resume downloads"
                    )
                    self.status_label.setText("⏸ Paused")
                else:
                    self.queue_status_lbl.setText(f"⏸ Paused{speed_limit_text}")
                    self.queue_status_lbl.setStyleSheet(
                        "color: #95a5a6; font-weight: bold;"
                    )
                    self.schedule_status_lbl.setText("")
                    self.status_label.setText("⏸ Paused")
            else:
                has_active = False
                for gid in q.downloads:
                    if gid in self._all_downloads:
                        status = self._all_downloads[gid].get("status", "")
                        if status in ["active", "waiting", "downloading"]:
                            has_active = True
                            break

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

    def _start_current_queue(self):
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

        for gid in q.downloads:
            if gid in self._all_downloads:
                total = self._all_downloads[gid].get("totalLength", 0)
                self._all_downloads[gid]["error_count"] = 0
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

            if download_type == "youtube":
                real_status = self._all_downloads[gid].get("status", "")
                if real_status in ["paused"]:
                    self._start_youtube_download(gid)
                    self._all_downloads[gid]["status"] = "downloading"
                    resumed += 1
            else:
                status_data = self.aria2.get_status(gid)

                if status_data and isinstance(status_data, dict):
                    real_status = status_data.get("status", "unknown")
                else:
                    real_status = self._all_downloads.get(gid, {}).get(
                        "status", "waiting"
                    )

                print(f"🔍 [START] GID: {gid}, Status: {real_status}")

                if real_status in ["paused", "waiting", "error"]:
                    if q and getattr(q, "speed_limit", 0) > 0:
                        time.sleep(0.3)
                        self.aria2.set_download_speed_limit(gid, q.speed_limit)
                        print(
                            f"⚡ Queue speed limit {q.speed_limit}KB/s applied to {gid}"
                        )

                    result = self.aria2.resume(gid)
                    if result is not None:
                        resumed += 1
                        if gid in self._all_downloads:
                            self._all_downloads[gid]["status"] = "active"
                        if gid in q.downloads_info:
                            q.downloads_info[gid]["status"] = "active"
                        print(f"✅ Resumed: {gid}")
                    else:
                        info = q.downloads_info.get(gid, {})
                        url = info.get("url")
                        if url:
                            print(f"🔄 GID {gid} invalid, re-adding: {url[:50]}...")
                            new_gid = self.aria2.add_url(url, {"dir": q.save_path})
                            if new_gid:
                                idx = q.downloads.index(gid)
                                q.downloads[idx] = new_gid
                                if gid in q.downloads_info:
                                    q.downloads_info[new_gid] = q.downloads_info.pop(
                                        gid
                                    )
                                if gid in self._all_downloads:
                                    self._all_downloads[new_gid] = (
                                        self._all_downloads.pop(gid)
                                    )
                                self.aria2.resume(new_gid)
                                resumed += 1
                                print(f"✅ Re-added with new GID: {new_gid}")
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

    def _pause_current_queue(self):
        q = self._current_queue()
        if not q:
            return

        if q.name == "__direct__":
            return

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
                status_data = self.aria2.get_status(gid)

                if status_data and isinstance(status_data, dict):
                    real_status = status_data.get("status", "")
                else:
                    real_status = self._all_downloads.get(gid, {}).get("status", "")

                if real_status in ["active", "waiting"]:
                    self.aria2.pause(gid)
                    paused += 1

                if gid in self._all_downloads:
                    self._all_downloads[gid]["status"] = "paused"
                    self._all_downloads[gid]["downloadSpeed"] = 0

                if gid in q.downloads_info:
                    q.downloads_info[gid]["status"] = "paused"

        self._last_calculated_global_speed = 0
        self.speed_lbl.setText("↓ 0 B/s")
        self.tray.setToolTip("FelfelDM — ↓ 0 B/s")

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

    def _clear_completed_downloads(self):
        q = self._current_queue()
        if not q:
            return

        completed_gids = []
        for gid in q.downloads:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                if status in ["complete", "completed", "✅ Complete"]:
                    completed_gids.append(gid)

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

    def _update_progress_bar(self):
        q = self._current_queue()
        total_size = 0
        completed_size = 0

        if not q or q.name == "__direct__":
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("Direct Downloads — no queue")
            return

        if q:
            for gid in q.downloads:
                if gid in self._all_downloads:
                    row = self._all_downloads[gid]
                    total_size += int(row.get("totalLength", 0))
                    completed_size += int(row.get("completedLength", 0))

        speed_texts = []

        global_limit = self.store.settings.get("speed_limit", 0)
        if global_limit > 0:
            if global_limit >= 1024:
                speed_texts.append(f"Global: {global_limit//1024} MB/s")
            else:
                speed_texts.append(f"Global: {global_limit} KB/s")

        if q and getattr(q, "speed_limit", 0) > 0:
            q_limit = q.speed_limit
            if q_limit >= 1024:
                speed_texts.append(f"Queue: {q_limit//1024} MB/s")
            else:
                speed_texts.append(f"Queue: {q_limit} KB/s")

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

    def _add_queue(self):
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

    def _edit_queue(self):
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
            print(f"📊 Dialog returned: {d}")
            print(f"📊 speed_limit in dialog: {d.get('speed_limit', 'NOT FOUND')}")
            q.name = d["name"]
            q.save_path = d["save_path"]
            q.max_concurrent = d["max_concurrent"]
            self.store.settings["max_concurrent"] = d["max_concurrent"]
            q.schedule_enabled = d["schedule_enabled"]
            q.schedule_start = d["schedule_start"]
            q.schedule_end = d["schedule_end"]
            q.days = d["days"]

            q.speed_limit = d.get("speed_limit", 0)
            print(f"📊 speed_limit saved: {q.speed_limit}")

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

    def _delete_queue(self):
        q = self._current_queue()
        if not q:
            return

        if len(self.store.queues) <= 1:
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
    def _add_downloads_from_extension(self, urls):
        if not urls:
            return

        if len(urls) == 1:
            all_queues = self.store.queues
            dlg = QuickDownloadDialog(all_queues, self)
            dlg.url_edit.setPlainText(urls[0])
            dlg.setWindowModality(Qt.WindowModality.WindowModal)

            if dlg.exec():
                d = dlg.get_data()
                if not d["urls"]:
                    return

                # ===== دریافت صف انتخاب شده از دیالوگ =====
                queue_name = d.get("queue_name", "__direct__")
                target_queue = None

                for q in self.store.queues:
                    if q.name == queue_name:
                        target_queue = q
                        break

                # ===== اگه صف وجود نداشت، بساز =====
                if target_queue is None:
                    target_queue = Queue(queue_name, paused=False)
                    if queue_name == "__direct__":
                        target_queue.max_concurrent = 99
                    self.store.queues.insert(0, target_queue)
                    self.store.save()
                elif queue_name == "__direct__":
                    target_queue.paused = False

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
                    gid = self.aria2.add_url(url, options)
                    if gid:
                        target_queue.downloads.append(gid)
                        raw_name = url.split("/")[-1]
                        clean_name = (
                            raw_name.split("?")[0] if "?" in raw_name else raw_name
                        )
                        if not clean_name:
                            clean_name = "Unknown"
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

                        # ===== Pause نگه دار (مگر اینکه __direct__ باشه) =====
                        if queue_name == "__direct__":
                            self.aria2.resume(gid)
                        else:
                            self.aria2.pause(gid)
                            if gid in self._all_downloads:
                                self._all_downloads[gid]["status"] = "paused"
                                self._all_downloads[gid]["downloadSpeed"] = 0

                        added_gids.append(gid)

                self.store.save()
                self._refresh_queue_list()
                self._refresh_table()
                self._update_shutdown_button_state()

                # ===== پیام مناسب =====
                if queue_name == "__direct__":
                    self.tray.showMessage(
                        "FelfelDM",
                        f"✅ Added {len(added_gids)} download(s) to Direct Downloads",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000,
                    )
                else:
                    self.tray.showMessage(
                        "FelfelDM",
                        f"✅ Added {len(added_gids)} download(s) to '{queue_name}' (paused)",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000,
                    )

                if len(added_gids) == 1 and queue_name == "__direct__":
                    QTimer.singleShot(
                        500, lambda: self._open_progress_dialog(added_gids[0])
                    )
            return

        # ===== چندین URL =====
        visible_queues = [q for q in self.store.queues if q.name != "__direct__"]

        default_idx = 0
        for i, q in enumerate(visible_queues):
            if q.name == "Default":
                default_idx = i
                break

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
                gid = self.aria2.add_url(url, options)
                if gid:
                    if gid in self._cleared_gids:
                        self._cleared_gids.remove(gid)
                    q.downloads.append(gid)

                    # Save URL for restore
                    q.downloads_info[gid] = {
                        "url": url,
                        "name": url.split("/")[-1] or "Unknown",
                    }

                    new_gids.append(gid)
                    added += 1

                    # ===== همیشه Pause کن (چون __direct__ نیست) =====
                    self.aria2.pause(gid)
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "paused"
                        self._all_downloads[gid]["downloadSpeed"] = 0

            self.store.save()
            self._refresh_queue_list()
            self._update_queue_buttons()

            # ===== هیچوقت Resume نکن (چون __direct__ نیست) =====
            self._refresh_table()
            self.tray.showMessage(
                "FelfelDM",
                f"✅ Added {added} download(s) to '{q.name}' (paused)",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )

            self._refresh_table()

    def _add_download(self):
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
                    print(
                        f"🌐 Using queue/global proxy for {q.name}: {proxy._build_proxy_url()}"
                    )
            elif proxy_mode == 1:
                custom_proxy = d.get("custom_proxy")
                if custom_proxy and custom_proxy.is_valid():
                    options["all-proxy"] = custom_proxy._build_proxy_url()
                    print(f"🔧 Using custom proxy: {custom_proxy._build_proxy_url()}")
            elif proxy_mode == 2:
                options["all-proxy"] = ""
                print(f"⛔ No proxy for this download")
            else:
                proxy = self.proxy_manager.get_proxy_for_queue(q.name)
                if proxy and proxy.is_valid():
                    options["all-proxy"] = proxy._build_proxy_url()

            added = 0
            new_gids = []
            for url in d["urls"]:
                gid = self.aria2.add_url(url, options)
                if gid:
                    if gid in self._cleared_gids:
                        self._cleared_gids.remove(gid)
                    q.downloads.append(gid)

                    raw_name = url.split("/")[-1]
                    clean_name = raw_name.split("?")[0] if "?" in raw_name else raw_name
                    if not clean_name:
                        clean_name = "Unknown"
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
                    self._pending_pause.add(gid)

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
                    }

                    paused_successfully = False
                    for attempt in range(5):
                        time.sleep(0.15)

                        try:
                            status_data = self.aria2.get_status(gid)
                            if status_data is not None and isinstance(
                                status_data, dict
                            ):
                                real_status = status_data.get("status", "")
                                if real_status != "paused":
                                    result = self.aria2.pause(gid)
                                    if result is not None:
                                        paused_successfully = True
                                        print(
                                            f"⏸️ Paused successfully after {attempt+1} attempts: {gid}"
                                        )
                                        break
                                    else:
                                        print(
                                            f"⚠️ Pause returned None for {gid} (attempt {attempt+1})"
                                        )
                                else:
                                    paused_successfully = True
                                    print(f"⏸️ Already paused: {gid}")
                                    break
                            else:
                                print(
                                    f"⚠️ GID {gid} not ready yet (attempt {attempt+1})"
                                )
                        except Exception as e:
                            print(f"⚠️ Error on attempt {attempt+1} for {gid}: {e}")

                    if not paused_successfully:
                        print(
                            f"⚠️ Could not pause {gid} after 5 attempts, but download is added"
                        )

                    if gid in self._pending_pause:
                        self._pending_pause.remove(gid)

                    if q and getattr(q, "speed_limit", 0) > 0:
                        time.sleep(0.3)
                        self.aria2.set_download_speed_limit(gid, q.speed_limit)
                        print(
                            f"⚡ Queue speed limit {q.speed_limit}KB/s applied to {gid} (on add)"
                        )

            self._refresh_table()
            self.store.save()
            self._refresh_queue_list()
            self._update_queue_buttons()
            self._update_shutdown_button_state()

            if q and not q.paused and q.is_scheduled_now():
                all_has_size = True
                for gid in new_gids:
                    if gid in self._all_downloads:
                        total = self._all_downloads[gid].get("totalLength", 0)
                        if total == 0:
                            all_has_size = False
                            break

                if all_has_size:
                    for gid in new_gids:
                        if gid in self._all_downloads:
                            self.aria2.resume(gid)
                            self._all_downloads[gid]["status"] = "active"
                    self._refresh_table()
                    self.tray.showMessage(
                        "FelfelDM",
                        f"✅ Added {added} download(s) to running queue",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000,
                    )
                else:
                    self.tray.showMessage(
                        "FelfelDM",
                        f"✅ Added {added} download(s) (waiting for size)",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000,
                    )
            elif added > 0:
                self.tray.showMessage(
                    "FelfelDM",
                    f"✅ Added {added} download(s) in paused state",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )

            self._refresh_table()

    def _add_single_download(self):
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

            # === Proxy handling ===
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

            # Add proxy based on selection
            proxy_mode = data.get("proxy_mode", 0)
            if proxy_mode == 0:  # Use global/queue proxy
                # Get proxy from queue or global
                proxy = self.proxy_manager.get_proxy_for_queue("Single Downloads")
                if proxy and proxy.is_valid():
                    options["all-proxy"] = proxy._build_proxy_url()
            elif proxy_mode == 1:  # Custom proxy
                custom_proxy = data.get("custom_proxy")
                if custom_proxy and custom_proxy.is_valid():
                    options["all-proxy"] = custom_proxy._build_proxy_url()
            # mode 2: No proxy - don't add any proxy

            gid = self.aria2.add_url(data["url"], options)

            if gid:
                single_queue = None
                for q in self.store.queues:
                    if q.name == "Single Downloads":
                        single_queue = q
                        break

                if not single_queue:
                    single_queue = Queue(
                        "Single Downloads", paused=False, max_concurrent=1
                    )
                    self.store.queues.append(single_queue)

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

    def _pause_selected(self):
        gid = self._selected_gid()
        if not gid:
            return

        real_status = self.aria2.get_status(gid)
        if real_status in ["active", "waiting"]:
            self.aria2.pause(gid)
            if gid in self._all_downloads:
                self._all_downloads[gid]["status"] = "paused"
                self._all_downloads[gid]["downloadSpeed"] = 0

            q = self._current_queue()
            if q and gid in q.downloads_info:
                q.downloads_info[gid]["status"] = "paused"
                self.store.save()

            if q and q.name != "__direct__":
                has_active = False
                for other_gid in q.downloads:
                    if other_gid != gid and other_gid in self._all_downloads:
                        status = self._all_downloads[other_gid].get("status", "")
                        if status in ["active", "waiting"]:
                            has_active = True
                            break

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

    def _resume_selected(self):
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

        real_status = self.aria2.get_status(gid)
        if real_status == "paused":
            self.aria2.resume(gid)
            if gid in self._all_downloads:
                self._all_downloads[gid]["status"] = "active"

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

    def _remove_selected(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "Info", "No downloads selected.")
            return

        count = len(selected)

        dlg = QDialog(self)
        dlg.setWindowTitle("Remove Downloads")
        dlg.setMinimumWidth(500)
        dlg.setModal(True)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel(f"Remove {count} download(s)?")
        layout.addWidget(title)

        info = QLabel("Choose what to do with the downloaded files:")
        layout.addWidget(info)

        layout.addSpacing(10)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

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

        removed = 0
        gids_to_remove = []
        for idx in selected:
            gid = self.model.get_gid(idx.row())
            if gid:
                gids_to_remove.append(gid)

        for gid in gids_to_remove:
            file_paths = []
            download_path = None

            for q in self.store.queues:
                if gid in q.downloads_info:
                    info = q.downloads_info[gid]
                    download_path = q.save_path
                    name = info.get("name", "")
                    files = info.get("files", [])
                    for f in files:
                        path = f.get("path")
                        if path:
                            file_paths.append(path)
                    if not file_paths and name and download_path:
                        possible_path = os.path.join(download_path, name)
                        if os.path.exists(possible_path):
                            file_paths.append(possible_path)
                    break

            if not file_paths and gid in self._all_downloads:
                dl = self._all_downloads[gid]
                name = dl.get("name", "")
                files = dl.get("files", [])
                for f in files:
                    path = f.get("path")
                    if path:
                        file_paths.append(path)
                if not file_paths and name:
                    for q in self.store.queues:
                        if gid in q.downloads:
                            possible_path = os.path.join(q.save_path, name)
                            if os.path.exists(possible_path):
                                file_paths.append(possible_path)
                            break

            try:
                self.aria2.remove(gid)
            except Exception as e:
                print(f"⚠ Could not remove GID {gid} from aria2: {e}")

            try:
                self.aria2._call("aria2.removeDownloadResult", [gid])
            except Exception as e:
                print(f"⚠ Could not remove result for {gid}: {e}")

            for q in self.store.queues:
                if gid in q.downloads:
                    q.downloads.remove(gid)
                if gid in q.downloads_info:
                    del q.downloads_info[gid]

            if gid in self._all_downloads:
                del self._all_downloads[gid]

            if delete_files:
                file_paths = []
                save_path = None
                base_name = None

                print(f"🔍 [REMOVE START] GID: {gid}")

                print("🔎 Searching in downloads_info...")
                for q in self.store.queues:
                    if gid in q.downloads_info:
                        info = q.downloads_info[gid]
                        save_path = q.save_path
                        name = info.get("name", "").strip()
                        print(
                            f"✅ Found in downloads_info → save_path: {save_path} | name: {name}"
                        )
                        if name:
                            base_name = os.path.splitext(name)[0]
                        break

                if not save_path and gid in self._all_downloads:
                    print("🔎 Searching in _all_downloads...")
                    for q in self.store.queues:
                        if gid in q.downloads:
                            save_path = q.save_path
                            print(f"✅ Found save_path from queue: {save_path}")
                            break

                # 3. fallback به Downloads
                if not save_path or not os.path.exists(save_path):
                    save_path = os.path.expanduser("~/Downloads")
                    print(f"📁 Using default Downloads folder: {save_path}")

                if save_path and os.path.exists(save_path):
                    print(f"🔎 Listing files in: {save_path}")
                    try:
                        files_list = os.listdir(save_path)
                        print(f"📋 Total files in folder: {len(files_list)}")
                        for file in files_list:
                            full_path = os.path.join(save_path, file)
                            lower = file.lower()

                            if base_name and base_name.lower() in lower:
                                file_paths.append(full_path)
                                print(f"✅ MATCH base_name: {file}")
                            elif gid in file:
                                file_paths.append(full_path)
                                print(f"✅ MATCH GID: {file}")
                            elif any(
                                x in lower
                                for x in [
                                    ".part",
                                    ".f",
                                    ".webm",
                                    ".mp4",
                                    ".mkv",
                                    ".m4a",
                                    ".opus",
                                ]
                            ):
                                file_paths.append(full_path)
                                print(f"✅ MATCH yt-dlp pattern: {file}")
                    except Exception as e:
                        print(f"⚠ Dir list error: {e}")
                else:
                    print(f"⚠ Save path not found or not accessible: {save_path}")

                print(f"📊 Total candidate files: {len(set(file_paths))}")

                for path in set(file_paths):
                    try:
                        if os.path.exists(path):
                            if os.path.isfile(path):
                                os.remove(path)
                                print(f"🗑 DELETED SUCCESS: {os.path.basename(path)}")
                            elif os.path.isdir(path):
                                import shutil

                                shutil.rmtree(path)
                                print(f"🗑 DELETED folder: {path}")
                    except Exception as e:
                        print(f"⚠ Delete failed {path}: {e}")

                if save_path and os.path.exists(save_path):
                    print("🧹 Cleaning temp files...")
                    try:
                        for file in os.listdir(save_path):
                            if any(
                                x in file
                                for x in [".part", ".aria2", ".ytdl", ".temp", ".f"]
                            ):
                                full = os.path.join(save_path, file)
                                if os.path.exists(full):
                                    os.remove(full)
                                    print(f"🗑 DELETED temp: {file}")
                    except Exception as e:
                        print(f"⚠ Temp cleanup error: {e}")

            removed += 1

        self.store.save()
        self._refresh_table()
        self._refresh_queue_list()
        self._update_queue_buttons()

        if removed > 0:
            msg_text = f"Removed {removed} download(s)"
            if delete_files:
                msg_text += " (files and .aria2 files deleted)"
            self.tray.showMessage(
                "FelfelDM", msg_text, QSystemTrayIcon.MessageIcon.Information, 2000
            )

    def _selected_gid(self):
        """Get selected download GID"""
        idx = self.table.currentIndex()
        if idx.isValid():
            return self.model.get_gid(idx.row())
        return None

    def _context_menu(self, pos):
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
        download_name = dl_data.get("name", "Unknown")
        download_type = dl_data.get("download_type", "normal")

        # Get real status from aria2 or youtube
        if download_type == "youtube":
            real_status = dl_data.get("status", "")
        else:
            real_status = self.aria2.get_status(gid)
            if not real_status:
                real_status = dl_data.get("status", "")

        menu = QMenu(self)

        # Single Pause/Resume option based on real status
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
        elif real_status in ["paused"]:
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

        # ===== Open Folder =====
        def _open_folder():
            try:
                folder_path = None
                print(f"🔍 [OpenFolder] Looking for folder for GID: {gid}")

                # 1. از _all_downloads
                if gid in self._all_downloads:
                    dl = self._all_downloads[gid]
                    files = dl.get("files", [])
                    if files and files[0].get("path"):
                        folder_path = os.path.dirname(files[0]["path"])
                        print(f"📂 [OpenFolder] Found in _all_downloads: {folder_path}")

                # 2. از queue info
                if not folder_path:
                    for q in self.store.queues:
                        if gid in q.downloads_info:
                            info = q.downloads_info[gid]
                            files = info.get("files", [])
                            if files and files[0].get("path"):
                                folder_path = os.path.dirname(files[0]["path"])
                                print(
                                    f"📂 [OpenFolder] Found in queue info: {folder_path}"
                                )
                                break
                            elif q.save_path and os.path.exists(q.save_path):
                                folder_path = q.save_path
                                print(
                                    f"📂 [OpenFolder] Using queue save_path: {folder_path}"
                                )
                                break

                # 3. از YouTube
                if not folder_path:
                    saved_data = self.store.get_youtube_download(gid)
                    if saved_data:
                        folder_path = saved_data.get("save_path", "")
                        if folder_path and os.path.exists(folder_path):
                            print(f"📂 [OpenFolder] Found in YouTube: {folder_path}")

                # 4. fallback به Downloads
                if not folder_path or not os.path.exists(folder_path):
                    folder_path = os.path.expanduser("~/Downloads")
                    print(f"📂 [OpenFolder] Using fallback: {folder_path}")

                # باز کردن
                if folder_path and os.path.exists(folder_path):
                    print(f"✅ [OpenFolder] Opening: {folder_path}")
                    from PyQt6.QtCore import QUrl
                    from PyQt6.QtGui import QDesktopServices

                    QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))
                else:
                    print(f"❌ [OpenFolder] Folder not found: {folder_path}")
                    QMessageBox.warning(
                        self, "Error", f"Folder not found:\n{folder_path}"
                    )

            except Exception as e:
                print(f"❌ [OpenFolder] Error: {e}")
                import traceback

                traceback.print_exc()
                QMessageBox.warning(self, "Error", f"Could not open folder:\n{str(e)}")

        menu.addAction(get_icon("folder"), "Open Folder", _open_folder)

        # ===== Copy URL =====
        def _copy_link():
            saved_data = self.store.get_youtube_download(gid)
            if saved_data:
                QApplication.clipboard().setText(saved_data.get("url", ""))
            else:
                files = dl_data.get("files", [])
                if files and files[0].get("uris"):
                    QApplication.clipboard().setText(files[0]["uris"][0]["uri"])

        menu.addAction(get_icon("edit-copy"), "Copy URL", _copy_link)

        menu.addSeparator()

        # ===== Remove =====
        menu.addAction(
            get_icon("edit-delete"),
            "Remove",
            lambda: (self._remove_selected()),
        )

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _filter_downloads(self, text):
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
                name = row.get("name", "").lower()
                if text.lower() in name:
                    filtered.append(row)

        self.model.update_rows(filtered)

    def _refresh_table(self):
        """به‌روزرسانی جدول با دریافت اطلاعات لحظه‌ای از aria2"""
        q = self._current_queue()
        if not q:
            self.model.update_rows([])
            return

        rows = []
        search_text = self.search_box.text().strip().lower()

        for gid in q.downloads:
            if gid in self._all_downloads:
                row = self._all_downloads[gid].copy()

                if row.get("download_type") != "youtube":
                    status_data = self.aria2.get_status(gid)

                    if status_data and isinstance(status_data, dict):
                        real_status = status_data.get("status", "unknown")
                        total_length = int(status_data.get("totalLength", 0))
                        completed_length = int(status_data.get("completedLength", 0))
                        speed = int(status_data.get("downloadSpeed", 0))

                        row["status"] = real_status
                        row["totalLength"] = (
                            total_length
                            if total_length > 0
                            else row.get("totalLength", 0)
                        )
                        row["completedLength"] = completed_length
                        row["downloadSpeed"] = speed

                        if row["totalLength"] > 0:
                            row["progress"] = int(
                                (row["completedLength"] / row["totalLength"]) * 100
                            )
                        else:
                            row["progress"] = 0

                        if q.paused and real_status not in [
                            "complete",
                            "completed",
                            "error",
                            "removed",
                        ]:
                            row["status"] = "paused"
                            row["downloadSpeed"] = 0

                        self.temp_db.update_download_status(
                            gid=gid,
                            status=row["status"],
                            progress=row["progress"],
                            speed=row["downloadSpeed"],
                            name=row.get("name", "Unknown"),
                            totalLength=row["totalLength"],
                            completedLength=row["completedLength"],
                        )

                        self._all_downloads[gid] = row.copy()

                else:
                    pass

            else:
                info = q.downloads_info.get(gid, {})

                status_data = self.aria2.get_status(gid)

                if status_data and isinstance(status_data, dict):
                    real_status = status_data.get("status", "unknown")
                    total_length = int(status_data.get("totalLength", 0))
                    completed_length = int(status_data.get("completedLength", 0))
                    speed = int(status_data.get("downloadSpeed", 0))

                    name = info.get("name", "Unknown")
                    files = status_data.get("files", [])
                    if files and files[0].get("path"):
                        name = os.path.basename(files[0]["path"])
                    elif files and files[0].get("uris"):
                        name = files[0]["uris"][0]["uri"].split("/")[-1]
                else:
                    real_status = info.get("status", "paused")
                    total_length = info.get("totalLength", 0)
                    completed_length = info.get("completedLength", 0)
                    speed = 0
                    name = info.get("name", "Unknown")

                progress = 0
                if total_length > 0:
                    progress = int((completed_length / total_length) * 100)

                row = {
                    "gid": gid,
                    "name": name,
                    "status": real_status,
                    "progress": progress,
                    "downloadSpeed": speed,
                    "totalLength": total_length,
                    "completedLength": completed_length,
                    "category": info.get("category", "📁 Other"),
                    "download_type": info.get("download_type", "normal"),
                    "files": info.get("files", []),
                }

                if q.paused and real_status not in [
                    "complete",
                    "completed",
                    "error",
                    "removed",
                ]:
                    row["status"] = "paused"
                    row["downloadSpeed"] = 0

                self._all_downloads[gid] = row.copy()
                self.temp_db.update_download_status(
                    gid=gid,
                    status=row["status"],
                    progress=row["progress"],
                    speed=row["downloadSpeed"],
                    name=row["name"],
                    totalLength=row["totalLength"],
                    completedLength=row["completedLength"],
                )

            if search_text and search_text not in row.get("name", "").lower():
                continue

            rows.append(row)

        self.model.update_rows(rows)

    def _update_toggle_button(self):
        """Update toggle button state based on selected download"""
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

        download_type = "normal"
        if gid in self._all_downloads:
            download_type = self._all_downloads[gid].get("download_type", "normal")

        if download_type == "youtube":
            if gid in self._all_downloads:
                real_status = self._all_downloads[gid].get("status", "")
            else:
                real_status = ""
        else:
            real_status = self.aria2.get_status(gid)
            if not real_status and gid in self._all_downloads:
                real_status = self._all_downloads[gid].get("status", "")

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
        else:  # complete, completed, error, removed
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))

    def _toggle_shutdown(self, checked):
        self.store.settings["shutdown_after_finish"] = checked
        self.store.save()

        if not checked and self._shutdown_dialog:
            self._shutdown_dialog.reject()

    def _apply_global_speed_limit(self):
        limit = self.store.settings.get("speed_limit", 0)
        aria_limit = f"{limit}K" if limit > 0 else "0"
        self.aria2.change_global_option({"max-overall-download-limit": aria_limit})

    def _apply_settings_to_aria2(self):
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
        except:
            return False

    def _restart_aria2(self):
        try:
            subprocess.run(["pkill", "-f", "aria2c"], capture_output=True)
            time.sleep(0.5)
        except:
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

    def _open_settings(self):
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

    def _start_backend(self):
        """شروع BackendWorker برای مدیریت دانلودها"""
        print("🚀🚀🚀 _start_backend CALLED")
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

    def _on_stats_received(self, result):
        if not isinstance(result, dict):
            print(f"⚠️ [Stats] Invalid result type: {type(result)}")
            return

        if not result.get("connected"):
            self.status_lbl.setText("● Disconnected")
            self.status_lbl.setStyleSheet("color: #e74c3c; font-weight: bold;")
            self.speed_lbl.setText("↓ 0 B/s")
            self._last_calculated_global_speed = 0
            return

        self.status_lbl.setText("● Connected")
        self.status_lbl.setStyleSheet("color: #27ae60; font-weight: bold;")
        stat = result.get("stat", {})

        total_speed = 0

        q = self._current_queue()
        if q and q.paused:
            total_speed = 0
        else:
            aria2_speed = int(stat.get("downloadSpeed", 0))
            total_speed += aria2_speed

            youtube_downloads = result.get("youtube_downloads", [])
            if isinstance(youtube_downloads, list):
                for yt_data in youtube_downloads:
                    if not isinstance(yt_data, dict):
                        continue

                    speed_str = yt_data.get("speed", "")
                    if speed_str:
                        parsed_speed = self._parse_speed(speed_str)
                        total_speed += parsed_speed

        self._last_calculated_global_speed = total_speed
        self.speed_lbl.setText(f"↓ {format_speed(total_speed)}")
        self.tray.setToolTip(f"FelfelDM — ↓ {format_speed(total_speed)}")

        self._apply_settings_to_aria2()

        # Auto clear completed
        if self.store.settings.get("auto_clear_completed", False):
            q = self._current_queue()
            if q:
                completed_gids = []
                for gid in q.downloads:
                    if gid in self._all_downloads:
                        if self._all_downloads[gid].get("status") == "complete":
                            completed_gids.append(gid)

                if completed_gids:
                    for gid in completed_gids:
                        q.downloads.remove(gid)
                        if gid in self._all_downloads:
                            del self._all_downloads[gid]
                    self.store.save()
                    self._refresh_queue_list()

        self._update_progress_bar()

        # Shutdown check
        if self.shutdown_cb.isChecked():
            total_active = int(stat.get("numActive", 0))
            total_waiting = int(stat.get("numWaiting", 0))

            if total_active == 0 and total_waiting == 0:
                has_any_download = any(q.downloads for q in self.store.queues)

                if has_any_download:
                    for q in self.store.queues:
                        for gid in q.downloads:
                            status = self._all_downloads.get(gid, {}).get(
                                "status", "NOT FOUND"
                            )

                    all_done = all(
                        self._all_downloads.get(gid, {}).get("status")
                        in ["complete", "error", "removed"]
                        for q in self.store.queues
                        for gid in q.downloads
                    )

                    if all_done and not self._shutdown_dialog_shown:
                        self._shutdown_dialog_shown = True
                        self.tray.showMessage(
                            "🌶️ FelfelDM",
                            "✅ All downloads completed!\n🛑 System will shut down in 20 seconds.",
                            QSystemTrayIcon.MessageIcon.Information,
                            5000,
                        )
                        self._show_shutdown_countdown()
                    else:
                        print("⏳ Not all downloads are complete yet")

        # ===== Build saved_info lookup =====
        saved_info_map = {}
        for q in self.store.queues:
            for gid, info in q.downloads_info.items():
                saved_info_map[gid] = info

        # ===== Process downloads =====
        all_downloads_dict = {}

        def process_dl(dl, default_status):
            gid = dl.get("gid")
            if not gid:
                return None

            if gid in self._cleared_gids:
                return None

            saved_info = saved_info_map.get(gid, {})
            saved_total = saved_info.get("totalLength", 0)
            saved_completed = saved_info.get("completedLength", 0)
            saved_name = saved_info.get("name", "")
            saved_status = saved_info.get("status", "")
            saved_category = saved_info.get("category", "📁 Other")

            old_data = self._all_downloads.get(gid, {})
            old_status = old_data.get("status")
            error_count = old_data.get("error_count", 0)

            name = saved_name
            if not name or name == "Unknown":
                files = dl.get("files", [])
                if files and files[0].get("path"):
                    aria2_name = os.path.basename(files[0]["path"])
                    if aria2_name and aria2_name != "Unknown File":
                        name = aria2_name
                elif files and files[0].get("uris"):
                    aria2_name = (
                        files[0]["uris"][0]["uri"].split("/")[-1] or "Unknown File"
                    )
                    if aria2_name and aria2_name != "Unknown File":
                        name = aria2_name

            if not name or name == "Unknown" or name == "Unknown File":
                bittorrent = dl.get("bittorrent", {})
                info = bittorrent.get("info", {})
                name = info.get("name", saved_name or "Unknown File")

            speed = dl.get("downloadSpeed", 0)
            try:
                speed = int(speed)
            except (ValueError, TypeError):
                speed = 0

            total_length = saved_total
            completed_length = saved_completed

            aria2_total = dl.get("totalLength", 0)
            try:
                aria2_total = int(aria2_total)
            except (ValueError, TypeError):
                aria2_total = 0

            if aria2_total > 0:
                total_length = aria2_total

            aria2_completed = dl.get("completedLength", 0)
            try:
                aria2_completed = int(aria2_completed)
            except (ValueError, TypeError):
                aria2_completed = 0

            if aria2_completed > 0:
                completed_length = aria2_completed

            status = default_status
            if old_status == "paused" or saved_status == "paused":
                status = "paused"
                speed = 0
            elif default_status == "paused":
                status = "paused"
                speed = 0
            elif default_status == "complete":
                status = "complete"
                speed = 0

            return {
                "gid": gid,
                "name": name,
                "category": saved_category,
                "status": status,
                "totalLength": total_length,
                "completedLength": completed_length,
                "downloadSpeed": speed,
                "files": dl.get("files", []),
                "connections": dl.get("connections", 0),
                "error_count": error_count,
                "errorMessage": dl.get("errorMessage", ""),
            }

        active_list = result.get("active", [])
        if not isinstance(active_list, list):
            active_list = []

        waiting_list = result.get("waiting", [])
        if not isinstance(waiting_list, list):
            waiting_list = []

        stopped_list = result.get("stopped", [])
        if not isinstance(stopped_list, list):
            stopped_list = []

        # Active downloads
        for dl in active_list:
            data = process_dl(dl, "active")
            if data:
                all_downloads_dict[data["gid"]] = data

        # Waiting downloads
        for dl in waiting_list:
            data = process_dl(dl, "waiting")
            if data and data["gid"] not in all_downloads_dict:
                all_downloads_dict[data["gid"]] = data

        # Stopped downloads
        for dl in stopped_list:
            gid = dl.get("gid")
            if gid and gid not in all_downloads_dict:
                data = process_dl(dl, dl.get("status", "stopped"))
                if data:
                    all_downloads_dict[gid] = data

        # Handle pending pause
        for gid, data in all_downloads_dict.items():
            if gid in self._pending_pause and int(data.get("totalLength", 0)) > 0:
                if data.get("status") != "paused":
                    self.aria2.pause(gid)
                    data["status"] = "paused"
                    data["downloadSpeed"] = 0
                self._pending_pause.remove(gid)

        for gid, data in all_downloads_dict.items():
            if gid in self._all_downloads:
                old_size = self._all_downloads[gid].get("totalLength", 0)
                if old_size > 0:
                    data["totalLength"] = old_size
            self._all_downloads[gid] = data

        all_queue_gids = set()
        for q in self.store.queues:
            for gid in q.downloads:
                all_queue_gids.add(gid)

        for gid in list(self._all_downloads.keys()):
            if gid not in all_queue_gids and gid not in self._pending_size_fetch:
                del self._all_downloads[gid]

        # ===== Save complete download info to data_store =====
        for q in self.store.queues:
            for gid in q.downloads:
                if gid in self._all_downloads:
                    dl = self._all_downloads[gid]
                    if gid not in q.downloads_info:
                        q.downloads_info[gid] = {}

                    q.downloads_info[gid].update(
                        {
                            "totalLength": dl.get("totalLength", 0),
                            "completedLength": dl.get("completedLength", 0),
                            "status": dl.get("status", "unknown"),
                            "name": dl.get("name", "Unknown"),
                            "files": dl.get("files", []),
                            "category": dl.get("category", "📁 Other"),
                            "error_count": dl.get("error_count", 0),
                            "errorMessage": dl.get("errorMessage", ""),
                        }
                    )

        self.store.save()

        # ===== Retry downloads with errors =====
        max_retries = self.store.settings.get("max_retries", 3)

        for gid, data in all_downloads_dict.items():
            # ===== فقط برای aria2 (نه یوتیوب) =====
            if data.get("download_type") == "youtube":
                continue

            status = data.get("status", "")
            error_msg = data.get("errorMessage", "")

            # ===== اگه error یا stopped با پیام خطا =====
            if status in ["error", "stopped"] and error_msg:
                error_count = data.get("error_count", 0)

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

        # ===== Check queue completion =====
        for q in self.store.queues:
            if not q.paused and q.downloads:
                has_any_download = any(
                    gid in self._all_downloads for gid in q.downloads
                )
                if has_any_download:
                    all_done = all(
                        self._all_downloads.get(gid, {}).get("status")
                        in ["complete", "error", "removed"]
                        for gid in q.downloads
                        if gid in self._all_downloads
                    )
                    if all_done:
                        q.paused = True
                        self.tray.showMessage(
                            "FelfelDM",
                            f"✅ Queue '{q.name}' finished!",
                            QSystemTrayIcon.MessageIcon.Information,
                            4000,
                        )
                        self.store.save()

        # ===== Schedule management =====
        for q in self.store.queues:
            if not q.schedule_enabled:
                continue

            is_scheduled_time = q.is_scheduled_now()
            now = datetime.now().strftime("%H:%M")

            manually_paused = getattr(q, "manually_paused", False)

            print(
                f"🕐 [Schedule] Queue: {q.name}, Now: {now}, "
                f"Scheduled: {q.schedule_start.strftime('%H:%M')}-{q.schedule_end.strftime('%H:%M')}, "
                f"Is scheduled: {is_scheduled_time}, Paused: {q.paused}, ManuallyPaused: {manually_paused}"
            )

            if is_scheduled_time:
                if q.paused:
                    if not manually_paused:
                        print(
                            f"🕐 [Schedule] {q.name} is in schedule window and paused (auto), auto-resuming..."
                        )
                        q.paused = False
                        q.manually_paused = False  # reset
                        self.store.save()
                        self._refresh_queue_list()

                        resumed_count = 0
                        for gid in q.downloads:
                            download_type = "normal"
                            if gid in self._all_downloads:
                                download_type = self._all_downloads[gid].get(
                                    "download_type", "normal"
                                )

                            if download_type == "youtube":
                                if gid in self._all_downloads:
                                    current_status = self._all_downloads[gid].get(
                                        "status", ""
                                    )
                                    if current_status == "paused":
                                        self._start_youtube_download(gid)
                                        self._all_downloads[gid][
                                            "status"
                                        ] = "downloading"
                                        if gid in q.downloads_info:
                                            q.downloads_info[gid][
                                                "status"
                                            ] = "downloading"
                                        resumed_count += 1
                            else:
                                status_data = self.aria2.get_status(gid)
                                if status_data and isinstance(status_data, dict):
                                    real_status = status_data.get("status", "")
                                else:
                                    real_status = self._all_downloads.get(gid, {}).get(
                                        "status", ""
                                    )

                                if real_status == "paused":
                                    result_resume = self.aria2.resume(gid)
                                    if result_resume is not None:
                                        resumed_count += 1
                                        if gid in self._all_downloads:
                                            self._all_downloads[gid][
                                                "status"
                                            ] = "active"
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
                        print(
                            f"🕐 [Schedule] {q.name} is paused by user, NOT auto-resuming..."
                        )

                else:
                    for gid in q.downloads:
                        download_type = "normal"
                        if gid in self._all_downloads:
                            download_type = self._all_downloads[gid].get(
                                "download_type", "normal"
                            )

                        if download_type != "youtube":
                            status_data = self.aria2.get_status(gid)
                            if status_data and isinstance(status_data, dict):
                                real_status = status_data.get("status", "")
                                if real_status == "paused":
                                    self.aria2.resume(gid)
                                    if gid in self._all_downloads:
                                        self._all_downloads[gid]["status"] = "active"
                                    print(
                                        f"🕐 [Schedule] Resumed paused download: {gid}"
                                    )

            else:
                if not q.paused:
                    print(
                        f"🕐 [Schedule] {q.name} is outside schedule window, auto-pausing..."
                    )
                    q.paused = True
                    q.manually_paused = False
                    self.store.save()
                    self._refresh_queue_list()

                    paused_count = 0
                    for gid in q.downloads:
                        download_type = "normal"
                        if gid in self._all_downloads:
                            download_type = self._all_downloads[gid].get(
                                "download_type", "normal"
                            )

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
                        else:
                            status_data = self.aria2.get_status(gid)
                            if status_data and isinstance(status_data, dict):
                                real_status = status_data.get("status", "")
                            else:
                                real_status = self._all_downloads.get(gid, {}).get(
                                    "status", ""
                                )

                            if real_status in ["active", "waiting"]:
                                self.aria2.pause(gid)
                                paused_count += 1
                                if gid in self._all_downloads:
                                    self._all_downloads[gid]["status"] = "paused"
                                    self._all_downloads[gid]["downloadSpeed"] = 0
                                if gid in q.downloads_info:
                                    q.downloads_info[gid]["status"] = "paused"
                                print(f"🕐 [Schedule] Paused: {gid}")

                    if paused_count > 0:
                        next_time = q.get_next_schedule_time()
                        if next_time:
                            time_str = next_time.strftime("%H:%M")
                            self.tray.showMessage(
                                "FelfelDM",
                                f"⏰ Schedule ended for '{q.name}'. Next schedule at {time_str}.",
                                QSystemTrayIcon.MessageIcon.Information,
                                3000,
                            )

                    self._refresh_table()
                    self._update_queue_status()
                    self._update_queue_buttons()

        # ===== Update progress dialog =====
        try:
            if hasattr(self, "_progress_dialog"):
                dialog = self._progress_dialog
                if dialog is not None:
                    try:
                        if dialog.isVisible():
                            gid = dialog.gid
                            if gid in self._all_downloads:
                                dialog.update_data(self._all_downloads[gid])
                    except (RuntimeError, AttributeError):
                        self._progress_dialog = None
        except Exception as e:
            print(f"Progress dialog update error: {e}")
            self._progress_dialog = None

        # ===== Update YouTube dialog =====
        try:
            if hasattr(self, "_youtube_dialog"):
                dialog = self._youtube_dialog
                if dialog is not None:
                    try:
                        if dialog.isVisible() and hasattr(dialog, "worker"):
                            pass
                    except (RuntimeError, AttributeError):
                        self._youtube_dialog = None
        except Exception:
            self._youtube_dialog = None

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

        # ===== Refresh UI =====
        self._refresh_table()
        self._update_queue_status()
        self._refresh_queue_list()
        self._update_queue_buttons()
        self._update_shutdown_button_state()
        self._update_toggle_button()

    def _start_aria2_if_needed(self):
        if self.aria2.is_connected():
            return
        try:
            port = self.store.settings["aria2_port"]
            max_tries = self.store.settings.get("max_tries", 0)
            max_concurrent = self.store.settings.get("max_concurrent", 5)

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
            ]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1.0)
        except FileNotFoundError:
            QMessageBox.critical(
                self,
                "aria2 Not Found",
                "aria2 is not installed.\nRun: sudo pacman -S aria2",
            )

    def _on_aria2_error(self, message):
        if "disconnected" in message:
            return
        if "cannot be paused now" in message:
            return
        if "cannot be unpaused now" in message:
            return
        if "is not found" in message:
            return
        self.tray.showMessage(
            "FelfelDM", message, QSystemTrayIcon.MessageIcon.Warning, 3000
        )
        self.status_label.setText(f"⚠ {message}")

    def _open_progress_dialog(self, gid):
        """Open progress dialog for a download in a separate window"""
        dl_data = self._all_downloads.get(gid, {})

        if hasattr(self, "_progress_dialog") and self._progress_dialog is not None:
            try:
                self._progress_dialog.close()
            except:
                pass
            self._progress_dialog = None

        self._progress_dialog = DownloadProgressDialog(gid, dl_data, None)

        if self._progress_dialog:
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

    def _center_dialog_on_screen(self, dialog):
        """Center dialog on screen"""
        screen = QApplication.primaryScreen().geometry()
        dialog.move(
            screen.center().x() - dialog.width() // 2,
            screen.center().y() - dialog.height() // 2,
        )

    def _on_progress_dialog_closed(self):
        """Clean up progress dialog reference"""
        if hasattr(self, "_progress_dialog"):
            self._progress_dialog = None

    def _pause_from_dialog(self, gid):
        """Pause download from progress dialog"""
        print(f"⏸️ Pause requested for: {gid}")

        if not gid:
            return

        # ===== دریافت وضعیت از aria2 =====
        status_data = self.aria2.get_status(gid)

        # ===== استخراج status از دیکشنری =====
        if status_data and isinstance(status_data, dict):
            real_status = status_data.get("status", "")
        else:
            real_status = self._all_downloads.get(gid, {}).get("status", "")

        print(f"📊 Current status: {real_status}")

        if real_status in ["active", "waiting"]:
            try:
                result = self.aria2.force_pause(gid)
                print(f"🔧 force_pause result: {result}")

                if result is not None:
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
                            if other_gid in self._all_downloads:
                                status = self._all_downloads[other_gid].get(
                                    "status", ""
                                )
                                if status in ["active", "waiting"]:
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
                        hasattr(self, "_progress_dialog")
                        and self._progress_dialog is not None
                    ):
                        if (
                            self._progress_dialog.isVisible()
                            and gid in self._all_downloads
                        ):
                            self._progress_dialog.update_data(self._all_downloads[gid])

                    if not has_active and q and q.name != "__direct__":
                        self.tray.showMessage(
                            "FelfelDM",
                            f"⏸️ Queue '{q.name}' paused (no active downloads)",
                            QSystemTrayIcon.MessageIcon.Information,
                            2000,
                        )
                    else:
                        self.tray.showMessage(
                            "FelfelDM",
                            "⏸️ Download paused",
                            QSystemTrayIcon.MessageIcon.Information,
                            2000,
                        )
                else:
                    print("❌ force_pause returned None")

            except Exception as e:
                print(f"❌ Pause error: {e}")
                import traceback

                traceback.print_exc()
        else:
            print(f"⚠️ Cannot pause: status is {real_status}")

    def _resume_from_dialog(self, gid):
        """Resume download from progress dialog"""
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

        # ===== دریافت وضعیت از aria2 =====
        status_data = self.aria2.get_status(gid)

        # ===== استخراج status از دیکشنری =====
        if status_data and isinstance(status_data, dict):
            real_status = status_data.get("status", "")
        else:
            real_status = self._all_downloads.get(gid, {}).get("status", "")

        print(f"📊 Current status: {real_status}")

        if real_status == "paused":
            try:
                result = self.aria2.resume(gid)
                if result is not None:
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "active"

                    for q in self.store.queues:
                        if gid in q.downloads_info:
                            q.downloads_info[gid]["status"] = "active"
                            break

                    self.store.save()

                    if q and q.speed_limit > 0:
                        self.aria2.set_download_speed_limit(gid, q.speed_limit)
                        print(
                            f"⚡ Queue speed limit {q.speed_limit}KB/s applied to {gid}"
                        )

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
                        hasattr(self, "_progress_dialog")
                        and self._progress_dialog is not None
                    ):
                        if (
                            self._progress_dialog.isVisible()
                            and gid in self._all_downloads
                        ):
                            self._progress_dialog.update_data(self._all_downloads[gid])
            except Exception as e:
                print(f"❌ Resume error: {e}")

    def _cancel_from_dialog(self, gid):
        """Cancel download from progress dialog (without deleting files)"""
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

    def _cancel_with_delete_from_dialog(self, gid):
        """Cancel download and delete files from progress dialog"""
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

        try:
            self.aria2.remove(gid)
        except Exception as e:
            print(f"⚠ Could not remove GID {gid} from aria2: {e}")

        for q in self.store.queues:
            if gid in q.downloads:
                q.downloads.remove(gid)

        if gid in self._all_downloads:
            del self._all_downloads[gid]

        for path in file_paths:
            try:
                if os.path.isfile(path):
                    os.remove(path)
                    print(f"🗑 Deleted file: {path}")
                elif os.path.isdir(path):
                    import shutil

                    shutil.rmtree(path)
                    print(f"🗑 Deleted folder: {path}")
            except Exception as e:
                print(f"⚠ Could not delete {path}: {e}")

        for aria2_path in aria2_files:
            try:
                if os.path.exists(aria2_path):
                    os.remove(aria2_path)
                    print(f"🗑 Deleted aria2 file: {aria2_path}")
            except Exception as e:
                print(f"⚠ Could not delete {aria2_path}: {e}")

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

    def _quick_download(self):
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
            target_queue = None

            # ===== پیدا کردن صف =====
            for q in self.store.queues:
                if q.name == queue_name:
                    target_queue = q
                    break

            # ===== اگه صف وجود نداشت، بساز =====
            if target_queue is None:
                target_queue = Queue(queue_name, paused=False)
                if queue_name == "__direct__":
                    target_queue.max_concurrent = 99
                self.store.queues.append(target_queue)
                self.store.save()
            elif queue_name == "__direct__":
                target_queue.paused = False

            if not hasattr(target_queue, "downloads_info"):
                target_queue.downloads_info = {}

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
                gid = self.aria2.add_url(url, options)
                if gid:
                    target_queue.downloads.append(gid)

                    raw_name = url.split("/")[-1]
                    clean_name = raw_name.split("?")[0] if "?" in raw_name else raw_name
                    if not clean_name:
                        clean_name = "Unknown"
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
                    }

                    try:
                        time.sleep(0.15)
                        status_data = self.aria2.get_status(gid)
                        if status_data is not None and isinstance(status_data, dict):
                            real_status = status_data.get("status", "")
                            if real_status != "paused":
                                self.aria2.pause(gid)
                                print(f"⏸️ Paused after quick add: {gid}")
                            else:
                                print(f"⏸️ Already paused: {gid}")
                        else:
                            print(f"⚠️ GID {gid} not ready, skipping pause")
                    except Exception as e:
                        print(f"⚠️ Could not pause {gid}: {e}")

                    if gid in self._pending_pause:
                        self._pending_pause.remove(gid)

                    start_now = (
                        d.get("start_immediately", True) and not target_queue.paused
                    )

                    if target_queue and getattr(target_queue, "speed_limit", 0) > 0:
                        time.sleep(0.3)
                        self.aria2.set_download_speed_limit(
                            gid, target_queue.speed_limit
                        )
                        print(
                            f"⚡ Queue speed limit {target_queue.speed_limit}KB/s applied to {gid} (before start)"
                        )

                    if start_now:
                        self._all_downloads[gid]["status"] = "paused"
                        if gid in target_queue.downloads_info:
                            target_queue.downloads_info[gid]["status"] = "paused"
                        self._pending_pause.add(gid)
                    else:
                        self._all_downloads[gid]["status"] = "paused"
                        if gid in target_queue.downloads_info:
                            target_queue.downloads_info[gid]["status"] = "paused"
                        self._pending_pause.add(gid)

                    added_gids.append(gid)

            self.store.save()
            self._refresh_queue_list()
            self._refresh_table()
            self._update_shutdown_button_state()

            if (
                len(added_gids) == 1
                and d.get("start_immediately", True)
                and not target_queue.paused
            ):

                def open_dialog_when_ready():
                    gid = added_gids[0]
                    if gid in self._all_downloads:
                        total = self._all_downloads[gid].get("totalLength", 0)
                        if total > 0:
                            self._open_progress_dialog(gid)
                        else:
                            QTimer.singleShot(1000, open_dialog_when_ready)

                QTimer.singleShot(500, open_dialog_when_ready)

    def _on_table_double_click(self, index):
        """دابل کلیک روی جدول"""
        gid = self.model.get_gid(index.row())
        if not gid:
            return

        download_type = "normal"
        if gid in self._all_downloads:
            download_type = self._all_downloads[gid].get("download_type", "normal")

        if download_type == "youtube":
            self._open_youtube_progress_dialog(gid)
        else:
            self._open_progress_dialog(gid)

    def _close_splash(self):
        if hasattr(self, "splash") and self.splash:
            self.splash.close()
            self.splash = None

    def _youtube_download(self):
        queues = [q for q in self.store.queues if q.name != "__direct__"]

        current_q = self._current_queue()
        default_idx = 0
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

    def _add_youtube_to_queue(self, download_data: dict):
        print("🎯🎯🎯 _add_youtube_to_queue CALLED")
        print(f"🎯🎯🎯 download_data: {download_data}")

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
        filename = f"{title}.{ext}"

        import re

        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
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

        print(f"🎯🎯🎯 Calling worker.add_youtube_download for {download_id}")
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
        else:
            print("❌❌❌ worker is None!")

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

    def _start_youtube_download(self, download_id: str):
        """شروع دانلود یوتیوب (دستی توسط کاربر)"""
        if not hasattr(self, "worker") or not self.worker:
            print("❌ Worker not available")
            return

        data = self.store.get_youtube_download(download_id)
        if not data:
            print(f"❌ Download {download_id} not found")
            return

        total_size = data.get("total_size", 0)
        print(f"📏 [START] total_size for {download_id}: {total_size}")

        print(f"▶️ Starting YouTube download: {download_id}")

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

    def _pause_youtube_download(self, download_id: str):
        """توقف موقت دانلود یوتیوب (از دیالوگ یا منو)"""
        if not hasattr(self, "worker"):
            return

        print(f"⏸️ [UI] Pausing YouTube: {download_id}")
        self.worker.pause_youtube_download(download_id)

        if download_id in self._all_downloads:
            self._all_downloads[download_id]["status"] = "paused"

        q = self._current_queue()
        if q and q.name != "__direct__":
            has_active = False
            for gid in q.downloads:
                if gid in self._all_downloads:
                    status = self._all_downloads[gid].get("status", "")
                    if status in ["active", "waiting", "downloading"]:
                        has_active = True
                        break

            if not has_active:
                q.paused = True
                self.store.save()
                print(f"⏸️ [UI] Queue '{q.name}' auto-paused (no active downloads)")

        self._update_queue_buttons()
        self._refresh_table()

    def _resume_youtube_download(self, download_id: str):
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

    def _do_resume_youtube_download(self, download_id: str):
        """اجرای واقعی Resume دانلود یوتیوب"""
        if not hasattr(self, "worker"):
            return

        print(f"▶️ [UI] Resuming YouTube: {download_id}")
        self.worker.resume_youtube_download(download_id)

        if download_id in self._all_downloads:
            self._all_downloads[download_id]["status"] = "downloading"

        self._update_queue_buttons()
        self._refresh_table()

        print(f"▶️ [UI] Resuming YouTube: {download_id}")
        self.worker.resume_youtube_download(download_id)

        if download_id in self._all_downloads:
            self._all_downloads[download_id]["status"] = "downloading"

        self._update_queue_buttons()
        self._refresh_table()

    def _resume_youtube_download_after_queue_start(self, download_id: str):
        """بعد از Start شدن صف، دانلود رو Resume کن"""
        if not hasattr(self, "worker"):
            return

        q = self._current_queue()
        if q and q.paused:
            QMessageBox.warning(
                self,
                "صف متوقف شده",
                f"صف '{q.name}' هنوز در حالت توقف است.\n\n"
                "لطفاً ابتدا دکمه 'Start' را برای این صف در نوار کناری بزنید.",
                QMessageBox.StandardButton.Ok,
            )
            return

        print(f"▶️ [UI] Resuming YouTube after queue start: {download_id}")
        self.worker.resume_youtube_download(download_id)

        if download_id in self._all_downloads:
            self._all_downloads[download_id]["status"] = "downloading"

        self._update_queue_buttons()
        self._refresh_table()

    def _cancel_youtube_download(self, download_id: str):
        """لغو دانلود یوتیوب (از مودال) - همیشه فایل‌ها رو پاک کن"""
        if not hasattr(self, "worker"):
            print("❌ Worker not available")
            return

        print(f"🗑️ Cancelling YouTube download from UI: {download_id}")

        if hasattr(self, "_youtube_dialog") and self._youtube_dialog is not None:
            try:
                self._youtube_dialog.close()
            except:
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

    def _on_youtube_finished(self, success: bool, message: str):
        """Handle YouTube download finished از BackendWorker"""
        if success:
            self.tray.showMessage(
                "FelfelDM",
                "✅ YouTube download completed!",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        else:
            if "cancelled" not in message.lower():
                self.tray.showMessage(
                    "FelfelDM",
                    f"❌ YouTube download failed: {message}",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000,
                )

    def _apply_proxy_to_aria2(self):
        proxy = self.proxy_manager.get_proxy_for_queue(None)

        if proxy and proxy.enabled and proxy.is_valid():
            result = self.aria2.set_global_proxy(proxy)
            if result is not None:
                print(f"✅ Global proxy applied: {proxy.get_display_string()}")
            else:
                print("⚠️ Failed to apply proxy")
        else:
            self.aria2.change_global_option({"all-proxy": ""})
            print("✅ Proxy disabled")

    def _toggle_pause_resume(self):
        """Toggle pause/resume for selected download"""
        gid = self._selected_gid()
        if not gid:
            return

        download_type = "normal"
        if gid in self._all_downloads:
            download_type = self._all_downloads[gid].get("download_type", "normal")

        if download_type == "youtube":
            if gid in self._all_downloads:
                real_status = self._all_downloads[gid].get("status", "")
            else:
                return
        else:
            real_status = self.aria2.get_status(gid)
            if not real_status and gid in self._all_downloads:
                real_status = self._all_downloads[gid].get("status", "")

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

    def _set_download_proxy(self, gid, download_name):
        """Set custom proxy for a specific download"""
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

            # Refresh table
            self._refresh_table()

    def _clear_download_proxy(self, gid):
        """Clear custom proxy for a download"""
        self.proxy_manager.set_download_proxy(gid, None)
        dl_data = self._all_downloads.get(gid, {})
        name = dl_data.get("name", "Unknown")

        self.tray.showMessage(
            "FelfelDM",
            f"🗑 Proxy cleared for: {name}",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )
        self._refresh_table()

    def _move_selected_to_queue(self):
        """Move selected downloads to another queue"""
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "Info", "No downloads selected.")
            return

        gids_to_move = []
        for idx in selected:
            gid = self.model.get_gid(idx.row())
            if gid:
                gids_to_move.append(gid)

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
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        info_label = QLabel(
            f"Move {len(gids_to_move)} download(s) from '{source_queue.name}' to:"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        queue_combo = QComboBox()
        for q in target_queues:
            queue_combo.addItem(q.name, q)
        layout.addWidget(queue_combo)

        layout.addSpacing(10)

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
        moved_count = 0

        for gid in gids_to_move:
            real_status = self.aria2.get_status(gid)
            if not real_status and gid in self._all_downloads:
                real_status = self._all_downloads[gid].get("status")

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
                        try:
                            self.aria2.pause(gid)
                        except:
                            pass

                moved_count += 1

        if len(source_queue.downloads) == 0:
            source_queue.paused = True

        self.store.save()

        self._refresh_queue_list()
        self._refresh_table()
        self._update_queue_buttons()
        self._update_toggle_button()

        self.tray.showMessage(
            "FelfelDM",
            f"✅ Moved {moved_count} download(s) to '{target_queue.name}'",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _on_size_fetched(self, gid: str, size: int, category: str = "📁 Other"):
        if gid in self._all_downloads:
            self._all_downloads[gid]["totalLength"] = size
            self._all_downloads[gid]["category"] = category

            q = self._current_queue()
            if q and gid in q.downloads:
                row_index = q.downloads.index(gid)
                if row_index >= 0:
                    index = self.model.index(row_index, 1)
                    self.model.dataChanged.emit(index, index)
                    index2 = self.model.index(row_index, 2)
                    self.model.dataChanged.emit(index2, index2)
                    index3 = self.model.index(row_index, 4)
                    self.model.dataChanged.emit(index3, index3)

            print(f"✅ [MainWindow] Size updated for {gid}")
        else:
            print(f"⚠️ [MainWindow] GID {gid} not found")

    def _show_shutdown_countdown(self):
        """نمایش دیالوگ شمارش معکوس برای خاموشی"""
        if self._shutdown_dialog:
            self._shutdown_dialog.close()
            self._shutdown_dialog = None

        dialog = ShutdownCountdownDialog(self)
        dialog.accepted.connect(self._shutdown_system)
        dialog.rejected.connect(self._cancel_shutdown)

        dialog.show()
        dialog.start_countdown()

        self._shutdown_dialog = dialog
        self._center_dialog_on_screen(dialog)

    def _shutdown_system(self):
        """خاموش کردن سیستم"""
        self._shutdown_dialog = None
        self._shutdown_dialog_shown = False

        self.tray.showMessage(
            "FelfelDM",
            "🛑 Shutting down system...",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )
        os.system("systemctl poweroff")

    def _cancel_shutdown(self):
        """کنسل کردن خاموشی"""
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

    def _update_shutdown_button_state(self):
        """به‌روزرسانی وضعیت دکمه Shutdown on Finish"""
        q = self._current_queue()

        if not q or q.name == "__direct__":
            self.shutdown_cb.setEnabled(False)
            return

        if len(q.downloads) == 0:
            self.shutdown_cb.setEnabled(False)
            return

        all_complete = True
        for gid in q.downloads:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                if status not in ["complete", "error", "removed"]:
                    all_complete = False
                    break
            else:
                all_complete = False
                break

        if all_complete:
            self.shutdown_cb.setEnabled(False)
            if self.shutdown_cb.isChecked():
                self.shutdown_cb.setChecked(False)
                self.store.settings["shutdown_after_finish"] = False
                self.store.save()
            return

        self.shutdown_cb.setEnabled(True)

    def _has_active_downloads(self, q):
        """Check if queue has any active or waiting downloads"""
        if not q:
            return False

        for gid in q.downloads:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                if status in ["active", "waiting"]:
                    return True
        return False

    def _has_resumable_downloads(self, q):
        """Check if queue has any paused or waiting downloads"""
        if not q:
            return False

        for gid in q.downloads:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                if status in ["paused", "waiting"]:
                    return True
        return False

    def _apply_queue_speed_limit(self, q):
        """Apply speed limit for a specific queue to all its downloads"""
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
                        if global_limit > 0:
                            self.aria2.set_download_speed_limit(gid, global_limit)
                        else:
                            self.aria2.set_download_speed_limit(gid, 0)

    def _parse_speed(self, speed_str: str) -> int:
        """تبدیل سرعت به عدد (bytes/sec)"""
        if not speed_str:
            return 0
        try:
            speed_str = speed_str.strip()
            if "KiB/s" in speed_str:
                return int(float(speed_str.replace("KiB/s", "").strip()) * 1024)
            elif "MiB/s" in speed_str:
                return int(float(speed_str.replace("MiB/s", "").strip()) * 1024 * 1024)
            elif "KB/s" in speed_str:
                return int(float(speed_str.replace("KB/s", "").strip()) * 1000)
            elif "MB/s" in speed_str:
                return int(float(speed_str.replace("MB/s", "").strip()) * 1000 * 1000)
            elif speed_str.isdigit():
                return int(speed_str)
            return 0
        except:
            return 0

    def _on_youtube_progress(self, download_id: str, progress: int):
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

    def _on_youtube_status(self, download_id: str, status: str):
        """به‌روزرسانی وضعیت دانلود یوتیوب از BackendWorker"""
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

    def _on_youtube_speed(self, download_id: str, speed: str, eta: str):
        """به‌روزرسانی سرعت و زمان باقیمانده یوتیوب"""
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["speed"] = speed
            self._all_downloads[download_id]["eta"] = eta
            self._all_downloads[download_id]["downloadSpeed"] = self._parse_speed(speed)

            self._refresh_table()

    def _on_youtube_size_fetched(self, download_id: str, size: int):
        """دریافت حجم دانلود یوتیوب"""
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["totalLength"] = size
            self._all_downloads[download_id]["total_size"] = size
            print(f"📏 YouTube size updated for {download_id}: {size} bytes")
            self._refresh_table()

    def _on_youtube_progress(self, download_id: str, progress: int):
        """به‌روزرسانی پیشرفت دانلود یوتیوب"""
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["progress"] = progress
            self._all_downloads[download_id]["status"] = "downloading"

            self._update_youtube_dialog(download_id, progress=progress)

            self._refresh_table()

    def _on_youtube_status(self, download_id: str, status: str):
        """به‌روزرسانی وضعیت دانلود یوتیوب از BackendWorker"""
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
            elif status in [
                "completed",
                "✅ Download completed!",
            ]:
                print(f"🔴🔴🔴 [UI] COMPLETED BRANCH REACHED for {download_id}")
                self._update_youtube_dialog(download_id, status="✅ Complete")
                self._update_youtube_dialog_finished(
                    download_id, True, "Download completed successfully!"
                )
            elif status == "error":
                self._update_youtube_dialog(download_id, status="❌ Error")
                self._update_youtube_dialog_finished(
                    download_id, False, "Download failed"
                )

            self._update_queue_buttons()
            self._refresh_table()

    def _on_youtube_speed(self, download_id: str, speed: str, eta: str):
        """به‌روزرسانی سرعت و زمان باقیمانده یوتیوب"""
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["speed"] = speed
            self._all_downloads[download_id]["eta"] = eta
            self._all_downloads[download_id]["downloadSpeed"] = self._parse_speed(speed)

            progress = self._all_downloads[download_id].get("progress", 0)
            self._update_youtube_dialog(
                download_id, progress=progress, speed=speed, eta=eta
            )

            self._refresh_table()

    def _on_youtube_size_fetched(self, download_id: str, size: int):
        """دریافت حجم دانلود یوتیوب"""
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["totalLength"] = size
            self._all_downloads[download_id]["total_size"] = size
            print(f"📏 YouTube size updated for {download_id}: {size} bytes")
            self._refresh_table()

    def _open_youtube_progress_dialog(self, download_id: str):
        """باز کردن دیالوگ پیشرفت برای دانلود یوتیوب"""
        try:
            from ui.youtube_progress import YouTubeProgressDialog

            if not download_id:
                return

            if hasattr(self, "_youtube_dialog") and self._youtube_dialog is not None:
                try:
                    self._youtube_dialog.close()
                    self._youtube_dialog.deleteLater()
                except:
                    pass
                self._youtube_dialog = None

            data = self.store.get_youtube_download(download_id)
            if not data:
                QMessageBox.warning(self, "Error", "Download not found")
                return

            # ===== parent رو None بذار =====
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

            # ===== تنظیمات پنجره =====
            self._youtube_dialog.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.WindowCloseButtonHint
                | Qt.WindowType.WindowMinimizeButtonHint
            )
            self._youtube_dialog.setWindowModality(Qt.WindowModality.NonModal)

            # ===== اتصال سیگنال‌ها =====
            self._youtube_dialog.pause_requested.connect(self._pause_youtube_download)
            self._youtube_dialog.resume_requested.connect(self._resume_youtube_download)
            self._youtube_dialog.cancel_requested.connect(self._cancel_youtube_download)

            # ===== نمایش =====
            self._youtube_dialog.show()
            self._center_dialog_on_screen(self._youtube_dialog)
            self._youtube_dialog.raise_()
            self._youtube_dialog.activateWindow()

            # ===== بعد از باز شدن، وضعیت رو از _all_downloads بگیر و به‌روز کن =====
            if download_id in self._all_downloads:
                dl_data = self._all_downloads[download_id]
                status = dl_data.get("status", "pending")
                progress = dl_data.get("progress", 0)
                speed = dl_data.get("speed", "")
                eta = dl_data.get("eta", "")

                # ===== به‌روزرسانی دیالوگ =====
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

                # ===== فعال کردن دکمه‌ها =====
                if status in ["paused", "downloading"]:
                    self._youtube_dialog.set_action_button_enabled(True)
                elif status == "completed":
                    self._youtube_dialog.set_action_button_enabled(True)
                else:
                    self._youtube_dialog.set_action_button_enabled(False)

        except Exception as e:
            print(f"❌ Error opening YouTube dialog: {e}")
            import traceback

            traceback.print_exc()
            QMessageBox.warning(self, "Error", f"Failed to open dialog: {e}")

    def _update_youtube_dialog(
        self, download_id: str, progress=None, speed=None, eta=None, status=None
    ):
        """به‌روزرسانی دیالوگ یوتیوب اگر باز باشه"""
        if not hasattr(self, "_youtube_dialog") or self._youtube_dialog is None:
            return

        try:
            if not self._youtube_dialog.isVisible():
                return

            if (
                hasattr(self._youtube_dialog, "download_id")
                and self._youtube_dialog.download_id != download_id
            ):
                return

            if progress is not None:
                current_speed = speed or getattr(
                    self._youtube_dialog, "_speed_text", ""
                )
                current_eta = eta or getattr(self._youtube_dialog, "_eta_text", "")
                if hasattr(self._youtube_dialog, "update_progress"):
                    self._youtube_dialog.update_progress(
                        progress, current_speed, current_eta
                    )

            if status is not None:
                if hasattr(self._youtube_dialog, "update_status"):
                    self._youtube_dialog.update_status(status)

        except Exception as e:
            print(f"⚠️ Error updating YouTube dialog: {e}")

    def _update_youtube_dialog_pause_state(self, download_id: str, is_paused: bool):
        """به‌روزرسانی وضعیت Pause/Resume در دیالوگ"""
        if not hasattr(self, "_youtube_dialog") or self._youtube_dialog is None:
            return

        try:
            if not self._youtube_dialog.isVisible():
                return

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
    ):
        """به‌روزرسانی پایان دانلود در دیالوگ"""
        if not hasattr(self, "_youtube_dialog") or self._youtube_dialog is None:
            return

        try:
            if not self._youtube_dialog.isVisible():
                return

            if (
                hasattr(self._youtube_dialog, "download_id")
                and self._youtube_dialog.download_id != download_id
            ):
                return

            if hasattr(self._youtube_dialog, "update_finished"):
                self._youtube_dialog.update_finished(success, message)

        except Exception as e:
            print(f"⚠️ Error updating YouTube dialog finished: {e}")

    def _update_youtube_dialog_to_completed(self, download_id: str):
        """تغییر دکمه دیالوگ به Open Folder بعد از اتمام دانلود"""
        if not hasattr(self, "_youtube_dialog") or self._youtube_dialog is None:
            print(f"⚠️ [UI] No dialog found for {download_id}")
            return

        try:
            dialog = self._youtube_dialog
            if not dialog.isVisible():
                print(f"⚠️ [UI] Dialog not visible for {download_id}")
                return

            if hasattr(dialog, "download_id") and dialog.download_id != download_id:
                print(
                    f"⚠️ [UI] Dialog download_id mismatch: {dialog.download_id} != {download_id}"
                )
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
            except:
                pass
            dialog.action_btn.clicked.connect(dialog._open_folder)

            dialog.cancel_btn.setText(" Close")
            dialog.cancel_btn.setIcon(get_icon("window-close"))
            try:
                dialog.cancel_btn.clicked.disconnect()
            except:
                pass
            dialog.cancel_btn.clicked.connect(dialog.accept)

            print(f"✅ [UI] YouTube dialog updated to completed: {download_id}")

        except Exception as e:
            print(f"⚠️ Error updating YouTube dialog to completed: {e}")
            import traceback

            traceback.print_exc()

    def _delete_youtube_files(self, file_path: str, save_path: str, title: str):
        """پاک کردن فایل‌های دانلود یوتیوب (کامل و ناقص)"""
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
                    except:
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
                    except:
                        pass

        except Exception as e:
            print(f"⚠️ Error deleting files: {e}")

    def _show_about(self):
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

    def _show_update_dialog(self, parent_dialog=None):
        if parent_dialog:
            parent_dialog.accept()

        update_dialog = UpdateDialog(self)
        update_dialog.exec()
