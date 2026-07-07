# ui/main_window.py

import os
import time
import subprocess
from datetime import datetime
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

from core import Aria2RPC, DataStore, Queue, BackendWorker
from ui.dialogs import *
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
                import subprocess
                result = subprocess.run(
                    ['kreadconfig5', '--group', 'Colors:Window', '--key', 'BackgroundNormal'],
                    capture_output=True, text=True
                )
                if result.stdout:
                    color = result.stdout.strip()
                    if color.startswith('#'):
                        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
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
        self.start_queue_btn = QPushButton(get_icon('media-playback-start'), "Start")
        self.start_queue_btn.setObjectName("start_btn")
        self.start_queue_btn.clicked.connect(self._start_current_queue)
        btn_layout.addWidget(self.start_queue_btn)

        self.pause_queue_btn = QPushButton(get_icon('media-playback-pause'), "Pause")
        self.pause_queue_btn.setObjectName("pause_btn")
        self.pause_queue_btn.clicked.connect(self._pause_current_queue)
        btn_layout.addWidget(self.pause_queue_btn)
        sb_lay.addLayout(btn_layout)

        mgmt_lay = QVBoxLayout()
        mgmt_lay.setSpacing(4)
        mgmt_lay.addWidget(QPushButton(get_icon('list-add'), "New Queue", clicked=self._add_queue))
        mgmt_lay.addWidget(QPushButton(get_icon('configure'), "Settings", clicked=self._edit_queue))
        mgmt_lay.addWidget(QPushButton(get_icon('list-remove'), "Delete", clicked=self._delete_queue))
        sb_lay.addLayout(mgmt_lay)

        sb_lay.addSpacing(12)

        status_group = QGroupBox("Status")
        status_lay = QVBoxLayout(status_group)
        status_lay.setSpacing(4)

        self.queue_status_lbl = QLabel("⏸ Paused")
        self.queue_status_lbl.setStyleSheet("color: #f39c12; font-weight: bold;")
        status_lay.addWidget(self.queue_status_lbl)

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

        self.btn_add = QPushButton(get_icon('download'), "Download")
        self.btn_add.clicked.connect(self._quick_download)

        self.btn_add_queue = QPushButton(get_icon('list-add'), "Add to Queue")
        self.btn_add_queue.clicked.connect(self._add_download)
        tb_lay.addWidget(self.btn_add_queue)
        tb_lay.addWidget(self.btn_add)


        self.btn_toggle = QPushButton(get_icon('media-playback-pause'), "Pause")
        self.btn_toggle.clicked.connect(self._toggle_pause_resume)
        self.btn_toggle.setEnabled(False)  # Disabled initially
        tb_lay.addWidget(self.btn_toggle)
        
        self.btn_move_queue = QPushButton(get_icon('go-next'), "Move to Queue")
        self.btn_move_queue.clicked.connect(self._move_selected_to_queue)
        self.btn_move_queue.setEnabled(False)
        tb_lay.addWidget(self.btn_move_queue)

        self.btn_remove = QPushButton(get_icon('edit-delete'), "Remove")
        self.btn_remove.clicked.connect(self._remove_selected)
        tb_lay.addWidget(self.btn_remove)

        self.btn_clear_completed = QPushButton(get_icon('edit-clear'), "Clear Completed")
        self.btn_clear_completed.clicked.connect(self._clear_completed_downloads)
        tb_lay.addWidget(self.btn_clear_completed)

        self.btn_youtube = QPushButton()
        self.btn_youtube.setIcon(get_icon('video-display'))
        self.btn_youtube.setText(" YouTube")
        self.btn_youtube.clicked.connect(self._youtube_download)
        tb_lay.addWidget(self.btn_youtube)
        
        tb_lay.addStretch()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search...")
        self.search_box.setMaximumWidth(180)
        self.search_box.textChanged.connect(self._filter_downloads)
        tb_lay.addWidget(self.search_box)

        self.btn_settings = QPushButton(get_icon('configure'), "")
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
            self.table.selectionModel().selectionChanged.connect(self._update_toggle_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(200)
        self.progress_bar.setTextVisible(True)
        self.statusBar().addPermanentWidget(self.progress_bar)

        self.status_label = QLabel("Ready")
        self.statusBar().addPermanentWidget(self.status_label)

        self.shutdown_cb = QCheckBox("Shutdown on Finish")
        self.shutdown_cb.setChecked(self.store.settings.get("shutdown_after_finish", False))
        self.shutdown_cb.toggled.connect(self._toggle_shutdown)
        self.statusBar().addPermanentWidget(self.shutdown_cb)

        splitter.addWidget(sidebar)
        splitter.addWidget(main_area)
        splitter.setSizes([210, 840])

        root.addWidget(splitter)

        
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        add_action = QAction(get_icon('list-add'), "Add Downloads", self)
        add_action.triggered.connect(self._add_download)
        add_action.setShortcut("Ctrl+N")
        file_menu.addAction(add_action)


        file_menu.addSeparator()

        settings_action = QAction(get_icon('configure'), "Settings", self)
        settings_action.triggered.connect(self._open_settings)
        settings_action.setShortcut("Ctrl+,")
        file_menu.addAction(settings_action)
        file_menu.addSeparator()

        quit_action = QAction(get_icon('application-exit'), "Quit", self)
        quit_action.triggered.connect(self.quit_app)
        quit_action.setShortcut("Ctrl+Q")
        file_menu.addAction(quit_action)

        queue_menu = mb.addMenu("&Queue")
        queue_menu.addAction(get_icon('list-add'), "New Queue", self._add_queue)
        queue_menu.addAction(get_icon('configure'), "Edit Queue", self._edit_queue)
        queue_menu.addAction(get_icon('list-remove'), "Delete Queue", self._delete_queue)

        view_menu = mb.addMenu("&View")
        refresh_action = QAction(get_icon('view-refresh'), "Refresh", self)
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
            get_resource_path("logo/icon64.png"),
            get_resource_path("logo/icon128.png"), 
            get_resource_path("icons/icon64.png"),
            get_resource_path("icons/icon128.png"),
        ]
        
        icon_set = False
        for path in icon_paths:
            if os.path.exists(path):
                self.tray.setIcon(QIcon(path))
                icon_set = True
                print(f"✅ Tray icon loaded from: {path}")
                break
        
        if not icon_set:
            
            self.tray.setIcon(get_icon('download-manager'))
            print("⚠️ Tray icon: Using Papirus fallback")

        menu = QMenu()
        menu.addAction(get_icon('window'), "Show", self.show)
        menu.addAction(get_icon('application-exit'), "Quit", self.quit_app)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()

    def _show_about(self):
        QMessageBox.about(self, "About FelfelDM",
        "<h2 style='color: #e74c3c;'>🌶️ FelfelDM</h2>"
        "<p>A modern download manager</p>"
        "<p>Built with PyQt6 and aria2</p>")

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
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._pause_all_downloads()
                
                self.hide()
                self.tray.showMessage(
                    "FelfelDM",
                    "Downloads are running in the background.\n"
                    "Double-click the tray icon to show the main window.",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000
                )
                event.ignore()
                return
        
        # If no active downloads or user said close
        if hasattr(self, 'tray') and self.tray.isVisible():
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
        
        if hasattr(self, '_progress_dialog') and self._progress_dialog is not None:
            try:
                self._progress_dialog.close()
            except:
                pass
            self._progress_dialog = None
        
        if hasattr(self, '_youtube_dialog') and self._youtube_dialog is not None:
            try:
                self._youtube_dialog.close()
            except:
                pass
            self._youtube_dialog = None
        
        # Kill all background
        if hasattr(self, 'worker'):
            self.worker.terminate()
        
        try:
            import subprocess
            subprocess.run(["pkill", "-9", "aria2c"], capture_output=True)
        except:
            pass
        
        if hasattr(self, 'tray'):
            self.tray.hide()
        
        import sys
        sys.exit(0)

    def _restore_downloads_with_progress(self):
        """Restore downloads with progress updates"""
        print("🔄 Restoring downloads...")
        restored_count = 0
        total_downloads = sum(len(q.downloads) for q in self.store.queues)
        
        if total_downloads == 0:
            self.splash.update_status("No downloads to restore", 95)
            QApplication.processEvents()
            return
        
        wait_count = 0
        while not self.aria2.is_connected() and wait_count < 25:
            time.sleep(0.2)
            wait_count += 1
        
        if not self.aria2.is_connected():
            print("⚠️ aria2 not ready, skipping restore")
            self.splash.update_status("aria2 not ready, skipping restore", 95)
            QApplication.processEvents()
            return
        
        processed = 0
        for q in self.store.queues:
            for gid in q.downloads[:]:
                processed += 1
                progress = 92 + int((processed / total_downloads) * 8)
                self.splash.update_status(f"Restoring... ({processed}/{total_downloads})", progress)
                QApplication.processEvents()
                
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
                                "name": old_info.get("name", url.split("/")[-1] or "Unknown"),
                                "status": "paused",
                                "totalLength": old_info.get("totalLength", 0),
                                "completedLength": old_info.get("completedLength", 0),
                                "downloadSpeed": 0,
                                "connections": 0,
                                "files": old_info.get("files", []),
                                "errorMessage": "",
                                "category": old_info.get("category", "📁 Other")
                            }
                            
                            try:
                                self.aria2.pause(new_gid)
                                print(f"⏸️ Restored as paused: {old_info.get('name', url)}")
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
        
        self.splash.update_status("Ready!", 100)
        QApplication.processEvents()
        
    def _delayed_restore(self):
        """Delay restore until aria2 is fully ready"""
        if self.aria2.is_connected():
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
        
        if all_complete and len(q.downloads) > 0:
            self.start_queue_btn.setEnabled(False)
            self.pause_queue_btn.setEnabled(False)
            return

        if q.paused:
            self.start_queue_btn.setEnabled(True)
            self.pause_queue_btn.setEnabled(False)
        else:
            self.start_queue_btn.setEnabled(False)
            self.pause_queue_btn.setEnabled(True)
    
    def _refresh_queue_list(self):
        self.queue_list.blockSignals(True)
        self.queue_list.clear()
        for q in self.store.queues:
            if len(q.downloads) == 0:
                q.paused = True
                self._cleared_gids.clear()
                for gid in q.downloads[:]:
                    if gid in self._all_downloads:
                        del self._all_downloads[gid]
                q.downloads.clear()

            if q.name == "__direct__":
                item = QListWidgetItem(get_icon('media-playback-start'), "Direct Downloads")
                item.setForeground(QColor("#3498db"))
            else:
                item = QListWidgetItem(q.name)
                
            if q.paused:
                item.setIcon(get_icon('media-playback-pause'))
                item.setForeground(QColor("#f39c12"))
            else:
                item.setIcon(get_icon('media-playback-start'))
                item.setForeground(QColor("#27ae60"))
            self.queue_list.addItem(item)

        if self.store.queues:
            self._current_queue_idx = min(self._current_queue_idx, len(self.store.queues)-1)
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

        if all_complete and len(q.downloads) > 0:
            self.queue_status_lbl.setText("✅ Complete")
            self.queue_status_lbl.setStyleSheet("color: #27ae60; font-weight: bold;")
            self.schedule_status_lbl.setText("")
            self.status_label.setText("✅ All downloads complete")
            return

        now = datetime.now().time().replace(second=0, microsecond=0)
        now_day = datetime.now().weekday()
        is_scheduled = q.is_scheduled_now()

        if q.paused:
            if q.schedule_enabled:
                self.queue_status_lbl.setText("⏸ Paused")
                self.queue_status_lbl.setStyleSheet("color: #f39c12; font-weight: bold;")
                self.schedule_status_lbl.setText("⏸ Click 'Start' to activate schedule")
                self.schedule_status_lbl.setStyleSheet("color: #f39c12; font-size: 11px;")
                self.status_label.setText("⏸ Paused - Click Start to begin")
            else:
                self.queue_status_lbl.setText("⏸ Paused")
                self.queue_status_lbl.setStyleSheet("color: #f39c12; font-weight: bold;")
                self.schedule_status_lbl.setText("")
                self.status_label.setText("⏸ Paused")
            return

        if q.schedule_enabled:
            if is_scheduled:
                self.queue_status_lbl.setText("▶ Running (🕐 Scheduled)")
                self.queue_status_lbl.setStyleSheet("color: #27ae60; font-weight: bold;")
                self.schedule_status_lbl.setText("🕐 Schedule time is active ✓")
                self.schedule_status_lbl.setStyleSheet("color: #27ae60; font-weight: bold;")
                self.status_label.setText("🕐 Scheduled time is active")
            else:
                days_text = ", ".join(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i] for i in q.days)
                self.queue_status_lbl.setText(f"⏰ Waiting for Schedule")
                self.queue_status_lbl.setStyleSheet("color: #3498db; font-weight: bold;")
                self.schedule_status_lbl.setText(f"⏰ Next: {q.schedule_start.strftime('%H:%M')}-{q.schedule_end.strftime('%H:%M')} {days_text}")
                self.schedule_status_lbl.setStyleSheet("color: #3498db; font-size: 11px;")
                self.status_label.setText(f"⏰ Waiting: {q.schedule_start.strftime('%H:%M')}")
        else:
            self.queue_status_lbl.setText("▶ Running")
            self.queue_status_lbl.setStyleSheet("color: #27ae60; font-weight: bold;")
            self.schedule_status_lbl.setText("")
            self.status_label.setText("▶ Running")

    def _start_current_queue(self):
        q = self._current_queue()
        if not q:
            return
        if q.name == "__direct__":
            return

        is_scheduled = q.is_scheduled_now()
        
        self._apply_settings_to_aria2()

        q.paused = False
        self.store.save()
        self._refresh_queue_list()

        resumed = 0
        for gid in q.downloads:
            real_status = self.aria2.get_status(gid)
            if real_status == "paused":
                result = self.aria2.resume(gid)
                if result is not None:
                    resumed += 1
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "active"
                    if gid in q.downloads_info:
                        q.downloads_info[gid]["status"] = "active"
            elif real_status in ["active", "waiting"]:
                if gid in self._all_downloads:
                    self._all_downloads[gid]["status"] = real_status
                if gid in q.downloads_info:
                    q.downloads_info[gid]["status"] = real_status

        self.store.save()
        self._refresh_table()
        self._update_queue_status()
        self._update_queue_buttons()
        self._update_shutdown_button_state() 

        if resumed > 0:
            self.tray.showMessage("FelfelDM", f"▶️ Resumed {resumed} download(s)",
                                QSystemTrayIcon.MessageIcon.Information, 2000)
        elif is_scheduled:
            days_text = ", ".join(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i] for i in q.days)
            self.tray.showMessage("FelfelDM", 
                f"⏰ Queue started. Waiting for schedule: {q.schedule_start.strftime('%H:%M')}-{q.schedule_end.strftime('%H:%M')} {days_text}",
                QSystemTrayIcon.MessageIcon.Information, 4000)
    
    def _pause_current_queue(self):
        q = self._current_queue()
        if not q:
            return

        if q.name == "__direct__":
            return
        
        q.paused = True
        self.store.save()
        self._refresh_queue_list()

        paused = 0
        for gid in q.downloads:
            real_status = self.aria2.get_status(gid)
            
            if real_status in ["active", "waiting"]:
                self.aria2.pause(gid)
                paused += 1
            
            if gid in self._all_downloads:
                self._all_downloads[gid]["status"] = "paused"
                self._all_downloads[gid]["downloadSpeed"] = 0
            
            if gid in q.downloads_info:
                q.downloads_info[gid]["status"] = "paused"

        self.store.save()
        self._refresh_table()
        self._update_queue_status()
        self._update_queue_buttons()
        self._update_shutdown_button_state() 

        if paused > 0:
            self.tray.showMessage("FelfelDM", f"⏸️ Paused {paused} download(s)",
                                QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            self.tray.showMessage("FelfelDM", "No active downloads to pause",
                                QSystemTrayIcon.MessageIcon.Information, 2000)
   
    def _clear_completed_downloads(self):
        q = self._current_queue()
        if not q:
            return
        
        completed_gids = []
        for gid in q.downloads:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status")
                if status == "complete":
                    completed_gids.append(gid)
        
        if not completed_gids:
            QMessageBox.information(self, "Info", "No completed downloads to clear.")
            return
        
        reply = QMessageBox.question(
            self, 
            "Clear Completed",
            f"Remove {len(completed_gids)} completed download(s) from queue and aria2?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.No:
            return
        
        removed = 0
        for gid in completed_gids:
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
        
        self.tray.showMessage("FelfelDM", f"Removed {removed} completed download(s) from queue and aria2",
                            QSystemTrayIcon.MessageIcon.Information, 2000)

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
        
        if total_size > 0:
            progress = int((completed_size / total_size) * 100)
            self.progress_bar.setValue(min(progress, 100))
            self.progress_bar.setFormat(f"{format_size(completed_size)} / {format_size(total_size)} ({progress}%)")
        else:
            self.progress_bar.setValue(0)
            self.progress_bar.setFormat("No active downloads")

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
        if not q: return
        if q.name == "__direct__":
            QMessageBox.information(self, "Info", "Quick Downloads queue has no settings.")
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
            
            q.proxy_config = d.get("proxy_config")
        
            if q.proxy_config:
                self.proxy_manager.set_queue_proxy(q.name, q.proxy_config)
            else:
                self.proxy_manager.remove_queue_proxy(q.name)
                
            self.store.save()
            self._refresh_queue_list()
            self._update_queue_buttons()
            self._apply_settings_to_aria2()

    def _delete_queue(self):
        q = self._current_queue()
        if not q:
            return
        
        if len(self.store.queues) <= 1:
            QMessageBox.warning(self, "Error", "Cannot delete the last queue.")
            return
        
        if QMessageBox.question(self, "Delete", f"Delete queue '{q.name}'?") == QMessageBox.StandardButton.Yes:
            self.store.queues.pop(self._current_queue_idx)
            self._current_queue_idx = 0
            self.store.save()
            self._refresh_queue_list()
            self._update_queue_buttons()
            
            
    @pyqtSlot(list)
    def _add_downloads_from_extension(self, urls):
        if not urls:
            return
        
        self.show()
        self.raise_()
        self.activateWindow()

        if len(urls) == 1:
            dlg = QuickDownloadDialog(self)
            dlg.url_edit.setText(urls[0])
            
            if dlg.exec():
                d = dlg.get_data()
                if not d["urls"]:
                    return
                
                direct_queue = None
                for q in self.store.queues:
                    if q.name == "__direct__":
                        direct_queue = q
                        break
                if not direct_queue:
                    direct_queue = Queue("__direct__", paused=False, max_concurrent=99)
                    self.store.queues.insert(0, direct_queue)
                
                options = {
                    "dir": d["path"],
                    "split": str(d["connections"]),
                    "max-connection-per-server": str(d["connections"]),
                    "min-split-size": "1M",
                    "continue": "true",
                    "always-resume": "true",
                    "header": ["User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"]
                }
                
                added_gids = []
                for url in d["urls"]:
                    gid = self.aria2.add_url(url, options)
                    if gid:
                        direct_queue.downloads.append(gid)
                        raw_name = url.split('/')[-1]
                        clean_name = raw_name.split('?')[0] if '?' in raw_name else raw_name
                        if not clean_name:
                            clean_name = "Unknown"
                        full_path = os.path.join(d["path"], clean_name)
                        
                        direct_queue.downloads_info[gid] = {
                            "url": url,
                            "name": clean_name,
                            "totalLength": 0,
                            "completedLength": 0,
                            "status": "waiting",
                            "files": [{
                                "path": full_path,
                                "length": "0",
                                "completedLength": "0",
                                "selected": "true",
                                "uris": []
                            }],
                            "category": "📁 Other"
                        }
                        self.aria2.resume(gid)
                        added_gids.append(gid)
                
                self.store.save()
                self._refresh_queue_list()
                self._refresh_table()
                self._update_shutdown_button_state()
                
                if len(added_gids) == 1:
                    QTimer.singleShot(500, lambda: self._open_progress_dialog(added_gids[0]))
            return

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
                "header": ["User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"]
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
                        "name": url.split("/")[-1] or "Unknown"
                    }
                    
                    new_gids.append(gid)
                    added += 1
                    self.aria2.pause(gid)
                    if gid in self._all_downloads:
                        self._all_downloads[gid]["status"] = "paused"
                        self._all_downloads[gid]["downloadSpeed"] = 0
            
            self.store.save()
            self._refresh_queue_list()
            self._update_queue_buttons()
            
            if q and not q.paused and q.is_scheduled_now():
                for gid in new_gids:
                    if gid in self._all_downloads:
                        self.aria2.resume(gid)
                        self._all_downloads[gid]["status"] = "active"
                self._refresh_table()
                self.tray.showMessage("FelfelDM", f"✅ Added {added} download(s) to running queue",
                                    QSystemTrayIcon.MessageIcon.Information, 2000)
            elif added > 0:
                self.tray.showMessage("FelfelDM", f"✅ Added {added} download(s) in paused state",
                                    QSystemTrayIcon.MessageIcon.Information, 2000)
            
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
            valid_lines = [line.strip() for line in clip.split('\n') if line.strip().startswith(("http", "magnet:", "ftp"))]
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
                "header": ["User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"]
            }
            
            if proxy_mode == 0:
                proxy = self.proxy_manager.get_proxy_for_queue(q.name)
                if proxy and proxy.is_valid():
                    options["all-proxy"] = proxy._build_proxy_url()
                    print(f"🌐 Using queue/global proxy for {q.name}: {proxy._build_proxy_url()}")
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
                    
                    raw_name = url.split('/')[-1]
                    clean_name = raw_name.split('?')[0] if '?' in raw_name else raw_name
                    if not clean_name:
                        clean_name = "Unknown"
                    full_path = os.path.join(d["path"], clean_name)
                    
                    q.downloads_info[gid] = {
                        "url": url,
                        "name": clean_name,
                        "totalLength": 0,
                        "completedLength": 0,
                        "status": "waiting",
                        "files": [{
                            "path": full_path,
                            "length": "0",
                            "completedLength": "0",
                            "selected": "true",
                            "uris": []
                        }],
                        "category": "📁 Other"
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
                        "category": "📁 Other"
                    }
            
            self._refresh_table()
            self.store.save()
            self._refresh_queue_list()
            self._update_queue_buttons()
            self._update_shutdown_button_state()

            if q and not q.paused and q.is_scheduled_now():
                for gid in new_gids:
                    if gid in self._all_downloads:
                        self.aria2.resume(gid)
                        self._all_downloads[gid]["status"] = "active"
                self._refresh_table()
                self.tray.showMessage("FelfelDM", f"✅ Added {added} download(s) to running queue",
                                    QSystemTrayIcon.MessageIcon.Information, 2000)
            elif added > 0:
                self.tray.showMessage("FelfelDM", f"✅ Added {added} download(s) in paused state",
                                    QSystemTrayIcon.MessageIcon.Information, 2000)

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
                "header": ["User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"]
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
                    single_queue = Queue("Single Downloads", paused=False, max_concurrent=1)
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

                QMessageBox.information(self, "Success",
                    f"Download added to 'Single Downloads' queue.\n"
                    f"Status: {'Downloading' if data['start_immediately'] else 'Paused'}")
            else:
                QMessageBox.warning(self, "Error", "Could not add download. Is aria2 running?")            

    def _pause_selected(self):
        gid = self._selected_gid()
        if gid:
            self.aria2.pause(gid)
            if gid in self._all_downloads:
                self._all_downloads[gid]["status"] = "paused"
                self._all_downloads[gid]["downloadSpeed"] = 0
                
                q = self._current_queue()
                if q and gid in q.downloads_info:
                    q.downloads_info[gid]["status"] = "paused"
                    self.store.save()
                
            self._refresh_table()
            self._update_toggle_button()

    def _resume_selected(self):
        gid = self._selected_gid()
        if gid:
            q = self._current_queue()
            if q and q.paused and q.name != "__direct__":
                QMessageBox.warning(self, "Queue Paused",
                    "This queue is paused. Please click 'Start Queue' to begin all downloads.")
                return

            self.aria2.resume(gid)
            if gid in self._all_downloads:
                self._all_downloads[gid]["status"] = "active"
                
                if q and gid in q.downloads_info:
                    q.downloads_info[gid]["status"] = "active"
                    self.store.save()
                
            self._refresh_table()
            self._update_toggle_button()

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
        
        delete_files = (result == "remove_files")
        
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
                for path in file_paths:
                    try:
                        if os.path.exists(path):
                            if os.path.isfile(path):
                                os.remove(path)
                                print(f"🗑 Deleted file: {path}")
                            elif os.path.isdir(path):
                                import shutil
                                shutil.rmtree(path)
                                print(f"🗑 Deleted folder: {path}")
                        else:
                            print(f"⚠ File not found: {path}")
                    except Exception as e:
                        print(f"⚠ Could not delete {path}: {e}")
                
                for path in file_paths:
                    aria2_path = path + ".aria2"
                    try:
                        if os.path.exists(aria2_path):
                            os.remove(aria2_path)
                            print(f"🗑 Deleted aria2 file: {aria2_path}")
                    except Exception as e:
                        print(f"⚠ Could not delete {aria2_path}: {e}")
            
            removed += 1
        
        self.store.save()
        self._refresh_table()
        self._refresh_queue_list()
        self._update_queue_buttons()
        
        if removed > 0:
            msg_text = f"Removed {removed} download(s)"
            if delete_files:
                msg_text += " (files and .aria2 files deleted)"
            self.tray.showMessage("FelfelDM", msg_text,
                                QSystemTrayIcon.MessageIcon.Information, 2000)
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
            menu.addAction("Sort by Name", lambda: self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder))
            menu.addAction("Sort by Size", lambda: self.table.sortByColumn(1, Qt.SortOrder.DescendingOrder))
            menu.addAction("Sort by Progress", lambda: self.table.sortByColumn(2, Qt.SortOrder.DescendingOrder))
            menu.addAction("Sort by Speed", lambda: self.table.sortByColumn(3, Qt.SortOrder.DescendingOrder))
            menu.addAction("Sort by Status", lambda: self.table.sortByColumn(5, Qt.SortOrder.AscendingOrder))
            menu.addSeparator()
            menu.addAction("Clear Completed", self._clear_completed_downloads)
            menu.exec(self.table.viewport().mapToGlobal(pos))
            return
        
        dl_data = self._all_downloads.get(gid, {})
        download_name = dl_data.get("name", "Unknown")
        
        # Get real status from aria2
        real_status = self.aria2.get_status(gid)
        if not real_status:
            real_status = dl_data.get("status", "")
        
        menu = QMenu(self)
        
        # Single Pause/Resume option based on real status
        if real_status in ["active", "waiting"]:
            menu.addAction(get_icon('media-playback-pause'), "Pause", self._pause_selected)
        elif real_status == "paused":
            menu.addAction(get_icon('media-playback-start'), "Resume", self._resume_selected)
        
        menu.addSeparator()
        
        # ===== Proxy Settings =====
        proxy_menu = menu.addMenu(get_icon('network'), "Proxy Settings")
        
        current_proxy = self.proxy_manager.get_proxy_for_download(gid)
        if current_proxy:
            proxy_menu.addAction(f"✅ Current: {current_proxy.get_display_string()}")
        else:
            q = self._current_queue()
            if q:
                queue_proxy = self.proxy_manager.get_proxy_for_queue(q.name)
                if queue_proxy:
                    proxy_menu.addAction(f"📦 Queue: {queue_proxy.get_display_string()}")
                else:
                    proxy_menu.addAction("🌐 Global/No Proxy")
        
        proxy_menu.addSeparator()
        proxy_menu.addAction("Set Custom Proxy", lambda: self._set_download_proxy(gid, download_name))
        proxy_menu.addAction("Clear Custom Proxy", lambda: self._clear_download_proxy(gid))
        
        menu.addSeparator()

        # ===== Open Folder =====
        def _open_folder():
            files = dl_data.get("files", [])
            if files and files[0].get("path"):
                path = files[0]["path"]
                folder = os.path.dirname(path)
                if os.path.exists(folder):
                    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        menu.addAction(get_icon('folder'), "Open Folder", _open_folder)

        # ===== Copy URL =====
        def _copy_link():
            files = dl_data.get("files", [])
            if files and files[0].get("uris"):
                QApplication.clipboard().setText(files[0]["uris"][0]["uri"])
        menu.addAction(get_icon('edit-copy'), "Copy URL", _copy_link)

        menu.addSeparator()
        
        # ===== Remove =====
        menu.addAction(get_icon('edit-delete'), "Remove", self._remove_selected)
        
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
        q = self._current_queue()
        if not q:
            self.model.update_rows([])
            return

        rows = []
        search_text = self.search_box.text().strip().lower()

        for gid in q.downloads:
            if gid not in self._all_downloads:
                info = q.downloads_info.get(gid, {})
                if info:
                    self._all_downloads[gid] = {
                        "gid": gid,
                        "name": info.get("name", "Unknown"),
                        "status": info.get("status", "paused"),
                        "totalLength": info.get("totalLength", 0),
                        "completedLength": info.get("completedLength", 0),
                        "downloadSpeed": 0,
                        "connections": 0,
                        "files": info.get("files", []),
                        "errorMessage": "",
                        "category": info.get("category", "📁 Other")
                    }
                else:
                    continue

            row = self._all_downloads[gid].copy()
            real_status = self.aria2.get_status(gid)
            
            if q.paused:
                if real_status not in ["complete", "error", "removed"]:
                    row["status"] = "paused"
                    row["downloadSpeed"] = 0
                    if real_status in ["active", "waiting"]:
                        try:
                            self.aria2.pause(gid)
                        except:
                            pass
                else:
                    row["status"] = real_status
            else:
                if real_status:
                    row["status"] = real_status
                    if real_status == "paused":
                        row["downloadSpeed"] = 0
                        if gid in self._all_downloads:
                            try:
                                self.aria2.resume(gid)
                                row["status"] = "active"
                                print(f"▶️ Auto-resumed {gid} (queue is not paused)")
                            except:
                                pass
                else:
                    info = q.downloads_info.get(gid, {})
                    row["status"] = info.get("status", "waiting")

            if search_text and search_text not in row.get("name", "").lower():
                continue

            rows.append(row)

        self.model.update_rows(rows)   
        
    def _update_toggle_button(self):
        """Update toggle button state based on selected download"""
        if not hasattr(self, 'table') or not self.table.selectionModel():
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon('media-playback-pause'))
            self.btn_move_queue.setEnabled(False)
            return
        
        selected_indexes = self.table.selectionModel().selectedRows()
        if not selected_indexes:
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon('media-playback-pause'))
            self.btn_move_queue.setEnabled(False)
            return
        
        idx = selected_indexes[0]
        if not idx.isValid():
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon('media-playback-pause'))
            self.btn_move_queue.setEnabled(False)
            return
        
        self.btn_move_queue.setEnabled(True)
        
        gid = self.model.get_gid(idx.row())
        
        if not gid:
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon('media-playback-pause'))
            return
        
        # Get real status from aria2
        real_status = self.aria2.get_status(gid)
        
        # If aria2 fails, fallback to _all_downloads
        if not real_status:
            if gid in self._all_downloads:
                real_status = self._all_downloads[gid].get("status")
            else:
                self.btn_toggle.setEnabled(False)
                self.btn_toggle.setText("Pause")
                self.btn_toggle.setIcon(get_icon('media-playback-pause'))
                return
        
        if real_status in ["active", "waiting"]:
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon('media-playback-pause'))
        elif real_status == "paused":
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Resume")
            self.btn_toggle.setIcon(get_icon('media-playback-start'))
        else:  # complete, error, removed
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon('media-playback-pause'))
    
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

            self.aria2.change_global_option({
                "max-concurrent-downloads": str(max_concurrent),
                "max-tries": str(max_tries)
            })
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

        QMessageBox.information(self, "aria2 Restarted",
            "aria2 has been restarted with new settings.")

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
                self.tray.showMessage("FelfelDM", "Settings applied successfully",
                                     QSystemTrayIcon.MessageIcon.Information, 2000)

            self._refresh_table()

    def _start_backend(self):
        print("🚀🚀🚀 _start_backend CALLED")
        self.worker = BackendWorker(self.aria2, self.store)
        print("🚀🚀🚀 worker created")
        self.worker.stats_updated.connect(self._on_stats_received)
        self.worker.aria2_error.connect(self._on_aria2_error)
        self.worker.size_fetched.connect(self._on_size_fetched)
        print("🚀🚀🚀 signals connected")
        self.worker.start()
        print("🚀🚀🚀 worker.start() called")

    def _on_stats_received(self, result):
        if not result.get("connected"):
            self.status_lbl.setText("● Disconnected")
            self.status_lbl.setStyleSheet("color: #e74c3c; font-weight: bold;")
            self.speed_lbl.setText("↓ 0 B/s")
            self._last_calculated_global_speed = 0
            return

        self.status_lbl.setText("● Connected")
        self.status_lbl.setStyleSheet("color: #27ae60; font-weight: bold;")
        stat = result["stat"]
        self._last_calculated_global_speed = int(stat.get("downloadSpeed", 0))
        self.speed_lbl.setText(f"↓ {format_speed(self._last_calculated_global_speed)}")
        self.tray.setToolTip(f"FelfelDM — ↓ {format_speed(self._last_calculated_global_speed)}")

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
                            status = self._all_downloads.get(gid, {}).get("status", "NOT FOUND")
                    
                    all_done = all(
                        self._all_downloads.get(gid, {}).get("status") in ["complete", "error", "removed"]
                        for q in self.store.queues
                        for gid in q.downloads
                    )
                    
                    if all_done and not self._shutdown_dialog_shown: 
                        self._shutdown_dialog_shown = True 
                        self.tray.showMessage(
                            "🌶️ FelfelDM",
                            "✅ All downloads completed!\n🛑 System will shut down in 20 seconds.",
                            QSystemTrayIcon.MessageIcon.Information,
                            5000
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
            
            name = saved_name
            if not name or name == "Unknown":
                files = dl.get("files", [])
                if files and files[0].get("path"):
                    aria2_name = os.path.basename(files[0]["path"])
                    if aria2_name and aria2_name != "Unknown File":
                        name = aria2_name
                elif files and files[0].get("uris"):
                    aria2_name = files[0]["uris"][0]["uri"].split("/")[-1] or "Unknown File"
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
                "errorMessage": dl.get("errorMessage", "")
            }
        
        # Active downloads
        for dl in result["active"]:
            data = process_dl(dl, "active")
            if data:
                all_downloads_dict[data["gid"]] = data

        # Waiting downloads
        for dl in result["waiting"]:
            data = process_dl(dl, "waiting")
            if data and data["gid"] not in all_downloads_dict:
                all_downloads_dict[data["gid"]] = data

        # Stopped downloads
        for dl in result["stopped"]:
            gid = dl.get("gid")
            if gid and gid not in all_downloads_dict:
                data = process_dl(dl, dl.get("status", "stopped"))
                if data:
                    all_downloads_dict[gid] = data

        # Handle pending pause
        for gid, data in all_downloads_dict.items():
            if (
                gid in self._pending_pause
                and int(data.get("totalLength", 0)) > 0
            ):
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
                    
                    q.downloads_info[gid].update({
                        "totalLength": dl.get("totalLength", 0),
                        "completedLength": dl.get("completedLength", 0),
                        "status": dl.get("status", "unknown"),
                        "name": dl.get("name", "Unknown"),
                        "files": dl.get("files", []),
                        "category": dl.get("category", "📁 Other")
                    })
                        
        self.store.save()

        # Check queue completion
        for q in self.store.queues:
            if not q.paused and q.downloads:
                has_any_download = any(gid in self._all_downloads for gid in q.downloads)
                if has_any_download:
                    all_done = all(
                        self._all_downloads.get(gid, {}).get("status") in ["complete", "error", "removed"]
                        for gid in q.downloads
                        if gid in self._all_downloads
                    )
                    if all_done:
                        q.paused = True
                        self.tray.showMessage("FelfelDM", f"✅ Queue '{q.name}' finished!",
                        QSystemTrayIcon.MessageIcon.Information, 4000)
                        self.store.save()

        # Schedule management
        for q in self.store.queues:
            if q.paused or not q.schedule_enabled:
                continue

            if q.is_scheduled_now():
                for gid in q.downloads:
                    if self.aria2.get_status(gid) == "paused":
                        self.aria2.resume(gid)
                        if gid in self._all_downloads:
                            self._all_downloads[gid]["status"] = "active"
            else:
                for gid in q.downloads:
                    if gid in self._all_downloads and self._all_downloads[gid].get("status") == "active":
                        self.aria2.pause(gid)
                        self._all_downloads[gid]["status"] = "paused"
                        self._all_downloads[gid]["downloadSpeed"] = 0

        # ===== Update progress dialog =====
        try:
            if hasattr(self, '_progress_dialog'):
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
            if hasattr(self, '_youtube_dialog'):
                dialog = self._youtube_dialog
                if dialog is not None:
                    try:
                        if dialog.isVisible() and hasattr(dialog, 'worker'):
                            pass
                    except (RuntimeError, AttributeError):
                        self._youtube_dialog = None
        except Exception:
            self._youtube_dialog = None

        # ===== Refresh UI =====
        self._refresh_table()
        self._update_queue_status()
        self._refresh_queue_list()
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
                "aria2c", "--enable-rpc", "--rpc-listen-all",
                "--rpc-allow-origin-all", "--daemon",
                f"--rpc-listen-port={port}",
                f"--max-concurrent-downloads={max_concurrent}",
                f"--max-tries={max_tries}",
                "--max-connection-per-server=16",
                "--split=16",
                "--continue=true",
                "--always-resume=true",
                "--retry-wait=2",
            ]
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
        except FileNotFoundError:
            QMessageBox.critical(self, "aria2 Not Found",
                "aria2 is not installed.\nRun: sudo pacman -S aria2")
    def _on_aria2_error(self, message):
        if "disconnected" in message:
            return
        if "cannot be paused now" in message:
            return
        if "cannot be unpaused now" in message:
            return
        if "is not found" in message:
            return
        self.tray.showMessage("FelfelDM ⚠", message,
                            QSystemTrayIcon.MessageIcon.Warning, 3000)
        self.status_label.setText(f"⚠ {message}")
        
    def _open_progress_dialog(self, gid):
        """Open progress dialog for a download"""
        dl_data = self._all_downloads.get(gid, {})
        
        if hasattr(self, '_progress_dialog') and self._progress_dialog is not None:
            try:
                self._progress_dialog.close()
            except:
                pass
            self._progress_dialog = None
        
        self._progress_dialog = DownloadProgressDialog(gid, dl_data, None) 
        self._progress_dialog.pause_requested.connect(self._pause_from_dialog)
        self._progress_dialog.resume_requested.connect(self._resume_from_dialog)
        self._progress_dialog.cancel_requested.connect(self._cancel_from_dialog)
        self._progress_dialog.cancel_with_delete_requested.connect(self._cancel_with_delete_from_dialog)
        self._progress_dialog.finished.connect(self._on_progress_dialog_closed)
        self._progress_dialog.show()
        
        self._center_dialog_on_screen(self._progress_dialog)

    def _center_dialog_on_screen(self, dialog):
        """Center dialog on screen"""
        screen = QApplication.primaryScreen().geometry()
        dialog.move(
            screen.center().x() - dialog.width() // 2,
            screen.center().y() - dialog.height() // 2
        )

    def _on_progress_dialog_closed(self):
        """Clean up progress dialog reference"""
        if hasattr(self, '_progress_dialog'):
            self._progress_dialog = None

    def _pause_from_dialog(self, gid):
        """Pause download from progress dialog"""
        real_status = self.aria2.get_status(gid)
        if real_status in ["active", "waiting"]:
            self.aria2.force_pause(gid)
            if gid in self._all_downloads:
                self._all_downloads[gid]["status"] = "paused"
                self._all_downloads[gid]["downloadSpeed"] = 0
            
            self._refresh_table()
            self._update_progress_bar()
            
            if hasattr(self, '_progress_dialog') and self._progress_dialog is not None:
                if self._progress_dialog.isVisible() and gid in self._all_downloads:
                    self._progress_dialog.update_data(self._all_downloads[gid])

    def _resume_from_dialog(self, gid):
        """Resume download from progress dialog"""
        real_status = self.aria2.get_status(gid)
        if real_status == "paused":
            self.aria2.resume(gid)
            if gid in self._all_downloads:
                self._all_downloads[gid]["status"] = "active"
            
            self._refresh_table()
            self._update_progress_bar()
            
            if hasattr(self, '_progress_dialog') and self._progress_dialog is not None:
                if self._progress_dialog.isVisible() and gid in self._all_downloads:
                    self._progress_dialog.update_data(self._all_downloads[gid])

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
        
        self.tray.showMessage("FelfelDM", 
            "Download cancelled.",
            QSystemTrayIcon.MessageIcon.Information, 2000)
    
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
        
        self.tray.showMessage("FelfelDM", 
            "Download cancelled and files deleted.",
            QSystemTrayIcon.MessageIcon.Information, 2000)     
           
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
            
            for q in self.store.queues:
                if q.name == queue_name:
                    target_queue = q
                    break
            
            if target_queue is None:
                target_queue = Queue(queue_name, paused=False)
                if queue_name == "__direct__":
                    target_queue.max_concurrent = 99
                self.store.queues.append(target_queue)
                self.store.save()

            options = {
                "dir": d["path"],
                "split": str(d["connections"]),
                "max-connection-per-server": str(d["connections"]),
                "min-split-size": "1M",
                "continue": "true",
                "always-resume": "true",
                "header": ["User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"]
            }

            proxy_mode = d.get("proxy_mode", 0)
            custom_proxy = d.get("custom_proxy") if proxy_mode == 1 else None
            proxy_for_detection = None
            
            if proxy_mode == 0:
                proxy = self.proxy_manager.get_proxy_for_queue(target_queue.name)
                if proxy and proxy.is_valid():
                    options["all-proxy"] = proxy._build_proxy_url()
                    proxy_for_detection = proxy
            elif proxy_mode == 1:
                if custom_proxy and custom_proxy.is_valid():
                    options["all-proxy"] = custom_proxy._build_proxy_url()
                    proxy_for_detection = custom_proxy
            elif proxy_mode == 2:  
                options["all-proxy"] = "" 

            added_gids = []
            for url in d["urls"]:
                gid = self.aria2.add_url(url, options)
                if gid:
                    target_queue.downloads.append(gid)
                    
                    raw_name = url.split('/')[-1]
                    clean_name = raw_name.split('?')[0] if '?' in raw_name else raw_name
                    if not clean_name:
                        clean_name = "Unknown"
                    full_path = os.path.join(d["path"], clean_name)
                    
                    target_queue.downloads_info[gid] = {
                        "url": url,
                        "name": clean_name,
                        "totalLength": 0,
                        "completedLength": 0,
                        "status": "waiting",
                        "files": [{
                            "path": full_path,
                            "length": "0",
                            "completedLength": "0",
                            "selected": "true",
                            "uris": []
                        }],
                        "category": "📁 Other"
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
                        "category": "📁 Other"
                    }
                    
                    if d.get("start_immediately", True):
                        if not target_queue.paused:
                            self.aria2.resume(gid)
                            self._all_downloads[gid]["status"] = "active"
                        else:
                            self.aria2.pause(gid)
                            self._all_downloads[gid]["status"] = "paused"
                    else:
                        self.aria2.pause(gid)
                        self._all_downloads[gid]["status"] = "paused"
                    
                    added_gids.append(gid)

            self.store.save()
            self._refresh_queue_list()
            self._refresh_table()
            self._update_shutdown_button_state()

            if len(added_gids) == 1 and d.get("start_immediately", True) and queue_name == "__direct__":
                QTimer.singleShot(500, lambda: self._open_progress_dialog(added_gids[0]))
    
    def _on_table_double_click(self, index):
        gid = self.model.get_gid(index.row())
        if gid:
            self._open_progress_dialog(gid)
            
    def _close_splash(self):
        if hasattr(self, 'splash') and self.splash:
            self.splash.close()
            self.splash = None
            
    def _youtube_download(self):
        from ui.dialogs import YouTubeDownloadDialog
        
        dlg = YouTubeDownloadDialog(self)
        
        clip = QApplication.clipboard().text().strip()
        if clip and ("youtube.com" in clip or "youtu.be" in clip):
            dlg.url_edit.setText(clip)
        
        if dlg.exec():
            data = dlg.get_data()
            if not data["url"]:
                QMessageBox.warning(self, "Error", "Please enter a YouTube URL.")
                return
            
            os.makedirs(data["path"], exist_ok=True)
            
            proxy_url = data.get("proxy_url")
            
            from ui.youtube_progress import YouTubeProgressDialog
            self._youtube_dialog = YouTubeProgressDialog(
                url=data["url"],
                output_path=data["path"],
                format_type=data["format"],
                cookie_file=data["cookie_file"],
                video_info=data.get("video_info"),
                parent=None,
                proxy_url=proxy_url
            )
            self._youtube_dialog.show() 
            
            self._youtube_dialog.worker.finished.connect(
                lambda success, msg: self._on_youtube_finished(success, msg)
            )

    def _on_youtube_finished(self, success, message):
        """Handle YouTube download finished"""
        if success:
            self.tray.showMessage(
                "FelfelDM",
                "✅ YouTube download completed!",
                QSystemTrayIcon.MessageIcon.Information,
                3000
            )
        else:
            self.tray.showMessage(
                "FelfelDM",
                f"❌ YouTube download failed: {message}",
                QSystemTrayIcon.MessageIcon.Warning,
                3000
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
        
        # Get real status from aria2
        real_status = self.aria2.get_status(gid)
        
        # If aria2 fails, fallback to _all_downloads
        if not real_status:
            if gid in self._all_downloads:
                real_status = self._all_downloads[gid].get("status")
            else:
                return
        
        if real_status in ["active", "waiting"]:
            self._pause_selected()
        elif real_status == "paused":
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
                self.tray.showMessage("FelfelDM", 
                    f"✅ Custom proxy set for: {download_name}",
                    QSystemTrayIcon.MessageIcon.Information, 2000)
            else:
                self.proxy_manager.set_download_proxy(gid, None)
                self.tray.showMessage("FelfelDM", 
                    f"ℹ️ Proxy cleared for: {download_name}",
                    QSystemTrayIcon.MessageIcon.Information, 2000)
            
            # Refresh table
            self._refresh_table()

    def _clear_download_proxy(self, gid):
        """Clear custom proxy for a download"""
        self.proxy_manager.set_download_proxy(gid, None)
        dl_data = self._all_downloads.get(gid, {})
        name = dl_data.get("name", "Unknown")
        
        self.tray.showMessage("FelfelDM", 
            f"🗑 Proxy cleared for: {name}",
            QSystemTrayIcon.MessageIcon.Information, 2000)
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

        target_queues = [q for q in self.store.queues if q.name != source_queue.name and q.name != "__direct__"]
        
        if not target_queues:
            QMessageBox.warning(self, "Error", "No other queues available to move to.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Move to Queue")
        dlg.setMinimumWidth(400)
        
        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        info_label = QLabel(f"Move {len(gids_to_move)} download(s) from '{source_queue.name}' to:")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        queue_combo = QComboBox()
        for q in target_queues:
            queue_combo.addItem(q.name, q)
        layout.addWidget(queue_combo)
        
        layout.addSpacing(10)
        
        btn_layout = QHBoxLayout()
        btn_move = QPushButton("Move")
        btn_move.setIcon(get_icon('go-next'))
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
            2000
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
            3000
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
            2000
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