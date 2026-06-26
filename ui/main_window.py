# ui/main_window.py

import os
import time
import subprocess
from datetime import datetime
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

from core import Aria2RPC, DataStore, Queue, BackendWorker
from ui.dialogs import AddDownloadDialog, SingleDownloadDialog, QueueSettingsDialog, SettingsDialog
from ui.table_model import DownloadTableModel
from ui.delegates import ProgressDelegate
from utils.helpers import format_size, format_speed, get_category, get_icon
from core.local_server import LocalServer

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
       
        self.setWindowTitle("DL Manager")
        self.setMinimumSize(1050, 680)

        self.store = DataStore()
        
        default_exists = False
        for q in self.store.queues:
            if q.name == "Default":
                default_exists = True
                break
        
        if not default_exists:
            default_queue = Queue("Default", paused=True)
            self.store.queues.insert(0, default_queue)  # اول لیست قرار بده
            self.store.save()
            
        self.aria2 = Aria2RPC(
            self.store.settings["aria2_host"],
            self.store.settings["aria2_port"],
            self.store.settings["aria2_secret"],
        )
        self._current_queue_idx = 0
        self._all_downloads = {}
        self._last_calculated_global_speed = 0
        self._cleared_gids = set()

        self._build_ui()
        self._build_tray()
        self._start_aria2_if_needed()
        self._apply_global_speed_limit()
        self._start_backend()
        
        self.local_server = LocalServer(main_window=self)
        self.local_server.start(8765)
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ─── سایدبار (با QSplitter برای تغییر اندازه) ──────────────────────
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

        # ─── سایدبار ──────────────────────────────────────────────────────────
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
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(10, 12, 10, 12)
        sb_lay.setSpacing(8)

        header_lay = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(get_icon('download-manager').pixmap(32, 32))
        header_lay.addWidget(icon)
        title = QLabel("<b>DL Manager</b>")
        title.setStyleSheet("font-size: 16px; color: #efeff1;")
        header_lay.addWidget(title)
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

        # ─── بخش اصلی ──────────────────────────────────────────────────────────
        main_area = QWidget()
        ma_lay = QVBoxLayout(main_area)
        ma_lay.setContentsMargins(0, 0, 0, 0)
        ma_lay.setSpacing(0)

        # تولبار
        toolbar = QWidget()
        toolbar.setStyleSheet("""
            QWidget {
                background-color: #2d2d30;
                border-bottom: 1px solid #1e1e20;
                padding: 4px;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                color: #efeff1;
            }
            QPushButton:hover { background-color: #3a3f44; }
            QPushButton:pressed { background-color: #1e1e20; }
            QPushButton:disabled { opacity: 0.4; }
            QLineEdit {
                background-color: #1e1e20;
                border: 1px solid #3d4045;
                border-radius: 4px;
                padding: 4px 8px;
                color: #efeff1;
            }
            QLineEdit:focus { border: 1px solid #3daee9; }
        """)
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(8, 4, 8, 4)
        tb_lay.setSpacing(4)

        self.btn_add = QPushButton(get_icon('list-add'), "Add")
        self.btn_add.clicked.connect(self._add_download)
        tb_lay.addWidget(self.btn_add)


        self.btn_pause = QPushButton(get_icon('media-playback-pause'), "Pause")
        self.btn_pause.clicked.connect(self._pause_selected)
        tb_lay.addWidget(self.btn_pause)

        self.btn_resume = QPushButton(get_icon('media-playback-start'), "Resume")
        self.btn_resume.clicked.connect(self._resume_selected)
        tb_lay.addWidget(self.btn_resume)

        self.btn_remove = QPushButton(get_icon('edit-delete'), "Remove")
        self.btn_remove.clicked.connect(self._remove_selected)
        tb_lay.addWidget(self.btn_remove)

        self.btn_clear_completed = QPushButton(get_icon('edit-clear'), "Clear Completed")
        self.btn_clear_completed.clicked.connect(self._clear_completed_downloads)
        tb_lay.addWidget(self.btn_clear_completed)

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

        # جدول
        self.table = QTableView()
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.setWordWrap(False)   
        self.table.setAlternatingRowColors(True)
        self.model = DownloadTableModel()
        self.progress_delegate = ProgressDelegate(self)
        self.table.setItemDelegateForColumn(2, self.progress_delegate)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        ma_lay.addWidget(self.table)

        # نوار وضعیت
        self.statusBar().setStyleSheet("QStatusBar { background-color: #2d2d30; color: #efeff1; }")
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
        self.shutdown_cb.setStyleSheet("QCheckBox { color: #efeff1; }")
        self.statusBar().addPermanentWidget(self.shutdown_cb)

        splitter.addWidget(sidebar)
        splitter.addWidget(main_area)
        splitter.setSizes([210, 840])

        root.addWidget(splitter)

        # منو
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
        self.tray.setIcon(get_icon('download-manager'))

        menu = QMenu()
        menu.addAction(get_icon('window'), "Show", self.show)
        menu.addAction(get_icon('application-exit'), "Quit", self.quit_app)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda r: self.show() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()

    def _show_about(self):
        QMessageBox.about(self, "About DL Manager",
            "<h2 style='color: #3daee9;'>DL Manager</h2>"
            "<p>A modern download manager</p>"
            "<p>Built with PyQt6 and aria2</p>"
            "<p style='color: #95a5a6;'>Using Papirus icons</p>")

    def closeEvent(self, e):
        e.ignore()
        self.hide()

    def quit_app(self):
        if hasattr(self, 'worker'):
            self.worker.running = False
            self.worker.wait()
        self.store.save()

        if hasattr(self, 'tray'):
            self.tray.hide()

        QApplication.quit()

    # ─── مدیریت صف ──────────────────────────────────────────────────────────

    def _on_queue_changed(self, idx):
        if idx >= 0:
            self._current_queue_idx = idx
            self._update_queue_status()
            self._update_queue_buttons()
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

        is_scheduled = q.is_scheduled_now()
        
        self._apply_settings_to_aria2()

        q.paused = False
        self.store.save()
        self._refresh_queue_list()

        resumed = 0
        if is_scheduled:
            for gid in q.downloads:
                if gid in self._all_downloads:
                    status = self._all_downloads[gid].get("status")
                    if status == "paused":
                        result = self.aria2.resume(gid)
                        if result is not None:
                            resumed += 1
                            self._all_downloads[gid]["status"] = "active"
        else:
            days_text = ", ".join(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i] for i in q.days)
            self.tray.showMessage("DL Manager", 
                f"⏰ Queue started. Waiting for schedule: {q.schedule_start.strftime('%H:%M')}-{q.schedule_end.strftime('%H:%M')} {days_text}",
                QSystemTrayIcon.MessageIcon.Information, 4000)

        self._refresh_table()
        self._update_queue_status()
        self._update_queue_buttons()

        if resumed > 0:
            self.tray.showMessage("DL Manager", f"Started {resumed} download(s)",
                                QSystemTrayIcon.MessageIcon.Information, 2000)

    def _pause_current_queue(self):
        q = self._current_queue()
        if not q:
            return

        q.paused = True
        self.store.save()
        self._refresh_queue_list()

        paused = 0
        for gid in q.downloads:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status")
                if status == "active":
                    self.aria2.pause(gid)
                    paused += 1
                    self._all_downloads[gid]["status"] = "paused"
                    self._all_downloads[gid]["downloadSpeed"] = 0
                elif status == "waiting":
                    self.aria2.pause(gid)
                    self._all_downloads[gid]["status"] = "paused"

        self._refresh_table()
        self._update_queue_status()
        self._update_queue_buttons()

        if paused > 0:
            self.tray.showMessage("DL Manager", f"Paused {paused} download(s)",
                                QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            self.tray.showMessage("DL Manager", "No active downloads to pause",
                                QSystemTrayIcon.MessageIcon.Information, 2000)

    def _clear_completed_downloads(self):
        """پاک کردن دانلودهای کامل شده از صف و aria2"""
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
        
        self.tray.showMessage("DL Manager", f"Removed {removed} completed download(s) from queue and aria2",
                            QSystemTrayIcon.MessageIcon.Information, 2000)

    def _update_progress_bar(self):
        """به‌روزرسانی نوار پیشرفت"""
        q = self._current_queue()
        total_size = 0
        completed_size = 0
        
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
            # جلوگیری از ایجاد صف با اسم Default
            if name.strip() == "Default":
                QMessageBox.warning(self, "Error", "Queue name 'Default' is reserved.")
                return
            
            self.store.queues.append(Queue(name.strip(), paused=True))
            self.store.save()
            self._refresh_queue_list()
            self._update_queue_buttons()

    def _edit_queue(self):
        q = self._current_queue()
        if not q: return
        dlg = QueueSettingsDialog(q, self)
        if dlg.exec():
            d = dlg.get_queue_data()
            q.name = d["name"]
            q.save_path = d["save_path"]
            q.max_concurrent = d["max_concurrent"]
            q.schedule_enabled = d["schedule_enabled"]
            q.schedule_start = d["schedule_start"]
            q.schedule_end = d["schedule_end"]
            q.days = d["days"]
            self.store.save()
            self._refresh_queue_list()
            self._update_queue_buttons()
            self._apply_settings_to_aria2()

    def _delete_queue(self):
        q = self._current_queue()
        if not q:
            return
        
        # 🔥 جلوگیری از پاک کردن صف Default
        if q.name == "Default":
            QMessageBox.warning(self, "Error", "Cannot delete the Default queue.")
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
            
            
    def _add_downloads_from_extension(self, urls):
        """اضافه کردن دانلود از اکستنشن با استفاده از AddDownload Dialog"""
        if not urls:
            return
        
        # برنامه رو جلو بیار
        self.show()
        self.raise_()
        self.activateWindow()
        
        # پیدا کردن index صف Default
        default_idx = 0
        for i, q in enumerate(self.store.queues):
            if q.name == "Default":
                default_idx = i
                break
        
        # ایجاد دیالوگ AddDownload با صف Default انتخاب شده
        dlg = AddDownloadDialog(self.store.queues, default_idx, self)
        dlg.url_edit.setPlainText("\n".join(urls))  # لینک‌ها رو پر کن
        
        if dlg.exec():
            d = dlg.get_data()
            if not d["urls"]:
                return
            
            queue_index = d["queue"]
            if queue_index < 0 or queue_index >= len(self.store.queues):
                QMessageBox.warning(self, "Error", "Selected queue does not exist.")
                return
            
            q = self.store.queues[queue_index]
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
                self.tray.showMessage("DL Manager", f"✅ Added {added} download(s) to running queue",
                                    QSystemTrayIcon.MessageIcon.Information, 2000)
            elif added > 0:
                self.tray.showMessage("DL Manager", f"✅ Added {added} download(s) in paused state",
                                    QSystemTrayIcon.MessageIcon.Information, 2000)
            
            self._refresh_table()
    def _add_download(self):
        dlg = AddDownloadDialog(self.store.queues, self._current_queue_idx, self)

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
            if queue_index < 0 or queue_index >= len(self.store.queues):
                QMessageBox.warning(self, "Error", "Selected queue does not exist.")
                return

            q = self.store.queues[queue_index]

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
                self.tray.showMessage("DL Manager", f"✅ Added {added} download(s) to running queue",
                                    QSystemTrayIcon.MessageIcon.Information, 2000)
            elif added > 0:
                self.tray.showMessage("DL Manager", f"✅ Added {added} download(s) in paused state",
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

            options = {
                "dir": data["path"],
                "split": str(data["connections"]),
                "max-connection-per-server": str(data["connections"]),
                "continue": "true",
                "always-resume": "true",
                "header": ["User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"]
            }

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
            self._refresh_table()

    def _resume_selected(self):
        gid = self._selected_gid()
        if gid:
            q = self._current_queue()
            if q and q.paused:
                QMessageBox.warning(self, "Queue Paused",
                    "This queue is paused. Please click 'Start Queue' to begin all downloads.")
                return

            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status")
                if status == "paused":
                    self.aria2.resume(gid)
                    self._all_downloads[gid]["status"] = "active"

            self._refresh_table()

    def _remove_selected(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "Info", "No downloads selected.")
            return

        count = len(selected)
        if QMessageBox.question(self, "Remove", f"Remove {count} download(s)?") == QMessageBox.StandardButton.Yes:
            removed = 0
            gids_to_remove = []
            for idx in selected:
                gid = self.model.get_gid(idx.row())
                if gid:
                    gids_to_remove.append(gid)

            for gid in gids_to_remove:
                self.aria2.remove(gid)
                for q in self.store.queues:
                    if gid in q.downloads:
                        q.downloads.remove(gid)
                if gid in self._all_downloads:
                    del self._all_downloads[gid]
                removed += 1

            self.store.save()
            self._refresh_table()
            self._refresh_queue_list()
            self._update_queue_buttons()

            if removed > 0:
                self.tray.showMessage("DL Manager", f"Removed {removed} download(s)",
                                     QSystemTrayIcon.MessageIcon.Information, 2000)

    def _selected_gid(self):
        idx = self.table.currentIndex()
        return self.model.get_gid(idx.row()) if idx.isValid() else None

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

        menu = QMenu(self)
        menu.addAction(get_icon('media-playback-pause'), "Pause", self._pause_selected)
        menu.addAction(get_icon('media-playback-start'), "Resume", self._resume_selected)
        menu.addSeparator()

        def _open_folder():
            files = dl_data.get("files", [])
            if files and files[0].get("path"):
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(files[0]["path"])))
        menu.addAction(get_icon('folder'), "Open Folder", _open_folder)

        def _copy_link():
            files = dl_data.get("files", [])
            if files and files[0].get("uris"):
                QApplication.clipboard().setText(files[0]["uris"][0]["uri"])
        menu.addAction(get_icon('edit-copy'), "Copy URL", _copy_link)

        menu.addSeparator()
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
        """به‌روزرسانی جدول با اطلاعات دانلودهای صف جاری"""
        q = self._current_queue()
        
        if not q:
            self.model.update_rows([])
            return

        all_rows = []
        for gid in q.downloads:
            # اگر دانلود در کش وجود دارد
            if gid in self._all_downloads:
                row = self._all_downloads[gid].copy()
                current_status = row.get('status')
            
                if not q.paused:
                    if current_status == 'paused' and current_status not in ['complete', 'removed']:
                        row['status'] = 'waiting'
                        row['downloadSpeed'] = 0
                    # اگر دانلود active هست، همون active بمونه
                    elif current_status == 'active':
                        # سرعت رو از کش بگیر
                        pass
                    elif current_status == 'error':
                        row['status'] = 'waiting'
                        row['downloadSpeed'] = 0
                        pass
                    elif current_status == 'waiting':
                        pass
                    elif current_status in ['complete', 'removed']:
                        pass
                else:
                    if current_status not in ['complete', 'removed']:
                        row['status'] = 'paused'
                        row['downloadSpeed'] = 0
                
                all_rows.append(row)
            
            # اگر دانلود در کش وجود ندارد، از aria2 اطلاعات بگیریم
            else:
                try:
                    # دریافت اطلاعات دانلود از aria2 با tell_status
                    dl_info = self.aria2.tell_status(gid)
                    if dl_info:
                        # استخراج نام فایل
                        name = "Unknown File"
                        files = dl_info.get("files", [])
                        if files and files[0].get("path"):
                            name = os.path.basename(files[0]["path"])
                        elif files and files[0].get("uris"):
                            name = files[0]["uris"][0]["uri"].split("/")[-1] or "Unknown File"
                        
                        if not name or name == "Unknown File":
                            bittorrent = dl_info.get("bittorrent", {})
                            info = bittorrent.get("info", {})
                            name = info.get("name", "Unknown File")
                        
                        # دریافت وضعیت واقعی از aria2
                        real_status = dl_info.get("status", "unknown")
                        
                        # استخراج سرعت دانلود
                        speed = dl_info.get("downloadSpeed", 0)
                        try:
                            speed = int(speed)
                        except (ValueError, TypeError):
                            speed = 0
                        
                        # ساخت ردیف
                        row = {
                            "gid": gid,
                            "name": name,
                            "category": get_category(name),
                            "status": real_status,  # وضعیت واقعی از aria2
                            "totalLength": dl_info.get("totalLength", 0),
                            "completedLength": dl_info.get("completedLength", 0),
                            "downloadSpeed": speed,
                            "files": dl_info.get("files", []),
                            "connections": dl_info.get("connections", 0),
                            "errorMessage": dl_info.get("errorMessage", "")
                        }
                        
                        # اگر صف Pause است و دانلود کامل یا خطا نیست، paused کن
                        if q.paused and real_status not in ['complete', 'error', 'removed']:
                            row['status'] = 'paused'
                            row['downloadSpeed'] = 0
                        # اگر صف در حال اجراست و دانلود paused است، به waiting تغییر بده
                        elif not q.paused and real_status == 'paused' and real_status not in ['complete', 'error', 'removed']:
                            row['status'] = 'waiting'
                            row['downloadSpeed'] = 0
                        
                        # ذخیره در کش
                        self._all_downloads[gid] = row
                        all_rows.append(row)
                    else:
                        # اگر اطلاعاتی دریافت نشد، یک ردیف پیش‌فرض با وضعیت unknown
                        row = {
                            "gid": gid,
                            "name": f"Unknown ({gid[:8]})",
                            "category": "other",
                            "status": "unknown",
                            "totalLength": 0,
                            "completedLength": 0,
                            "downloadSpeed": 0,
                            "files": [],
                            "connections": 0,
                            "errorMessage": "Download not found in aria2"
                        }
                        all_rows.append(row)
                
                except Exception as e:
                    # در صورت خطا، دانلود را با وضعیت error نمایش بده
                    print(f"⚠ Could not fetch info for GID {gid}: {e}")
                    row = {
                        "gid": gid,
                        "name": f"Error ({gid[:8]})",
                        "category": "other",
                        "status": "error",
                        "totalLength": 0,
                        "completedLength": 0,
                        "downloadSpeed": 0,
                        "files": [],
                        "connections": 0,
                        "errorMessage": str(e)
                    }
                    all_rows.append(row)

        # اعمال فیلتر جستجو
        search_text = self.search_box.text().strip()
        if search_text:
            filtered_rows = []
            for row in all_rows:
                name = row.get("name", "").lower()
                if search_text.lower() in name:
                    filtered_rows.append(row)
            rows_to_show = filtered_rows
        else:
            rows_to_show = all_rows

        # به‌روزرسانی مدل
        current_sort_col = self.model.sort_column
        current_sort_order = self.model.sort_order
        
        self.model.update_rows(rows_to_show)
        
        # اعمال مرتب‌سازی قبلی
        if current_sort_col >= 0 and len(rows_to_show) > 0:
            self.model.sort(current_sort_col, current_sort_order)
            
    def _toggle_shutdown(self, checked):
        self.store.settings["shutdown_after_finish"] = checked
        self.store.save()

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

            if not self._apply_settings_to_aria2():
                self._restart_aria2()
            else:
                self.tray.showMessage("DL Manager", "Settings applied successfully",
                                     QSystemTrayIcon.MessageIcon.Information, 2000)

    def _start_backend(self):
        self.worker = BackendWorker(self.aria2, self.store)
        self.worker.stats_updated.connect(self._on_stats_received)
        self.worker.start()

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
        self.tray.setToolTip(f"DL Manager — ↓ {format_speed(self._last_calculated_global_speed)}")

        self._apply_settings_to_aria2()

        # ─── پاک کردن خودکار کامل شده‌ها ──────────────────────────────────────
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

        # ─── به‌روزرسانی نوار پیشرفت ──────────────────────────────────────────
        self._update_progress_bar()

        # ─── بررسی Shutdown ────────────────────────────────────────────────────
        if self.shutdown_cb.isChecked():
            total_active = int(stat.get("numActive", 0))
            total_waiting = int(stat.get("numWaiting", 0))
            if total_active == 0 and total_waiting == 0:
                all_done = True
                for q in self.store.queues:
                    if q.downloads:
                        for gid in q.downloads:
                            if gid in self._all_downloads:
                                status = self._all_downloads[gid].get("status")
                                if status not in ["complete", "error", "removed"]:
                                    all_done = False
                                    break
                if all_done:
                    self.tray.showMessage("DL Manager", "All downloads complete! Shutting down...",
                                        QSystemTrayIcon.MessageIcon.Information, 3000)
                    os.system("systemctl poweroff")

        # ─── به‌روزرسانی کش دانلودها ──────────────────────────────────────────
        all_downloads_dict = {}
        
        def process_dl(dl, default_status):
            gid = dl.get("gid")
            if not gid:
                return None
            
            if gid in self._cleared_gids:
                return None
            
            name = "Unknown File"
            files = dl.get("files", [])
            if files and files[0].get("path"):
                name = os.path.basename(files[0]["path"])
            elif files and files[0].get("uris"):
                name = files[0]["uris"][0]["uri"].split("/")[-1] or "Unknown File"
            
            if not name or name == "Unknown File":
                bittorrent = dl.get("bittorrent", {})
                info = bittorrent.get("info", {})
                name = info.get("name", "Unknown File")

            speed = dl.get("downloadSpeed", 0)
            try:
                speed = int(speed)
            except (ValueError, TypeError):
                speed = 0

            return {
                "gid": gid,
                "name": name,
                "category": get_category(name),
                "status": default_status,
                "totalLength": dl.get("totalLength", 0),
                "completedLength": dl.get("completedLength", 0),
                "downloadSpeed": speed,
                "files": dl.get("files", []),
                "connections": dl.get("connections", 0),
                "errorMessage": dl.get("errorMessage", "")
            }

        # پردازش active
        for dl in result["active"]:
            data = process_dl(dl, "active")
            if data:
                all_downloads_dict[data["gid"]] = data

        # پردازش waiting
        for dl in result["waiting"]:
            data = process_dl(dl, "waiting")
            if data and data["gid"] not in all_downloads_dict:
                all_downloads_dict[data["gid"]] = data

        # پردازش stopped
        for dl in result["stopped"]:
            gid = dl.get("gid")
            if gid and gid not in all_downloads_dict:
                data = process_dl(dl, dl.get("status", "stopped"))
                if data:
                    all_downloads_dict[gid] = data

        # ─── حفظ وضعیت Paused از کش قبلی ──────────────────────────────────────
        for gid, old_data in self._all_downloads.items():
            if gid in all_downloads_dict and old_data.get("status") == "paused":
                all_downloads_dict[gid]["status"] = "paused"
                all_downloads_dict[gid]["downloadSpeed"] = 0

        self._all_downloads = all_downloads_dict

        for q in self.store.queues:
            if q.paused:
                for gid in q.downloads:
                    if gid in self._all_downloads:
                        status = self._all_downloads[gid].get("status")
                        # فقط دانلودهای active و waiting رو pause کن
                        if status in ["active", "waiting"]:
                            self.aria2.pause(gid)
                            self._all_downloads[gid]["status"] = "paused"
                            self._all_downloads[gid]["downloadSpeed"] = 0
                        # وضعیت‌های complete و error رو دست نزن
                        elif status in ["complete", "error", "removed"]:
                            # هیچ کاری نکن، وضعیتشون رو حفظ کن
                            pass

        # ─── به‌روزرسانی جدول ──────────────────────────────────────────────────
        self._refresh_table()
        
        # ─── به‌روزرسانی وضعیت صف ──────────────────────────────────────────────
        self._update_queue_status()
    
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