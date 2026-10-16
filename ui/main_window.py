import os
import time
import subprocess
import re
import uuid
import shutil
import signal
from datetime import datetime
from typing import Dict, List, Optional, Any, Set

from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

from core import (
    Aria2RPC,
    DataStore,
    Queue,
    BackendWorker,
    QueueOperationWorker,
    ScheduleManagerThread,
    ScheduleConfig,
)
from ui.dialogs import *
from ui.table_model import DownloadTableModel
from ui.delegates import ProgressDelegate, CategoryDelegate
from ui.youtube_progress import YouTubeProgressDialog
from ui.export_dialog import ExportDialog
from ui.export_manager import ExportManager
from ui.update_dialog import UpdateDialog
from ui.widgets import DropOverlay

from utils.helpers import (
    format_size,
    format_speed,
    get_icon,
    get_resource_path,
)
from core.local_server import LocalServer
from utils.style import setup_style, make_primary
from ui.splash import SplashScreen
from core.proxy_manager import ProxyManager
from core.rule_engine import expand_path


class MainWindow(QMainWindow):
    _aria2_error_signal = pyqtSignal(str)

    _PERMANENT_ERROR_PATTERNS = (
        "403",
        "401",
        "404",
        "410",
        "451",
        "unauthorized",
        "forbidden",
        "not found",
        "gone",
        "certificate",
        "cert verify",
        "unsupported",
        "invalid url",
        "malformed",
        "bad request",
    )

    def __init__(self) -> None:
        super().__init__()
        self._init_variables()
        self._init_ui()
        self._init_backend()
        self._init_services()
        self._setup_shortcuts()
        self._startup_complete = True

        if self.store.settings.get("start_minimized", False):
            QTimer.singleShot(0, self._minimize_to_tray)

    def _init_variables(self) -> None:
        self.store = DataStore()
        self._all_downloads: Dict[str, Dict[str, Any]] = {}
        self._current_queue_idx: int = 0
        self._retrying_gids: Set[str] = set()
        self._retry_timers: Dict[str, QTimer] = {}
        self._retry_state: Dict[str, dict] = {}
        # download_id -> (time healthy streak began, completedLength at that time)
        self._healthy_since: Dict[str, tuple] = {}
        self._countdown_timer: Optional[QTimer] = None
        self._pending_pause: Set[str] = set()
        self._shutdown_dialog_shown: bool = False
        self._progress_dialogs: Dict[str, DownloadProgressDialog] = {}
        self._youtube_dialogs: Dict[str, "YouTubeProgressDialog"] = {}
        self._shutdown_dialog: Optional[QDialog] = None
        self._speed_samples: List[int] = []
        self._max_samples: int = 8
        self._last_speed_update: float = time.time()
        self._smooth_speed: int = 0
        self._last_calculated_global_speed: int = 0
        self._shutdown_countdown: int = 20
        self.worker: Optional[BackendWorker] = None
        self._first_stats_received = False
        self._queue_worker: Optional[QueueOperationWorker] = None
        self.local_server: Optional[LocalServer] = None
        self.speed_update_timer: Optional[QTimer] = None
        self.splash = None
        self._details_visible = False
        self.details_panel = None
        self._completed_gids: Set[str] = set()
        self._cancelling_youtube: Set[str] = set()
        # Downloads whose size fetch finished without a result (shown as
        # "Unknown"; they must not block starting a queue).
        self._size_unknown: Set[str] = set()
        self._queue_list_dirty = True
        self._open_dialogs: Dict[str, QDialog] = {}
        self._pending_status: Dict[str, tuple] = {}
        self._last_speed_limit_active_count: Optional[int] = None
        self._last_schedules_hash: Optional[int] = None
        self.tray_icon_normal = None
        self.tray_icon_active = None
        self._last_tray_state = False
        self._startup_complete = False
        self.export_manager = ExportManager(self)
        self.schedule_thread = None
        self._drop_overlay: Optional[DropOverlay] = None

    def _init_ui(self) -> None:
        theme_setting: str = self.store.settings.get("theme", "auto")
        is_dark: bool = self._detect_theme(theme_setting)

        self.splash = SplashScreen(is_dark=is_dark)
        self.splash.update_status("Loading FelfelDM...", 5)
        QApplication.processEvents()

        self.setWindowTitle("FelfelDM")
        self.setMinimumSize(1300, 680)
        self.resize(1400, 680)

        self.splash.update_status("Setting up queues...", 25)
        QApplication.processEvents()
        self._ensure_default_queue()

        self.splash.update_status("Building interface...", 70)
        QApplication.processEvents()
        self._build_ui()

        self._drop_overlay = None

        self.splash.update_status("Building tray...", 80)
        QApplication.processEvents()
        self._build_tray()

        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)
        self._countdown_timer.timeout.connect(self._tick_retry_countdown)

    def _init_backend(self) -> None:
        if self.splash is None:
            raise RuntimeError("Splash screen not initialized! Call _init_ui first.")

        self.splash.update_status("Initializing aria2...", 35)
        QApplication.processEvents()

        self.aria2 = Aria2RPC(
            self.store.settings["aria2_host"],
            self.store.settings["aria2_port"],
            self.store.settings["aria2_secret"],
        )

        self.schedule_thread = ScheduleManagerThread(
            store=self.store,
            aria2=self.aria2,
            check_interval=5.0,
        )
        self.schedule_thread.start_queue.connect(self._on_schedule_start)
        self.schedule_thread.pause_queue.connect(self._on_schedule_pause)
        self.schedule_thread.start()

        self.proxy_manager = ProxyManager(self.store)
        self._apply_proxy_to_aria2()
        self._aria2_error_signal.connect(self._on_aria2_error)
        self.aria2.on_error = self._aria2_error_signal.emit

        self.splash.update_status("Connecting to aria2...", 45)
        QApplication.processEvents()

        if not self.aria2.is_connected():
            self.splash.update_status("Starting aria2 daemon...", 55)
            self._start_aria2_if_needed()
            QApplication.processEvents()

        self.splash.update_status("aria2 ready!", 60)
        QApplication.processEvents()

        self.splash.update_status("Applying settings...", 85)
        QApplication.processEvents()
        self._apply_global_speed_limit()
        self._apply_settings_to_aria2()

        self.splash.update_status("Starting services...", 90)
        QApplication.processEvents()
        self._start_backend()

        self.splash.update_status("Waiting for aria2...", 92)
        QApplication.processEvents()

        wait_count = 0
        while not self.aria2.is_connected() and wait_count < 25:
            time.sleep(0.2)
            wait_count += 1

        self.splash.update_status("Restoring downloads...", 93)
        QApplication.processEvents()
        self._restore_downloads()
        self._load_schedules()
        self.speed_update_timer = QTimer()
        self.speed_update_timer.timeout.connect(self._update_speed_display)
        self.speed_update_timer.start(300)

        self.splash.update_status("Ready!", 100)
        QApplication.processEvents()
        QTimer.singleShot(800, self._close_splash)

    def _init_services(self) -> None:
        if self.splash:
            self.splash.update_status("Starting local server...", 95)
            QApplication.processEvents()

        self.local_server = LocalServer(main_window=self)
        self.local_server.start(8766)

    def _minimize_to_tray(self):
        self.hide()

        if hasattr(self, "tray") and self.tray:
            QTimer.singleShot(
                100,
                lambda: self.tray.showMessage(
                    "FelfelDM",
                    "Started minimized to system tray.",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                ),
            )

    def _detect_theme(self, theme_setting: str) -> bool:
        if theme_setting == "light":
            return False
        if theme_setting == "dark":
            return True

        from utils.style import detect_system_theme

        return detect_system_theme()

    def _ensure_default_queue(self) -> None:
        if not self.store.queues:
            default_queue = Queue("Default", paused=True)
            self.store.queues.append(default_queue)
            self.store.save()

    def _start_aria2_if_needed(self) -> None:
        """Start aria2 if it isn't already running.

        C44/C56 fix:
        - Removed --rpc-listen-all and --rpc-allow-origin-all. The
          browser extension talks to LocalServer (8765/8766), never
          directly to aria2, so aria2 has no business listening on
          anything but loopback.
        - Moved --rpc-secret from argv to a 0600 config file. The old
          code leaked the secret to every local user via
          /proc/<pid>/cmdline.
        """
        if self.aria2.is_connected():
            return
        try:
            port = self.store.settings["aria2_port"]
            max_tries = self.store.settings.get("max_tries", 5)
            max_concurrent = self.store.settings.get("max_concurrent", 5)

            config_dir = os.path.expanduser("~/.config/felfelDM")
            session_file = os.path.join(config_dir, "aria2.session")
            pid_file = os.path.join(config_dir, "aria2.pid")
            conf_path = os.path.join(config_dir, "aria2.conf")

            os.makedirs(config_dir, exist_ok=True)
            if not os.path.exists(session_file):
                open(session_file, "w").close()

            disable_ssl = self.store.settings.get("disable_ssl_verify", False)
            conf_lines = [
                "# Auto-generated by FelfelDM. Do not edit manually.",
                f"rpc-listen-port={port}",
                "rpc-listen-all=false",
                "rpc-allow-origin-all=false",
                f"max-concurrent-downloads={max_concurrent}",
                f"max-tries={max_tries}",
                "max-connection-per-server=16",
                "split=16",
                "continue=true",
                "always-resume=true",
                "retry-wait=2",
                f"save-session={session_file}",
                f"input-file={session_file}",
                "save-session-interval=60",
                "pause=true",
                f"pid-file={pid_file}",
                "check-certificate=" + ("false" if disable_ssl else "true"),
            ]
            if self.aria2.secret:
                conf_lines.append(f"rpc-secret={self.aria2.secret}")
            conf_content = "\n".join(conf_lines) + "\n"

            # Write with 0600 from the start.
            fd = os.open(conf_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(conf_content)
            except Exception:
                try:
                    os.close(fd)
                except OSError:
                    pass
                raise
            try:
                os.chmod(conf_path, 0o600)
            except OSError:
                pass

            cmd = [
                "aria2c",
                "--enable-rpc",
                "--daemon",
                f"--conf-path={conf_path}",
            ]

            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2.0)

        except FileNotFoundError:
            QMessageBox.critical(
                self,
                "aria2 Not Found",
                "aria2 is not installed.",
            )

    def _on_schedule_start(self, queue_name: str):
        """UI notification that the scheduler has started a queue.

        The scheduler already did the real work (unpaused aria2
        downloads, updated the store). We need to:
          1. Reload the queue's paused flag from the store, because
             the scheduler may have changed it while the UI was
             frozen (Wayland lock).
          2. Refresh the UI so the user sees the new state.
        """
        print(f"🔔 [UI] Scheduler started queue: {queue_name}")

        # The store is the source of truth: re-read what the scheduler
        # wrote. We also update the live runtime dicts to match.
        for i, q in enumerate(self.store.queues):
            if q.name != queue_name:
                continue

            # Re-read paused from the store.
            # q.paused was already updated by the scheduler via the
            # shared store object — but if the UI was frozen during
            # the write, our local view may be stale. Force a refresh.
            self._all_downloads  # touch to avoid lints
            for gid in q.downloads:
                info = q.downloads_info.get(gid)
                if not info:
                    continue
                # Trust the store's "status" field.
                new_status = info.get("status", "")
                if gid in self._all_downloads and new_status:
                    self._all_downloads[gid]["status"] = new_status

            self._queue_list_dirty = True
            self._refresh_queue_list()
            self._refresh_table()
            self._update_queue_status()
            self._update_queue_buttons()
            self._update_shutdown_button_state()
            break

    def _on_schedule_pause(self, queue_name: str):
        """UI notification that the scheduler has paused a queue."""
        print(f"🔔 [UI] Scheduler paused queue: {queue_name}")

        for i, q in enumerate(self.store.queues):
            if q.name != queue_name:
                continue

            for gid in q.downloads:
                info = q.downloads_info.get(gid)
                if not info:
                    continue
                new_status = info.get("status", "")
                if gid in self._all_downloads and new_status:
                    self._all_downloads[gid]["status"] = new_status
                    if new_status == "paused":
                        self._all_downloads[gid]["downloadSpeed"] = 0

            self._queue_list_dirty = True
            self._refresh_queue_list()
            self._refresh_table()
            self._update_queue_status()
            self._update_queue_buttons()
            self._update_shutdown_button_state()
            break

    def _load_schedules(self):
        schedules = []
        for q in self.store.queues:
            if q.schedule_enabled:
                schedules.append(
                    ScheduleConfig(
                        queue_name=q.name,
                        start=q.schedule_start,
                        end=q.schedule_end,
                        days=set(q.days),
                        enabled=True,
                    )
                )

        # Only push to the schedule thread if something actually changed.
        # _load_schedules is called from several places (startup, queue edit,
        # settings save) and re-pushing an identical schedule list churns the
        # manager's _running_queues set, causing spurious start/pause signals.
        fingerprint = hash(
            tuple(
                sorted(
                    (s.queue_name, s.start, s.end, tuple(sorted(s.days)))
                    for s in schedules
                )
            )
        )
        if fingerprint == self._last_schedules_hash:
            return

        self._last_schedules_hash = fingerprint
        self.schedule_thread.set_schedules(schedules)
        print(f"📅 [Schedule] Loaded {len(schedules)} schedule(s)")

    def _stop_own_aria2(self) -> None:
        """Stop only the aria2 instance we started"""
        pid_file = os.path.join(os.path.expanduser("~/.config/felfelDM"), "aria2.pid")

        if not os.path.exists(pid_file):
            print("⚠️ No PID file found, skipping aria2 shutdown")
            return

        try:
            with open(pid_file, "r") as f:
                pid = int(f.read().strip())

            print(f"🛑 Stopping aria2 with PID: {pid}")

            os.kill(pid, signal.SIGTERM)

            for _ in range(10):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.2)
                except OSError:
                    break

            if os.path.exists(pid_file):
                os.remove(pid_file)
            print(f"✅ aria2 (PID: {pid}) stopped successfully")

        except FileNotFoundError:
            print("⚠️ PID file not found")
        except ProcessLookupError:
            print("⚠️ Process already terminated")
            if os.path.exists(pid_file):
                os.remove(pid_file)
        except Exception as e:
            print(f"⚠️ Error stopping aria2: {e}")

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("splitter")
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)

        sidebar = self._build_sidebar()
        main_area = self._build_main_area()

        splitter.addWidget(sidebar)
        splitter.addWidget(main_area)
        splitter.setSizes([260, 840])

        root.addWidget(splitter)

        self._build_menubar()

        self._refresh_queue_list()
        self._update_queue_buttons()

        self._update_queue_status()

    def _build_sidebar(self) -> QWidget:
        """Sidebar layout (top to bottom):

        header (title + New)  →  queue list  →  tool row for the selected queue
        →  "queue card" (state, limits, schedule, Start / Pause)  →  connection footer
        """
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(230)
        sidebar.setMaximumWidth(360)
        sb_lay = QVBoxLayout(sidebar)
        sb_lay.setContentsMargins(14, 16, 14, 12)
        sb_lay.setSpacing(10)

        # ── Header: title + New queue ──────────────────────────────
        header_lay = QHBoxLayout()
        header_lay.setContentsMargins(2, 0, 0, 0)
        header_lay.setSpacing(8)
        queues_title = QLabel("Queues")
        queues_title.setObjectName("section_title")
        header_lay.addWidget(queues_title)
        header_lay.addStretch()
        new_queue_btn = QPushButton(get_icon("list-add"), "", clicked=self._add_queue)
        new_queue_btn.setFixedSize(36, 36)
        new_queue_btn.setToolTip("Create a new queue")
        new_queue_btn.setProperty("compact", True)
        make_primary(new_queue_btn)
        header_lay.addWidget(new_queue_btn)
        sb_lay.addLayout(header_lay)

        # ── Queue list ─────────────────────────────────────────────
        self.queue_list = QListWidget()
        self.queue_list.setFrameShape(QFrame.Shape.NoFrame)
        self.queue_list.setSpacing(2)
        self.queue_list.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.queue_list.currentRowChanged.connect(self._on_queue_changed)
        sb_lay.addWidget(self.queue_list, 1)

        # ── Tools for the selected queue (icon buttons) ────────────
        tools_lay = QHBoxLayout()
        tools_lay.setSpacing(6)

        def tool_button(icon_name, fallback_text, tooltip, slot):
            btn = QPushButton()
            icon = get_icon(icon_name)
            if icon.isNull():
                btn.setText(fallback_text)
            else:
                btn.setIcon(icon)
            btn.setToolTip(tooltip)
            btn.setProperty("tool", True)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(slot)
            tools_lay.addWidget(btn)
            return btn

        self.move_up_btn = tool_button(
            "go-up", "↑", "Move queue up", self._move_queue_up
        )
        self.move_down_btn = tool_button(
            "go-down", "↓", "Move queue down", self._move_queue_down
        )
        tools_lay.addSpacing(6)
        tool_button("configure", "⚙", "Queue settings", self._edit_queue)
        delete_queue_btn = tool_button(
            "list-remove", "✕", "Delete queue", self._delete_queue
        )
        delete_queue_btn.setProperty("variant", "danger")
        sb_lay.addLayout(tools_lay)

        # ── Queue card: state + limits + schedule + Start/Pause ────
        card = QFrame()
        card.setObjectName("queue_card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(14, 12, 14, 14)
        card_lay.setSpacing(6)

        # Status row: icon + text
        self.queue_status_row = QWidget()
        qsr_lay = QHBoxLayout(self.queue_status_row)
        qsr_lay.setContentsMargins(0, 0, 0, 0)
        qsr_lay.setSpacing(6)

        self.queue_status_icon = QLabel()
        self.queue_status_icon.setFixedSize(18, 18)
        self.queue_status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qsr_lay.addWidget(self.queue_status_icon)

        self.queue_status_lbl = QLabel("Paused")
        self.queue_status_lbl.setStyleSheet(
            "color: #f39c12; font-weight: bold; font-size: 14px;"
        )
        qsr_lay.addWidget(self.queue_status_lbl)
        qsr_lay.addStretch()

        card_lay.addWidget(self.queue_status_row)

        self.speed_limit_lbl = QLabel("")
        self.speed_limit_lbl.setStyleSheet("color: #f39c12; font-size: 11px;")
        card_lay.addWidget(self.speed_limit_lbl)

        # Schedule row: icon + text
        self.schedule_status_row = QWidget()
        ssr_lay = QHBoxLayout(self.schedule_status_row)
        ssr_lay.setContentsMargins(0, 0, 0, 0)
        ssr_lay.setSpacing(6)

        self.schedule_status_icon = QLabel()
        self.schedule_status_icon.setFixedSize(14, 14)
        self.schedule_status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ssr_lay.addWidget(self.schedule_status_icon, 0, Qt.AlignmentFlag.AlignTop)

        self.schedule_status_lbl = QLabel("")
        self.schedule_status_lbl.setStyleSheet("color: #3498db; font-size: 11px;")
        self.schedule_status_lbl.setWordWrap(True)
        ssr_lay.addWidget(self.schedule_status_lbl, 1)

        card_lay.addWidget(self.schedule_status_row)

        card_lay.addSpacing(4)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(8)
        self.start_queue_btn = QPushButton(get_icon("media-playback-start"), "Start")
        self.start_queue_btn.setObjectName("start_btn")
        self.start_queue_btn.setProperty("variant", "success")
        self.start_queue_btn.setMinimumHeight(36)
        self.start_queue_btn.clicked.connect(self._start_current_queue)
        btn_layout.addWidget(self.start_queue_btn)

        self.pause_queue_btn = QPushButton(get_icon("media-playback-pause"), "Pause")
        self.pause_queue_btn.setObjectName("pause_btn")
        self.pause_queue_btn.setProperty("variant", "warning")
        self.pause_queue_btn.setMinimumHeight(36)
        self.pause_queue_btn.clicked.connect(self._pause_current_queue)
        btn_layout.addWidget(self.pause_queue_btn)
        card_lay.addLayout(btn_layout)
        sb_lay.addWidget(card)

        # ── Footer: connection status ──────────────────────────────
        separator = QFrame()
        separator.setObjectName("sidebar_separator")
        separator.setFixedHeight(1)
        sb_lay.addWidget(separator)

        self.status_lbl = QLabel("● Disconnected")
        self.status_lbl.setStyleSheet("color: #e74c3c; font-weight: bold;")
        self.status_lbl.setContentsMargins(2, 0, 0, 0)
        sb_lay.addWidget(self.status_lbl)
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
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        self.model = DownloadTableModel()
        self.progress_delegate = ProgressDelegate(self)
        self.table.setItemDelegateForColumn(2, self.progress_delegate)

        self.category_delegate = CategoryDelegate(self)
        self.table.setItemDelegateForColumn(7, self.category_delegate)
        self.table.setModel(self.model)

        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setHighlightSections(False)

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)  # Name
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)  # Size
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)  # Progress
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)  # Speed
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)  # Conns
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)  # ETA
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)  # Status
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Interactive)  # Category

        # Default widths (user can resize freely afterwards)
        self.table.setColumnWidth(0, 260)  # Name
        self.table.setColumnWidth(1, 104)  # Size
        self.table.setColumnWidth(2, 190)  # Progress
        self.table.setColumnWidth(3, 110)  # Speed
        self.table.setColumnWidth(4, 72)  # Conns
        self.table.setColumnWidth(5, 100)  # ETA
        self.table.setColumnWidth(6, 170)  # Status
        self.table.setColumnWidth(7, 120)  # Category

        # Right-click on the header to reset column widths
        header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        header.customContextMenuRequested.connect(self._header_context_menu)

        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        # Table + friendly empty-state message stacked on top of each other
        table_holder = QWidget()
        table_stack = QStackedLayout(table_holder)
        table_stack.setContentsMargins(0, 0, 0, 0)
        table_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)
        table_stack.addWidget(self.table)
        self.empty_state = QLabel()
        self.empty_state.setObjectName("empty_state")
        self.empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_state.setWordWrap(True)
        self.empty_state.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        table_stack.addWidget(self.empty_state)
        ma_lay.addWidget(table_holder, 1)
        self.model.modelReset.connect(self._refresh_empty_state)
        self.model.rowsInserted.connect(self._refresh_empty_state)
        self.model.rowsRemoved.connect(self._refresh_empty_state)
        self._refresh_empty_state()

        if self.table.selectionModel():
            self.table.selectionModel().selectionChanged.connect(
                self._update_toggle_button
            )

        self.details_panel = self._build_details_panel()
        self.details_panel.setVisible(True)
        self._details_visible = True
        ma_lay.addWidget(self.details_panel)

        self._build_status_bar()

        return main_area

    def _build_toolbar(self) -> QWidget:
        toolbar = QWidget()
        toolbar.setObjectName("toolbar")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(12, 10, 12, 10)
        tb_lay.setSpacing(6)

        icon_size = QSize(20, 20)

        def divider():
            line = QFrame()
            line.setObjectName("toolbar_divider")
            line.setFixedHeight(22)
            return line

        self.btn_add = QPushButton(get_icon("download"), "Add Download")
        self.btn_add.setIconSize(icon_size)
        make_primary(self.btn_add)
        self.btn_add.clicked.connect(self._add_download)
        tb_lay.addWidget(self.btn_add)
        tb_lay.addSpacing(4)
        tb_lay.addWidget(divider())
        tb_lay.addSpacing(4)
        self.btn_toggle = QPushButton(get_icon("media-playback-pause"), "Pause")
        self.btn_toggle.setIconSize(icon_size)
        self.btn_toggle.clicked.connect(self._toggle_pause_resume)
        self.btn_toggle.setEnabled(False)
        tb_lay.addWidget(self.btn_toggle)

        self.btn_move_queue = QPushButton(get_icon("go-next"), "Move to Queue")
        self.btn_move_queue.setIconSize(icon_size)
        self.btn_move_queue.clicked.connect(self._move_selected_to_queue)
        self.btn_move_queue.setEnabled(False)
        tb_lay.addWidget(self.btn_move_queue)

        self.btn_remove = QPushButton(get_icon("edit-delete"), "Remove")
        self.btn_remove.setIconSize(icon_size)
        self.btn_remove.setProperty("variant", "ghost-danger")
        self.btn_remove.clicked.connect(self._remove_selected)
        tb_lay.addWidget(self.btn_remove)

        self.btn_clear_completed = QPushButton(
            get_icon("edit-clear"), "Clear Completed"
        )
        self.btn_clear_completed.setIconSize(icon_size)
        self.btn_clear_completed.clicked.connect(self._clear_completed_downloads)
        tb_lay.addWidget(self.btn_clear_completed)
        tb_lay.addSpacing(4)
        tb_lay.addWidget(divider())
        tb_lay.addSpacing(4)

        self.btn_youtube = QPushButton(get_icon("applications-multimedia"), " YouTube")
        self.btn_youtube.setIconSize(icon_size)
        self.btn_youtube.setText(" YouTube")
        self.btn_youtube.clicked.connect(self._youtube_download)
        tb_lay.addWidget(self.btn_youtube)

        tb_lay.addStretch()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search downloads…")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setMinimumWidth(200)
        self.search_box.setMaximumWidth(280)
        self.search_box.setFixedHeight(34)
        self.search_box.textChanged.connect(self._filter_downloads)
        self.search_box.textChanged.connect(self._refresh_empty_state)
        tb_lay.addWidget(self.search_box)

        self.btn_show_details = QPushButton(get_icon("view-list-details"), "")
        self.btn_show_details.setProperty("iconOnly", True)
        self.btn_show_details.setIconSize(icon_size)
        self.btn_show_details.setToolTip("Toggle details panel (Ctrl+D)")
        self.btn_show_details.setCheckable(True)
        self.btn_show_details.toggled.connect(self._toggle_details_panel)
        tb_lay.addWidget(self.btn_show_details)

        self.btn_settings = QPushButton(get_icon("configure"), "")
        self.btn_settings.setProperty("iconOnly", True)
        self.btn_settings.setToolTip("Settings (Ctrl+,)")
        self.btn_settings.setIconSize(icon_size)
        self.btn_settings.clicked.connect(self._open_settings)
        tb_lay.addWidget(self.btn_settings)

        return toolbar

    def _build_status_bar(self) -> None:
        speed_widget = QWidget()
        speed_layout = QHBoxLayout(speed_widget)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(4)

        self.speed_icon_label = QLabel()
        self.speed_icon_label.setPixmap(get_icon("go-down").pixmap(16, 16))

        self.speed_status_label = QLabel("0 B/s")
        self.speed_status_label.setObjectName("speed_label")

        speed_layout.addWidget(self.speed_icon_label)
        speed_layout.addWidget(self.speed_status_label)
        self.statusBar().addPermanentWidget(speed_widget)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)

        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().addPermanentWidget(self.progress_bar)
        self.progress_bar.setTextVisible(True)

        self.status_label = QLabel("Ready")
        self.statusBar().addPermanentWidget(self.status_label)

        self.shutdown_cb = QCheckBox("Shutdown on Finish")
        self.shutdown_cb.setStyleSheet("margin:0 8px;")
        self.shutdown_cb.setChecked(
            self.store.settings.get("shutdown_after_finish", False)
        )
        self.shutdown_cb.toggled.connect(self._toggle_shutdown)
        self.statusBar().addPermanentWidget(self.shutdown_cb)

    def _build_menubar(self) -> None:
        mb = self.menuBar()

        file_menu = mb.addMenu("&File")
        add_action = QAction(get_icon("download"), "Add Download", self)
        add_action.triggered.connect(self._add_download)
        add_action.setShortcut("Ctrl+N")
        file_menu.addAction(add_action)

        file_menu.addSeparator()

        export_action = QAction(get_icon("document-save"), "Export Downloads", self)
        export_action.triggered.connect(self._export_downloads)
        export_action.setShortcut("Ctrl+E")
        file_menu.addAction(export_action)

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

        log_action = QAction(get_icon("text-x-generic"), "Show Logs", self)
        log_action.triggered.connect(self._show_log_viewer)
        log_action.setShortcut("Ctrl+L")
        view_menu.addAction(log_action)

        help_menu = mb.addMenu("&Help")
        help_menu.addAction("About", self._show_about)
        help_menu.addAction("Shortcuts", self._show_shortcuts)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self)

        normal_path = get_resource_path("logo/icon512.png")
        if os.path.exists(normal_path):
            self.tray_icon_normal = QIcon(normal_path)
        else:
            self.tray_icon_normal = get_icon("download-manager")

        active_path = get_resource_path("logo/tray-active.png")
        if os.path.exists(active_path):
            self.tray_icon_active = QIcon(active_path)
        else:
            self.tray_icon_active = self.tray_icon_normal

        self.tray.setIcon(self.tray_icon_normal)

        menu = QMenu()
        menu.addAction(get_icon("window"), "Show", self.show)
        menu.addAction(get_icon("application-exit"), "Quit", self.quit_app)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        """Toggle window visibility when the tray icon is clicked.

        Behavior:
        - Single left click toggles: if the window is visible and
          active, hide it (minimize to tray); otherwise show + raise
          + activate it.
        - Double click always shows and raises (this is what most
          users expect from a tray icon).
        - Middle click and right click are ignored (right click
          opens the context menu automatically).
        """
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show()
            self.raise_()
            self.activateWindow()
            return

        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show()
                if self.isMinimized():
                    self.showNormal()
                self.raise_()
                self.activateWindow()

    def _start_backend(self) -> None:
        print("🚀 Starting BackendWorker...")

        self.worker = BackendWorker(
            self.aria2, self.store, proxy_manager=self.proxy_manager
        )

        self.worker.stats_updated.connect(self._on_stats_received)
        self.worker.aria2_error.connect(self._on_aria2_error)
        self.worker.size_fetched.connect(self._on_size_fetched)
        self.worker.size_failed.connect(self._on_size_failed)

        self.worker.youtube_progress.connect(self._on_youtube_progress)
        self.worker.youtube_status.connect(self._on_youtube_status)
        self.worker.youtube_speed.connect(self._on_youtube_speed)
        self.worker.youtube_finished.connect(self._on_youtube_finished)
        self.worker.youtube_size_fetched.connect(self._on_youtube_size_fetched)

        self.worker.operation_result.connect(self._on_worker_operation_result)

        self.worker.start()
        print("✅ BackendWorker started")

    def _start_current_queue(self) -> None:
        """Start the entire queue"""
        print("▶️ Starting queue...")

        q = self._current_queue()
        if not q or q.name == "__direct__":
            return

        if q.schedule_enabled and not q.is_scheduled_now():
            self._show_schedule_info(q)
            return

        error_gids = []
        normal_gids = []
        youtube_gids = []

        for gid in q.downloads:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                dtype = self._all_downloads[gid].get("download_type", "normal")

                if dtype == "youtube":
                    youtube_gids.append(gid)
                    continue

                if status in ["error", "stopped"]:
                    error_gids.append(gid)
                else:
                    normal_gids.append(gid)

        for gid in error_gids:
            print(f"🔄 Retrying error download from queue start: {gid}")
            self._retry_single_download(gid)

        for gid in normal_gids:
            if gid in self._all_downloads:
                self._all_downloads[gid]["error_count"] = 0
                self._all_downloads[gid]["errorMessage"] = ""
                self._all_downloads[gid]["status"] = "waiting"
                if gid in q.downloads_info:
                    q.downloads_info[gid]["status"] = "waiting"

                self._pending_status.pop(gid, None)

        q.manually_paused = False
        self._apply_settings_to_aria2()
        q.paused = False
        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()

        if normal_gids:
            temp_queue = Queue(q.name, paused=False)
            temp_queue.downloads = normal_gids
            for gid in normal_gids:
                if gid in q.downloads_info:
                    temp_queue.downloads_info[gid] = q.downloads_info[gid]

            self._queue_worker = QueueOperationWorker(temp_queue, "start", self)
            self._connect_queue_worker_signals()
            self._queue_worker.start()
        else:
            self._queue_worker = None

        for gid in youtube_gids:
            print(f"🎬 Starting YouTube download from queue start: {gid}")
            self._start_youtube_download(gid)

        self.start_queue_btn.setEnabled(False)
        self.pause_queue_btn.setEnabled(False)
        self._last_speed_limit_active_count = None
        self._apply_queue_speed_limit(q)

    def _pause_current_queue(self):
        q = self._current_queue()
        if not q or q.name == "__direct__":
            return

        if q.schedule_enabled:
            q.schedule_enabled = False
            q.manually_paused = True
            self.tray.showMessage(
                "FelfelDM",
                f"⏸️ Queue '{q.name}' paused manually.\n⏰ Schedule disabled.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )

        q.paused = True
        q.manually_paused = True
        self.store.save()

        # Ask aria2 directly which gids are currently active/waiting.
        # We cannot trust _all_downloads[gid]["status"] here because
        # the scheduler may have changed aria2's state while the UI
        # was frozen (Wayland lock).
        #
        # IMPORTANT: we collect *download_ids* (not aria2 gids) here,
        # because _worker_pause_multi expects download_ids and will
        # translate them to aria2 gids itself. Sending aria2 gids
        # would cause _get_aria2_gid() to return None for each one,
        # silently dropping every gid — which is exactly why the
        # queue was "paused" in the UI but still downloading.
        download_ids_to_pause = []
        for gid in q.downloads:
            info = q.downloads_info.get(gid, {})
            dtype = info.get("download_type", "normal")

            if dtype == "youtube":
                # YouTube handled via the existing _pause_youtube_download path.
                if gid in self._all_downloads:
                    st = self._all_downloads[gid].get("status", "")
                    if st in ("downloading", "active", "waiting"):
                        self._pause_youtube_download(gid)
                        self._all_downloads[gid]["status"] = "paused"
                        if gid in q.downloads_info:
                            q.downloads_info[gid]["status"] = "paused"
                continue

            aria2_gid = info.get("aria2_gid")
            if not aria2_gid:
                continue

            # Ask aria2 for the real status.
            real_status = ""
            try:
                st = self.aria2.get_status(aria2_gid)
                if st:
                    real_status = st.get("status", "")
            except Exception:
                pass

            # If aria2 reports the download is active or waiting, we
            # want to pause it. We use the download_id (gid), not the
            # aria2 gid, because _worker_pause_multi resolves the
            # aria2 gid from _all_downloads itself.
            if real_status in ("active", "waiting", "paused"):
                download_ids_to_pause.append(gid)

            # Update our local view to match aria2.
            if real_status in ("active", "waiting"):
                if gid in self._all_downloads:
                    self._all_downloads[gid]["status"] = "paused"
                    self._all_downloads[gid]["downloadSpeed"] = 0
                if gid in q.downloads_info:
                    q.downloads_info[gid]["status"] = "paused"

        if download_ids_to_pause:
            print(
                f"⏸️ [UI] Pausing queue '{q.name}': "
                f"{len(download_ids_to_pause)} download(s)"
            )
            self._worker_pause_multi(download_ids_to_pause)
        else:
            print(f"⏸️ [UI] Queue '{q.name}' has no active downloads to pause")

        self.store.save()
        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_status()
        self._update_queue_buttons()
        self._update_shutdown_button_state()

        self.tray.showMessage(
            "FelfelDM",
            f"⏸️ Queue '{q.name}' paused",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    def _header_context_menu(self, pos) -> None:
        """Context menu shown when right-clicking the table header."""
        menu = QMenu(self)

        menu.addAction(
            get_icon("view-refresh"),
            "Fit Column Widths",
            self._fit_column_widths,
        )

        menu.addSeparator()

        header = self.table.horizontalHeader()
        col = header.logicalIndexAt(pos)
        if col >= 0:
            menu.addAction(
                f"Fit '{self.model.COLS[col]}' to Contents",
                lambda c=col: self.table.resizeColumnToContents(c),
            )

        menu.exec(header.mapToGlobal(pos))

    def _fit_column_widths(self) -> None:
        """fit all download table columns to fit the viewport exactly.

        Widths are distributed proportionally so the total never exceeds
        the viewport — no horizontal scrollbar appears.
        """
        header = self.table.horizontalHeader()
        available = self.table.viewport().width()
        if available <= 0:
            return

        # Column proportions (sum = 1.00)
        ratios = {
            0: 0.28,  # Name
            1: 0.09,  # Size
            2: 0.16,  # Progress
            3: 0.11,  # Speed
            4: 0.06,  # Conns
            5: 0.10,  # ETA
            6: 0.12,  # Status
            7: 0.08,  # Category
        }

        # Resize interactively so the user can still adjust them later
        for col in ratios:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)

        # Compute and apply widths. Rounding errors are absorbed by the
        # last column so the total exactly matches the viewport width.
        total = sum(ratios.values())
        assigned = 0
        cols = sorted(ratios.keys())

        for i, col in enumerate(cols):
            if i == len(cols) - 1:
                width = available - assigned
            else:
                width = int(available * (ratios[col] / total))
                assigned += width

            self.table.setColumnWidth(col, max(40, width))

    def _show_log_viewer(self) -> None:
        from ui.log_viewer import LogViewerDialog

        key = "log_viewer"
        existing = self._open_dialogs.get(key)
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.raise_()
                    existing.activateWindow()
                    return
            except RuntimeError:
                self._open_dialogs.pop(key, None)

        dlg = LogViewerDialog(parent=self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._open_dialogs[key] = dlg

        def _cleanup(*_):
            if self._open_dialogs.get(key) is dlg:
                self._open_dialogs.pop(key, None)

        dlg.finished.connect(_cleanup)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _connect_queue_worker_signals(self) -> None:
        if not self._queue_worker:
            return

        self._queue_worker.progress.connect(
            lambda current, total: self.status_label.setText(
                f"⏳ Processing... {current}/{total}"
            )
        )
        self._queue_worker.status_update.connect(
            lambda msg: self.status_label.setText(msg)
        )
        self._queue_worker.download_status_changed.connect(
            self._on_download_status_changed
        )
        self._queue_worker.finished.connect(self._on_queue_operation_finished)

    def _show_schedule_info(self, q: Queue) -> None:
        next_time = q.get_next_schedule_time()
        if next_time:
            time_str = next_time.strftime("%H:%M on %A")
            QMessageBox.information(
                self,
                "Queue Scheduled",
                f"This queue is scheduled to start at {time_str}.\n\n"
                f"It will start automatically at that time.",
                QMessageBox.StandardButton.Ok,
            )
        else:
            QMessageBox.information(
                self,
                "Queue Scheduled",
                "This queue is scheduled but no upcoming time found.",
                QMessageBox.StandardButton.Ok,
            )

    def _mark_pending_status(self, gid: str, status: str, ttl: float = 3.0) -> None:
        self._pending_status[gid] = (status, time.time() + ttl)

    def _on_download_status_changed(self, gid: str, status: str) -> None:
        if gid in self._all_downloads:
            self._all_downloads[gid]["status"] = status
            if status == "paused":
                self._all_downloads[gid]["downloadSpeed"] = 0

        for q in self.store.queues:
            if gid in q.downloads_info:
                q.downloads_info[gid]["status"] = status
                break

        QMetaObject.invokeMethod(
            self, "_delayed_ui_update", Qt.ConnectionType.QueuedConnection
        )

    @pyqtSlot()
    def _delayed_ui_update(self) -> None:
        self._refresh_table()
        self._update_queue_status()
        self._update_queue_buttons()

    def _on_queue_operation_finished(self, success: bool, message: str) -> None:

        self.start_queue_btn.setEnabled(True)
        self.pause_queue_btn.setEnabled(True)

        self.status_label.setText(message)
        self.tray.showMessage(
            "FelfelDM",
            message,
            (
                QSystemTrayIcon.MessageIcon.Information
                if success
                else QSystemTrayIcon.MessageIcon.Warning
            ),
            2000,
        )

        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_status()
        self._update_queue_buttons()
        self._update_shutdown_button_state()

        q = self._current_queue()
        if q:
            self._apply_queue_speed_limit(q)

        self._queue_worker = None

    def _current_queue(self) -> Optional[Queue]:
        if 0 <= self._current_queue_idx < len(self.store.queues):
            return self.store.queues[self._current_queue_idx]
        return None

    def _selected_gid(self) -> Optional[str]:
        """Return the gid of the selected download, or None.

        Returns None when zero or more than one row is selected, so
        the Details Panel and per-download actions never operate on
        an ambiguous selection.
        """
        if not self.table.selectionModel():
            return None

        rows = self.table.selectionModel().selectedRows()
        if len(rows) != 1:
            return None

        idx = rows[0]
        return self.model.get_gid(idx.row()) if idx.isValid() else None

    def _to_int(self, value: Any) -> int:
        try:
            if value is None:
                return 0
            if isinstance(value, str):
                return int(value) if value.strip() else 0
            return int(value) if value else 0
        except (ValueError, TypeError):
            return 0

    def _get_aria2_gid(self, download_id: str) -> Optional[str]:
        if not download_id:
            return None
        data = self._all_downloads.get(download_id)
        if not data:
            return None
        return data.get("aria2_gid")

    def _worker_pause(self, download_id: str) -> None:
        aria2_gid = self._get_aria2_gid(download_id)
        if aria2_gid:
            self.worker.pause_requested.emit(aria2_gid)

    def _worker_resume(self, download_id: str) -> None:
        aria2_gid = self._get_aria2_gid(download_id)
        if aria2_gid:
            self.worker.resume_requested.emit(aria2_gid)

    def _worker_remove(self, download_id: str) -> None:
        aria2_gid = self._get_aria2_gid(download_id)
        if aria2_gid:
            self.worker.remove_requested.emit(aria2_gid)

    def _worker_pause_multi(self, download_ids: list) -> None:
        aria2_gids = [self._get_aria2_gid(d) for d in download_ids]
        aria2_gids = [g for g in aria2_gids if g]
        if aria2_gids:
            self.worker.pause_multi_requested.emit(aria2_gids)

    def _worker_resume_multi(self, download_ids: list) -> None:
        aria2_gids = [self._get_aria2_gid(d) for d in download_ids]
        aria2_gids = [g for g in aria2_gids if g]
        if aria2_gids:
            self.worker.resume_multi_requested.emit(aria2_gids)

    def _worker_remove_multi(self, download_ids: list) -> None:
        aria2_gids = [self._get_aria2_gid(d) for d in download_ids]
        aria2_gids = [g for g in aria2_gids if g]
        if aria2_gids:
            self.worker.remove_multi_requested.emit(aria2_gids)

    def _worker_set_speed_limit(self, download_id: str, speed_kb: int) -> None:
        aria2_gid = self._get_aria2_gid(download_id)
        if aria2_gid:
            self.worker.set_speed_limit_requested.emit(aria2_gid, speed_kb)

    def _worker_set_speed_limit_multi(self, download_ids: list, speed_kb: int) -> None:
        aria2_gids = [self._get_aria2_gid(d) for d in download_ids]
        aria2_gids = [g for g in aria2_gids if g]
        if aria2_gids:
            self.worker.set_speed_limit_multi_requested.emit(aria2_gids, speed_kb)

    def _extract_filename(self, url: str) -> str:

        try:
            raw_name = url.split("/")[-1]
            clean_name = raw_name.split("?")[0] if "?" in raw_name else raw_name
            clean_name = clean_name.strip()
        except Exception:
            return "Unknown"

        # Reject dangerous or useless results.
        if not clean_name:
            return "Unknown"
        if clean_name in (".", ".."):
            return "Unknown"
        if "/" in clean_name or "\\" in clean_name:
            return "Unknown"
        # Reject Windows-reserved characters too, just for safety.
        if any(ch in clean_name for ch in '<>:"|*'):
            return "Unknown"

        return clean_name

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

    def _center_dialog_on_screen(self, dialog: QDialog) -> None:
        screen = QApplication.primaryScreen().geometry()
        dialog.move(
            screen.center().x() - dialog.width() // 2,
            screen.center().y() - dialog.height() // 2,
        )

    def _close_splash(self) -> None:
        if hasattr(self, "splash") and self.splash:
            self.splash.close()
            self.splash = None

    def _refresh_table(self) -> None:
        q = self._current_queue()
        if not q:
            self._apply_table_rows([])
            return

        rows = []
        search_text = self.search_box.text().strip().lower()

        for download_id in q.downloads:
            if download_id in self._all_downloads:
                row = self._all_downloads[download_id].copy()

            else:
                info = q.downloads_info.get(download_id, {})
                row = {
                    "id": download_id,
                    "aria2_gid": info.get("aria2_gid"),
                    "gid": download_id,
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
                    "error_count": info.get("error_count", 0),
                    "errorMessage": info.get("errorMessage", ""),
                    "matched_rule": info.get("matched_rule"),
                    "rule_speed_limit": info.get("rule_speed_limit", 0),
                    "connections": info.get("connections", 0),
                }
                self._all_downloads[download_id] = row.copy()

            row["sizeUnknown"] = download_id in self._size_unknown

            display_name = row.get("name", "Unknown")
            matched_rule = row.get("matched_rule")
            if matched_rule:
                display_row = row.copy()
                display_row["name"] = f"{display_name}  [rule: {matched_rule}]"
            else:
                display_row = row

            if search_text and search_text not in display_name.lower():
                continue

            rows.append(display_row)

        self._apply_table_rows(rows)

    def _apply_table_rows(self, rows: List[Dict[str, Any]]) -> None:
        """Push new rows into the table model, preserving the selection.

        The table is refreshed several times a second and any model reset
        clears the view's selection, so the selected downloads are captured
        by id and re-selected afterwards. This keeps the selection stable
        across refreshes, row insertions and re-sorting.
        """
        selection = self.table.selectionModel()
        selected_ids: List[str] = []
        if selection is not None:
            for idx in selection.selectedRows():
                gid = self.model.get_gid(idx.row())
                if gid:
                    selected_ids.append(gid)

        self.model.update_rows(rows)

        if not selected_ids or self.table.selectionModel() is None:
            return

        wanted = set(selected_ids)
        new_selection = QItemSelection()
        for row_idx, row in enumerate(self.model.rows):
            row_id = row.get("id") or row.get("gid")
            if row_id in wanted:
                new_selection.select(
                    self.model.index(row_idx, 0),
                    self.model.index(row_idx, self.model.columnCount() - 1),
                )

        if new_selection.isEmpty():
            return

        # Replace the (now empty) selection without emitting a user-edit
        # signal storm; ScrollHint.EnsureVisible keeps the anchor row visible.
        self.table.selectionModel().select(
            new_selection,
            QItemSelectionModel.SelectionFlag.ClearAndSelect
            | QItemSelectionModel.SelectionFlag.Rows,
        )

    def _refresh_queue_list(self) -> None:
        """Refresh the queue list with proper status indicators"""

        if not self._queue_list_dirty:
            return

        self._queue_list_dirty = False

        self.queue_list.blockSignals(True)
        self.queue_list.clear()

        something_changed = False

        for q in self.store.queues:
            if len(q.downloads) == 0:
                if q.paused != True or q.manually_paused != False:
                    something_changed = True
                q.paused = True
                q.manually_paused = False
                for gid in q.downloads[:]:
                    self._all_downloads.pop(gid, None)
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
                    has_active = any(
                        gid in self._all_downloads
                        and self._all_downloads[gid].get("status", "")
                        in ["active", "waiting", "downloading"]
                        for gid in q.downloads
                    )
                    if has_active:
                        item.setIcon(get_icon("media-playback-start"))
                        item.setForeground(QColor("#27ae60"))
                    else:
                        item.setIcon(get_icon("media-playback-start"))
                        item.setForeground(QColor("#3498db"))

            self.queue_list.addItem(item)

        if self.store.queues:
            self._current_queue_idx = min(
                self._current_queue_idx, len(self.store.queues) - 1
            )
            self.queue_list.setCurrentRow(self._current_queue_idx)

        self.queue_list.blockSignals(False)
        self._update_queue_status()
        self._update_queue_buttons()

        if something_changed:
            self.store.save()

    def _update_queue_buttons(self) -> None:
        q = self._current_queue()
        current_row = self.queue_list.currentRow()
        total_queues = len(self.store.queues)

        self.move_up_btn.setEnabled(current_row > 0)
        self.move_down_btn.setEnabled(0 <= current_row < total_queues - 1)

        if not q or len(q.downloads) == 0 or q.name == "__direct__":
            self.start_queue_btn.setEnabled(False)
            self.pause_queue_btn.setEnabled(False)

            if q and q.name == "__direct__":
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Direct Downloads",
                    "folder-download",
                    "#3498db",
                    size=18,
                )
            else:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Empty",
                    "folder-open",
                    "#95a5a6",
                    size=18,
                )
            return

        has_active = False
        has_waiting = False
        has_paused = False
        has_error = False
        has_getting_size = False

        for gid in q.downloads:
            if gid in self._all_downloads:
                status = self._all_downloads[gid].get("status", "")
                total = self._to_int(self._all_downloads[gid].get("totalLength", 0))

                if total == 0 and status in ["waiting", "paused"]:
                    has_getting_size = True

                if status in ["active", "downloading"]:
                    has_active = True
                elif status == "waiting" and total > 0:
                    has_waiting = True
                elif status == "paused" and total > 0:
                    has_paused = True
                elif status == "error":
                    has_error = True

        has_resumable = has_paused or has_error or has_getting_size

        if q.paused:
            self._set_status_with_icon(
                self.queue_status_lbl,
                self.queue_status_icon,
                "Paused",
                "media-playback-pause",
                "#f39c12",
                size=18,
            )

            if has_active or has_waiting:
                self.start_queue_btn.setEnabled(True)
                self.pause_queue_btn.setEnabled(False)
            elif has_resumable:
                self.start_queue_btn.setEnabled(True)
                self.pause_queue_btn.setEnabled(False)
            else:
                self.start_queue_btn.setEnabled(False)
                self.pause_queue_btn.setEnabled(False)
        else:

            if has_active or has_waiting:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Running",
                    "media-playback-start",
                    "#27ae60",
                    size=18,
                )
                self.start_queue_btn.setEnabled(False)
                self.pause_queue_btn.setEnabled(True)
            elif has_resumable:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Idle",
                    "appointment-soon",
                    "#95a5a6",
                    size=18,
                )
                self.start_queue_btn.setEnabled(True)
                self.pause_queue_btn.setEnabled(False)
            else:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Idle",
                    "appointment-soon",
                    "#95a5a6",
                    size=18,
                )
                self.start_queue_btn.setEnabled(False)
                self.pause_queue_btn.setEnabled(False)

    def _update_queue_status(self) -> None:
        q = self._current_queue()
        if not q:
            self._set_status_with_icon(
                self.queue_status_lbl,
                self.queue_status_icon,
                "No Queue",
                "dialog-question",
                "#95a5a6",
                size=18,
            )
            self.schedule_status_icon.clear()
            self.schedule_status_lbl.setText("")
            self.status_label.setText("Ready")
            return

        if q.name == "__direct__":
            self._set_status_with_icon(
                self.queue_status_lbl,
                self.queue_status_icon,
                "Direct Downloads",
                "folder-download",
                "#3498db",
                size=18,
            )
            self.schedule_status_icon.clear()
            self.schedule_status_lbl.setText("")
            self.status_label.setText("Direct Downloads")
            return

        if len(q.downloads) == 0:
            self._set_status_with_icon(
                self.queue_status_lbl,
                self.queue_status_icon,
                "Empty",
                "folder-open",
                "#95a5a6",
                size=18,
            )
            self.schedule_status_icon.clear()
            self.schedule_status_lbl.setText("Add downloads to start")
            self.status_label.setText("Empty queue")
            return

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
            self._set_status_with_icon(
                self.queue_status_lbl,
                self.queue_status_icon,
                "Complete",
                "emblem-default",
                "#27ae60",
                size=18,
            )
            self.schedule_status_icon.clear()
            self.schedule_status_lbl.setText("")
            self.status_label.setText("All downloads complete")
            return

        if q.schedule_enabled:
            self._update_scheduled_queue_status(q)
        else:
            self._update_regular_queue_status(q)

    def _set_status_with_icon(
        self,
        text_label: QLabel,
        icon_label: QLabel,
        text: str,
        icon_name: str,
        color: str,
        size: int = 16,
    ) -> None:
        """Set a status label's text plus a themed icon next to it.

        Falls back to a colored Unicode bullet if the theme has no
        matching icon, so the layout never collapses.
        """
        text_label.setText(text)
        text_label.setStyleSheet(f"color: {color}; font-weight: bold;")

        icon = get_icon(icon_name)
        if icon is not None and not icon.isNull():
            pm = icon.pixmap(size, size)
            if not pm.isNull():
                icon_label.setPixmap(pm)
                icon_label.setStyleSheet("")
                return

        # Fallback: colored bullet
        icon_label.clear()
        icon_label.setText("●")
        icon_label.setStyleSheet(f"color: {color}; font-size: {size}px;")

    def _update_scheduled_queue_status(self, q: Queue) -> None:
        if q.is_scheduled_now():
            if not q.paused:
                has_active = any(
                    gid in self._all_downloads
                    and self._all_downloads[gid].get("status", "")
                    in ["active", "waiting", "downloading"]
                    for gid in q.downloads
                )
                if has_active:
                    self._set_status_with_icon(
                        self.queue_status_lbl,
                        self.queue_status_icon,
                        "Running",
                        "media-playback-start",
                        "#27ae60",
                        size=18,
                    )
                else:
                    self._set_status_with_icon(
                        self.queue_status_lbl,
                        self.queue_status_icon,
                        "Waiting",
                        "appointment-soon",
                        "#3498db",
                        size=18,
                    )

                self._set_status_with_icon(
                    self.schedule_status_lbl,
                    self.schedule_status_icon,
                    "Schedule active",
                    "alarm-clock",
                    "#27ae60",
                    size=14,
                )
                self.status_label.setText("Scheduled time is active")
            else:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Waiting",
                    "appointment-soon",
                    "#f39c12",
                    size=18,
                )
                next_time = q.get_next_schedule_time()
                if next_time:
                    wait_text = f"Starts at {next_time.strftime('%H:%M')}"
                else:
                    wait_text = "Waiting for schedule"
                self._set_status_with_icon(
                    self.schedule_status_lbl,
                    self.schedule_status_icon,
                    wait_text,
                    "alarm-clock",
                    "#3498db",
                    size=14,
                )
                self.status_label.setText("Waiting for scheduled time")
        else:
            days_text = ", ".join(
                ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][i] for i in q.days
            )
            next_time = q.get_next_schedule_time()
            if next_time:
                next_text = f"Next: {next_time.strftime('%H:%M on %A')}"
            else:
                next_text = (
                    f"Next: {q.schedule_start.strftime('%H:%M')}-"
                    f"{q.schedule_end.strftime('%H:%M')} {days_text}"
                )
            self._set_status_with_icon(
                self.schedule_status_lbl,
                self.schedule_status_icon,
                next_text,
                "appointment-soon",
                "#3498db",
                size=14,
            )

            if q.paused:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Paused (waiting)",
                    "media-playback-pause",
                    "#f39c12",
                    size=18,
                )
                self.status_label.setText(
                    f"Paused - Next: {q.schedule_start.strftime('%H:%M')}"
                )
            else:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Waiting for schedule",
                    "appointment-soon",
                    "#3498db",
                    size=18,
                )
                self.status_label.setText(
                    f"Waiting: {q.schedule_start.strftime('%H:%M')}"
                )

    def _update_regular_queue_status(self, q: Queue) -> None:
        if q.paused:
            has_resumable = any(
                gid in self._all_downloads
                and self._all_downloads[gid].get("status", "") in ["paused", "waiting"]
                for gid in q.downloads
            )
            if has_resumable:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Paused",
                    "media-playback-pause",
                    "#f39c12",
                    size=18,
                )
                self._set_status_with_icon(
                    self.schedule_status_lbl,
                    self.schedule_status_icon,
                    "Click Start to resume",
                    "media-playback-start",
                    "#3498db",
                    size=14,
                )
                self.status_label.setText("Paused")
            else:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Paused",
                    "media-playback-pause",
                    "#95a5a6",
                    size=18,
                )
                self.schedule_status_icon.clear()
                self.schedule_status_lbl.setText("")
                self.status_label.setText("Paused")
        else:
            has_active = any(
                gid in self._all_downloads
                and self._all_downloads[gid].get("status", "")
                in ["active", "waiting", "downloading"]
                for gid in q.downloads
            )
            if has_active:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Running",
                    "media-playback-start",
                    "#27ae60",
                    size=18,
                )
            else:
                self._set_status_with_icon(
                    self.queue_status_lbl,
                    self.queue_status_icon,
                    "Idle",
                    "appointment-soon",
                    "#95a5a6",
                    size=18,
                )
            self.schedule_status_icon.clear()
            self.schedule_status_lbl.setText("")
            self.status_label.setText("Running")

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

        self.btn_move_queue.setEnabled(True)

        # Gather statuses of all selected downloads
        statuses = []
        for idx in selected_indexes:
            gid = self.model.get_gid(idx.row())
            if not gid:
                continue
            status = self._all_downloads.get(gid, {}).get("status", "")
            if status:
                statuses.append(status)

        if not statuses:
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
            return

        total = len(statuses)
        active_count = sum(1 for s in statuses if s in ("active", "downloading"))
        paused_count = sum(1 for s in statuses if s == "paused")
        error_count = sum(1 for s in statuses if s == "error")
        waiting_count = sum(1 for s in statuses if s == "waiting")

        if waiting_count == total:
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Waiting")
            self.btn_toggle.setIcon(get_icon("clock"))
            return

        # Single error → Retry
        if error_count == 1 and total == 1:
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Retry")
            self.btn_toggle.setIcon(get_icon("view-refresh"))
            return

        # All active → Pause
        if active_count == total:
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
            return

        # All paused → Resume
        if paused_count == total:
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Resume")
            self.btn_toggle.setIcon(get_icon("media-playback-start"))
            return

        # Mixed: if any active → Pause (only active ones will be paused)
        if active_count > 0:
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Pause")
            self.btn_toggle.setIcon(get_icon("media-playback-pause"))
            return

        # Mixed: if any paused (no active) → Resume (only paused ones resumed)
        if paused_count > 0:
            self.btn_toggle.setEnabled(True)
            self.btn_toggle.setText("Resume")
            self.btn_toggle.setIcon(get_icon("media-playback-start"))
            return

        # Nothing actionable (all complete/retrying/etc.)
        self.btn_toggle.setEnabled(False)
        self.btn_toggle.setText("Pause")
        self.btn_toggle.setIcon(get_icon("media-playback-pause"))

    def _update_shutdown_button_state(self) -> None:
        q = self._current_queue()

        if not q or q.name == "__direct__" or len(q.downloads) == 0:
            self.shutdown_cb.setEnabled(False)
            if self.shutdown_cb.isChecked():
                self.shutdown_cb.blockSignals(True)
                self.shutdown_cb.setChecked(False)
                self.shutdown_cb.blockSignals(False)
                self.store.settings["shutdown_after_finish"] = False
                self.store.save()
            return

        all_complete = all(
            gid in self._all_downloads
            and self._all_downloads[gid].get("status", "")
            in ["complete", "error", "removed"]
            for gid in q.downloads
        )

        self.shutdown_cb.setEnabled(not all_complete)

    def _update_speed_display(self) -> None:
        total_speed = 0
        has_active = False

        for dl in self._all_downloads.values():
            status = dl.get("status", "")
            if status in ["active", "downloading"]:
                has_active = True
                total_speed += int(dl.get("downloadSpeed", 0))

        self._speed_samples.append(total_speed)
        if len(self._speed_samples) > self._max_samples:
            self._speed_samples.pop(0)

        if self._speed_samples:
            sorted_samples = sorted(self._speed_samples)
            trim = max(1, len(sorted_samples) // 5)
            if len(sorted_samples) > trim * 2:
                samples = sorted_samples[trim:-trim]
            else:
                samples = sorted_samples
            avg_speed = sum(samples) // len(samples)
        else:
            avg_speed = total_speed

        if self._smooth_speed == 0:
            self._smooth_speed = avg_speed
        else:
            self._smooth_speed = int(self._smooth_speed * 0.7 + avg_speed * 0.3)

        speed_text = format_speed(self._smooth_speed)

        if hasattr(self, "speed_status_label"):
            if self.speed_status_label.text() != speed_text:
                self.speed_status_label.setText(speed_text)

        downloading = self._smooth_speed > 0

        if getattr(self, "_last_speed_icon", None) != downloading:
            self._last_speed_icon = downloading
            icon = (
                get_icon("go-down") if downloading else get_icon("media-playback-pause")
            )
            self.speed_icon_label.setPixmap(icon.pixmap(16, 16))

        now = time.monotonic()

        if hasattr(self, "tray") and self.tray.isVisible():
            if has_active and hasattr(self, "tray_icon_active"):
                if self.tray.icon().cacheKey() != self.tray_icon_active.cacheKey():
                    self.tray.setIcon(self.tray_icon_active)
            else:
                if (
                    hasattr(self, "tray_icon_normal")
                    and self.tray.icon().cacheKey() != self.tray_icon_normal.cacheKey()
                ):
                    self.tray.setIcon(self.tray_icon_normal)

            if has_active:
                tooltip = f"FelfelDM - Downloading ({speed_text})"
            else:
                tooltip = "FelfelDM - Ready"

            if now - getattr(
                self, "_last_tooltip_time", 0
            ) >= 1.0 and tooltip != getattr(self, "_last_tooltip", ""):
                self._last_tooltip = tooltip
                self._last_tooltip_time = now
                self.tray.setToolTip(tooltip)

    def _on_queue_changed(self, idx: int) -> None:
        if idx >= 0:
            self._current_queue_idx = idx
            self._update_queue_status()
            self._update_queue_buttons()
            self._update_shutdown_button_state()
            self._refresh_table()
            q = self._current_queue()
            if q and not q.paused:
                self._apply_settings_to_aria2()

    def _on_stats_received(self, result: Dict[str, Any]) -> None:
        if not isinstance(result, dict):
            return

        if not result.get("connected"):
            self.status_lbl.setText("● Disconnected")
            self.status_lbl.setStyleSheet("color: #e74c3c; font-weight: bold;")
            if hasattr(self, "speed_status_label"):
                self.speed_status_label.setText("0 B/s")
            if hasattr(self, "tray") and hasattr(self, "tray_icon_normal"):
                self.tray.setIcon(self.tray_icon_normal)
            return

        self.status_lbl.setText("● Connected")
        self.status_lbl.setStyleSheet("color: #27ae60; font-weight: bold;")

        downloads_list = result.get("downloads", [])

        new_errors = []
        for dl in downloads_list:
            if not isinstance(dl, dict):
                continue
            gid = dl.get("gid")
            if not gid:
                continue
            new_status = dl.get("status", "")

            if new_status == "error":
                download_id = None
                for did, ddata in self._all_downloads.items():
                    if ddata.get("aria2_gid") == gid:
                        download_id = did
                        break
                if download_id:
                    # Skip if this download is already being retried.
                    # Otherwise every poll tick re-detects the same error
                    # and calls _on_download_error again in a loop.
                    if (
                        download_id in self._retry_state
                        or download_id in self._retrying_gids
                    ):
                        continue
                    if self._all_downloads[download_id].get("status") == "retrying":
                        continue

                    old_status = self._all_downloads[download_id].get("status", "")

                    if old_status not in ("error", "stopped", "paused"):
                        new_errors.append((download_id, dl.get("errorMessage", "")))

        self._update_downloads_from_stats(downloads_list)

        for download_id, error_msg in new_errors:
            self._on_download_error(download_id, error_msg)

        youtube_downloads = result.get("youtube_downloads", [])
        self._update_youtube_dialogs(youtube_downloads)

        self._refresh_table()
        self._update_queue_status()

        if self._queue_list_dirty:
            self._refresh_queue_list()

        self._update_queue_buttons()
        self._update_shutdown_button_state()
        self._update_toggle_button()
        self._update_progress_bar()
        q = self._current_queue()
        if q and q.speed_limit > 0 and not q.paused:
            active_count = sum(
                1
                for did in q.downloads
                if self._all_downloads.get(did, {}).get("status", "")
                in ("active", "downloading")
            )
            last = getattr(self, "_last_speed_limit_active_count", None)
            if active_count != last:
                self._last_speed_limit_active_count = active_count
                self._apply_queue_speed_limit(q)

        if (
            self._details_visible
            and hasattr(self, "details_panel")
            and self.details_panel is not None
        ):
            self._update_details_panel()

        for gid, dialog in list(self._progress_dialogs.items()):
            try:
                if dialog.isVisible() and gid in self._all_downloads:
                    dialog.update_data(self._all_downloads[gid])
            except (RuntimeError, AttributeError):
                self._progress_dialogs.pop(gid, None)

        if self.shutdown_cb.isChecked():
            self._check_already_complete()

    def _update_downloads_from_stats(self, downloads_list: List[Dict]) -> None:

        gid_to_download_id: Dict[str, str] = {}
        for download_id, data in self._all_downloads.items():
            aria2_gid = data.get("aria2_gid")
            if aria2_gid:
                gid_to_download_id[aria2_gid] = download_id
        download_to_queue: Dict[str, Queue] = {}
        for q in self.store.queues:
            for download_id in q.downloads:
                download_to_queue[download_id] = q

        saved_data = {}
        for download_id, data in self._all_downloads.items():
            try:
                total = (
                    int(data.get("totalLength", 0)) if data.get("totalLength", 0) else 0
                )
                completed = (
                    int(data.get("completedLength", 0))
                    if data.get("completedLength", 0)
                    else 0
                )
            except (ValueError, TypeError):
                total = 0
                completed = 0
            if total > 0 or completed > 0:
                saved_data[download_id] = {
                    "totalLength": total,
                    "completedLength": completed,
                }

        newly_completed = []

        for dl in downloads_list:
            if not isinstance(dl, dict):
                continue
            gid = dl.get("gid")
            if not gid:
                continue

            download_id = gid_to_download_id.get(gid)

            if download_id and download_id in self._all_downloads:
                pass
            elif gid in self._all_downloads:

                download_id = gid
            else:

                continue

            if download_id in self._all_downloads:
                new_total = 0
                try:
                    new_total = (
                        int(dl.get("totalLength", 0)) if dl.get("totalLength", 0) else 0
                    )
                except (ValueError, TypeError):
                    new_total = 0

                if (
                    new_total == 0
                    and download_id in saved_data
                    and saved_data[download_id]["totalLength"] > 0
                ):

                    if (
                        download_id not in self._retry_state
                        and download_id not in self._retrying_gids
                        and download_id not in self._pending_status
                    ):

                        parent_queue = download_to_queue.get(download_id)
                        if (
                            parent_queue
                            and parent_queue.paused
                            and dl.get("status") in ("waiting", "active")
                        ):

                            if "files" in dl:
                                self._all_downloads[download_id]["files"] = dl["files"]
                        else:
                            for key in ["status", "downloadSpeed"]:
                                if key in dl:
                                    self._all_downloads[download_id][key] = dl[key]
                            if "files" in dl:
                                self._all_downloads[download_id]["files"] = dl["files"]
                    else:
                        if "files" in dl:
                            self._all_downloads[download_id]["files"] = dl["files"]

                    self._all_downloads[download_id]["totalLength"] = saved_data[
                        download_id
                    ]["totalLength"]
                    self._all_downloads[download_id]["completedLength"] = saved_data[
                        download_id
                    ]["completedLength"]
                    continue

                old_status = self._all_downloads[download_id].get("status", "")
                new_status = dl.get("status", "")

                parent_queue = download_to_queue.get(download_id)

                if (
                    parent_queue
                    and parent_queue.paused
                    and new_status in ("waiting", "active")
                    and old_status == "paused"
                ):
                    dl = dict(dl)
                    dl["status"] = "paused"
                    dl["downloadSpeed"] = "0"
                    new_status = "paused"

                if download_id in self._retry_state:
                    dl = dict(dl)
                    dl.pop("status", None)
                    dl.pop("downloadSpeed", None)
                    new_status = old_status
                else:
                    pending = self._pending_status.get(download_id)
                    if pending:
                        expected_status, expires_at = pending
                        if new_status == expected_status or time.time() > expires_at:
                            del self._pending_status[download_id]
                        else:
                            dl = dict(dl)
                            dl.pop("status", None)
                            dl.pop("downloadSpeed", None)
                            new_status = old_status

                if new_status == "stopped":
                    parent_queue = download_to_queue.get(download_id)
                    if parent_queue and parent_queue.paused:
                        dl = dict(dl)
                        dl["status"] = "paused"
                        dl["downloadSpeed"] = "0"
                        new_status = "paused"
                    elif old_status == "paused":
                        dl = dict(dl)
                        dl["status"] = "paused"
                        dl["downloadSpeed"] = "0"
                        new_status = "paused"

                if new_status in ["complete", "completed"] and old_status not in [
                    "complete",
                    "completed",
                ]:
                    if download_id not in self._completed_gids:
                        self._completed_gids.add(download_id)
                        newly_completed.append(download_id)

                self._all_downloads[download_id].update(dl)
            else:

                self._all_downloads[download_id] = dl

        for download_id in newly_completed:
            self._play_completion_sound()

        current_gids = {dl.get("gid") for dl in downloads_list if dl.get("gid")}
        for download_id in list(self._all_downloads.keys()):
            if self._all_downloads[download_id].get("download_type") == "youtube":
                continue
            in_queue = any(download_id in q.downloads for q in self.store.queues)
            aria2_gid = self._all_downloads[download_id].get("aria2_gid")
            if not in_queue and aria2_gid not in current_gids:
                del self._all_downloads[download_id]

        self._maybe_reset_error_counts()

        for q in self.store.queues:
            for download_id in q.downloads:
                if download_id in self._all_downloads:
                    dl = self._all_downloads[download_id]
                    if download_id not in q.downloads_info:
                        q.downloads_info[download_id] = {}

                    q.downloads_info[download_id].update(
                        {
                            "id": download_id,
                            "aria2_gid": dl.get("aria2_gid"),
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
                            "connections": self._to_int(dl.get("connections", 0)),
                        }
                    )

        self.store.mark_dirty()

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
                "Connection error",
                "Connection reset by peer",
            ]
        ):
            return
        self.tray.showMessage(
            "FelfelDM", message, QSystemTrayIcon.MessageIcon.Warning, 3000
        )
        self.status_label.setText(f"⚠ {message}")

    def _on_size_fetched(self, gid: str, size: int, category: str = "📁 Other") -> None:

        if size < 0:
            size = size & 0xFFFFFFFF

        if size <= 0:
            return

        download_id = None
        if gid in self._all_downloads:
            download_id = gid
        else:
            for did, ddata in self._all_downloads.items():
                if ddata.get("aria2_gid") == gid:
                    download_id = did
                    break

        if not download_id:

            print(f"⚠️ [MainWindow] GID {gid[:12]} not found in _all_downloads")
            return

        try:
            current_size = int(self._all_downloads[download_id].get("totalLength", 0))
        except (ValueError, TypeError):
            current_size = 0

        if current_size > 0 and current_size == size:
            return

        self._size_unknown.discard(download_id)
        self._all_downloads[download_id]["totalLength"] = size
        self._all_downloads[download_id]["category"] = category

        for q in self.store.queues:
            if download_id in q.downloads_info:
                q.downloads_info[download_id]["totalLength"] = size
                q.downloads_info[download_id]["category"] = category
                break

        self.store.save()
        self._refresh_table()
        self._update_progress_bar()

    def _on_size_failed(self, gid: str) -> None:
        """A size fetch ended without a size: show "Unknown", stop waiting."""
        download_id = None
        if gid in self._all_downloads:
            download_id = gid
        else:
            for did, ddata in self._all_downloads.items():
                if ddata.get("aria2_gid") == gid:
                    download_id = did
                    break
        if not download_id:
            return
        if self._to_int(self._all_downloads[download_id].get("totalLength", 0)) > 0:
            return
        self._size_unknown.add(download_id)
        self._refresh_table()

    def _on_table_double_click(self, index: QModelIndex) -> None:
        gid = self.model.get_gid(index.row())
        if not gid:
            return

        data = self._all_downloads.get(gid, {})
        download_type = data.get("download_type", "normal")

        # YouTube downloads always open the progress dialog
        if download_type == "youtube":
            self._open_youtube_progress_dialog(gid)
            return

        status = data.get("status", "")

        # Completed → open the file directly (Ctrl+Double-Click forces details)
        if status in ("complete", "completed"):
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier:
                self._open_progress_dialog(gid)
                return
            if self._open_download_file(gid):
                return
            # If the file is missing, fall through to the details dialog
            self._open_progress_dialog(gid)
            return

        # Everything else → progress/details dialog
        self._open_progress_dialog(gid)

    # ═══════════════════════════════════════════════════════════════
    # Drag & Drop
    # ═══════════════════════════════════════════════════════════════

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept drags that carry URLs (links, text, or local files)."""
        urls = self._extract_urls_from_mime(event.mimeData())
        if urls:
            event.acceptProposedAction()
            self._set_drop_highlight(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if self._extract_urls_from_mime(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._set_drop_highlight(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_drop_highlight(False)
        urls = self._extract_urls_from_mime(event.mimeData())
        if not urls:
            event.ignore()
            return
        event.acceptProposedAction()
        self._handle_dropped_urls(urls)

    def _extract_urls_from_mime(self, mime: QMimeData) -> list:
        """Extract download URLs from a drag-and-drop payload.

        Handles both text/uri-list (Firefox/Chrome link drags, file:// drops)
        and text/plain (some browsers only provide this). Returns an ordered,
        de-duplicated list of URLs.
        """
        urls = []

        if mime.hasUrls():
            for url in mime.urls():
                s = url.toString().strip()
                if not s:
                    continue
                if s.startswith("file://"):
                    # Local file drop — keep the local path so the user can
                    # see what they dropped, but only if it's a .txt we can
                    # parse. Otherwise, skip it.
                    local = url.toLocalFile()
                    if local and local.lower().endswith(".txt"):
                        try:
                            with open(local, "r", encoding="utf-8") as f:
                                for line in f:
                                    line = line.strip()
                                    if line and line.lower().startswith(
                                        (
                                            "http://",
                                            "https://",
                                            "ftp://",
                                            "ftps://",
                                            "magnet:",
                                        )
                                    ):
                                        urls.append(line)
                        except Exception as e:
                            print(f"⚠️ [Drop] Could not read {local}: {e}")
                    continue
                urls.append(s)

        if not urls and mime.hasText():
            text = mime.text().strip()
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.lower().startswith(
                    ("http://", "https://", "ftp://", "ftps://", "magnet:")
                ):
                    urls.append(line)

        # De-dup while preserving order
        seen = set()
        result = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                result.append(u)
        return result

    def _handle_dropped_urls(self, urls: list) -> None:
        """Open the Add Download dialog pre-filled with dropped URLs.

        Works the same way as the extension handler: if the dialog is
        already open, the URLs are appended to it.
        """
        if not urls:
            return

        self._open_or_update_add_dialog(urls)
        self.status_label.setText(f"📥 {len(urls)} URL(s) dropped")

    def _open_or_update_add_dialog(self, urls: List[str] = None) -> None:
        key = "add_download"
        existing = self._open_dialogs.get(key)

        if existing is not None:
            try:
                if existing.isVisible():
                    if urls:
                        current = existing.url_edit.toPlainText().strip()
                        existing_set = set(
                            line.strip() for line in current.split("\n") if line.strip()
                        )
                        fresh = [u for u in urls if u not in existing_set]
                        if fresh:
                            combined = (
                                f"{current}\n" + "\n".join(fresh)
                                if current
                                else "\n".join(fresh)
                            )
                            existing.url_edit.setPlainText(combined)

                    # Defer the raise until after the layout pass triggered
                    # by setPlainText → textChanged → resize has finished.
                    QTimer.singleShot(0, lambda w=existing: self._force_raise_dialog(w))
                    return
            except RuntimeError:
                self._open_dialogs.pop(key, None)

        all_queues = self.store.queues
        dlg = AddDownloadDialog(all_queues, 0, self)

        if urls:
            dlg.url_edit.setPlainText("\n".join(urls))
        else:
            clip = QApplication.clipboard().text().strip()
            if clip:
                valid_lines = [
                    line.strip()
                    for line in clip.split("\n")
                    if line.strip().startswith(("http", "magnet:", "ftp"))
                ]
                if valid_lines:
                    dlg.url_edit.setPlainText("\n".join(valid_lines))

        self._show_singleton_dialog(
            key, dlg, on_accepted=self._process_add_download_common
        )

    def _force_raise_dialog(self, dlg) -> None:
        """Bring a dialog to the front, even if minimized or unfocused.

        On KDE/Wayland, raise_()/activateWindow() alone don't reliably
        bring a dialog to the front when another window has focus. Adding
        WindowStaysOnTopHint temporarily forces the WM to surface it, then
        we restore the original flags.
        """
        try:
            # Remember the original flags
            original_flags = dlg.windowFlags()

            # Force the dialog on top of everything (works around
            # focus-stealing-prevention on KDE/Wayland)
            dlg.setWindowFlags(original_flags | Qt.WindowType.WindowStaysOnTopHint)
            dlg.show()
            dlg.raise_()
            dlg.activateWindow()

            # Restore the original flags after a short delay so the dialog
            # doesn't stay pinned above every other window forever.
            def _restore():
                try:
                    dlg.setWindowFlags(original_flags)
                    dlg.show()
                    dlg.raise_()
                    dlg.activateWindow()
                except RuntimeError:
                    pass

            QTimer.singleShot(300, _restore)
        except RuntimeError:
            pass

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._drop_overlay is not None and self._drop_overlay.isVisible():
            self._drop_overlay.setGeometry(self.table.viewport().rect())

    def _set_drop_highlight(self, on: bool) -> None:
        """Show/hide a subtle overlay over the downloads table only."""
        if on:
            if self._drop_overlay is None:
                # Parent is the table's viewport, so the overlay stays
                # exactly over the rows area (not on toolbar/sidebar/menu).
                self._drop_overlay = DropOverlay(self.table.viewport())
            self._drop_overlay.setGeometry(self.table.viewport().rect())
            self._drop_overlay.show()
            self._drop_overlay.raise_()
            self._drop_overlay.update()
        else:
            if self._drop_overlay is not None:
                self._drop_overlay.hide()

    def _open_download_file(self, download_id: str) -> bool:
        """Try to open the downloaded file with the default application.

        Returns True if the file was opened, False otherwise (caller should
        fall back to the details dialog).
        """
        data = self._all_downloads.get(download_id)
        if not data:
            return False

        file_path: Optional[str] = None

        # Prefer the stored file path(s)
        for f in data.get("files", []) or []:
            p = f.get("path")
            if p:
                file_path = p
                break

        # Fallback: derive from save_path + name
        if not file_path:
            save_path = data.get("save_path") or data.get("real_path")
            name = data.get("name")
            if save_path and name:
                candidate = os.path.join(save_path, name)
                if os.path.exists(candidate):
                    file_path = candidate

        if not file_path:
            return False

        # If it's a directory, open the folder instead
        if os.path.isdir(file_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
            return True

        if not os.path.exists(file_path):
            # File was moved/deleted by the user — show a warning but don't crash
            QMessageBox.warning(
                self,
                "File Not Found",
                f"The downloaded file no longer exists at:\n\n{file_path}",
            )
            return False

        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
        if not opened:
            QMessageBox.warning(
                self,
                "Cannot Open File",
                f"Could not open the file with the default application:\n\n{file_path}",
            )
            return False

        return True

    def _filter_downloads(self, text: str) -> None:
        q = self._current_queue()
        if not q:
            self._apply_table_rows([])
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

        self._apply_table_rows(filtered)

    def _show_singleton_dialog(self, key: str, dlg: QDialog, on_accepted=None) -> None:
        existing = self._open_dialogs.get(key)
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.raise_()
                    existing.activateWindow()
                    return
            except RuntimeError:
                pass
            self._open_dialogs.pop(key, None)

        self._open_dialogs[key] = dlg
        dlg.setWindowModality(Qt.WindowModality.NonModal)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        dlg.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )

        def _cleanup():
            if self._open_dialogs.get(key) is dlg:
                self._open_dialogs.pop(key, None)

        def _handle_accepted():
            try:
                if on_accepted:
                    on_accepted(dlg)
            finally:
                _cleanup()

        dlg.accepted.connect(_handle_accepted)
        dlg.rejected.connect(_cleanup)

        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _rules_with_size_conditions(self) -> bool:
        """True when at least one enabled rule constrains file size.

        Only then is it worth paying for an extra HEAD request when adding
        a download.
        """
        try:
            for rule in self.store.rule_engine.rules:
                if rule.enabled and (rule.size_min > 0 or rule.size_max > 0):
                    return True
        except Exception:
            pass
        return False

    def _probe_size_for_rules(self, url: str, proxy_dict=None) -> Optional[int]:
        """Best-effort file size lookup used only to evaluate size rules.

        Fully optional: a bounded HEAD request, and any failure means the
        size conditions are simply not evaluated for this URL.
        """
        try:
            from core.file_size_fetcher import FileSizeFetcher

            fetcher = FileSizeFetcher(timeout=5, proxy=proxy_dict)
            try:
                size = fetcher.get_size(url)
            finally:
                fetcher.close()
            if size and size > 0:
                return int(size)
        except Exception as e:
            print(f"⚠️ [Rules] Size probe failed for {url[:60]}: {e}")
        return None

    def _process_add_download_common(self, dlg: "AddDownloadDialog") -> None:
        """Unified handler for both Quick Download and Add to Queue."""
        d = dlg.get_data()
        if not d["urls"]:
            return

        queue_name = d.get("queue_name", "__direct__")
        target_queue = self._get_or_create_queue(queue_name)

        self._apply_settings_to_aria2()

        # ── Base options for this batch ──
        # User's connection count from the dialog (which now defaults
        # to settings["connections"]).
        user_connections = int(d.get("connections") or 8)

        options = {
            "dir": d["path"],
            "split": str(user_connections),
            "max-connection-per-server": str(user_connections),
            "min-split-size": "1M",
            "stream-piece-selector": "geom",
            "continue": "true",
            "always-resume": "true",
            "header": [
                "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"
            ],
        }

        proxy_mode = d.get("proxy_mode", 0)
        if proxy_mode == 0:
            proxy = self.proxy_manager.get_proxy_for_queue(queue_name)
            if proxy and proxy.is_valid():
                options["all-proxy"] = proxy._build_proxy_url()
        elif proxy_mode == 1:
            custom_proxy = d.get("custom_proxy")
            if custom_proxy and custom_proxy.is_valid():
                options["all-proxy"] = custom_proxy._build_proxy_url()
        elif proxy_mode == 2:
            options["all-proxy"] = ""

        is_direct = queue_name == "__direct__"
        added = 0
        new_gids = []

        print(f"📂 [Add] Queue: {queue_name}")
        print(f"📂 [Add] Save path: {d['path']!r}")
        print(f"📂 [Add] URLs: {len(d['urls'])}")

        # Snapshot of every URL currently tracked, so we can reject
        # duplicates before aria2 does (aria2 returns result:null for
        # duplicate URIs, which we used to misread as a failure).
        existing_urls: Dict[str, str] = {}
        for q in self.store.queues:
            for dl_id, dl_info in q.downloads_info.items():
                u = dl_info.get("url")
                if u:
                    existing_urls[u] = q.name

        # Size-conditional rules can only be evaluated with a known file
        # size, so only probe when such a rule exists at all.
        rules_need_size = self._rules_with_size_conditions()

        for url in d["urls"]:

            # ── Duplicate check (C5 follow-up) ──
            if url in existing_urls:
                print(
                    f"⏭️ [Add] Skipping duplicate URL — already in "
                    f"queue '{existing_urls[url]}': {url!r}"
                )
                continue

            # Size-based rules need the file size, which is unknown until the
            # server is asked. Probing costs a request, so it only happens
            # when a rule actually constrains size; otherwise this is a
            # plain URL match as before.
            rule_size = None
            if rules_need_size:
                rule_size = self._probe_size_for_rules(
                    url,
                    options.get("all-proxy")
                    and {
                        "http": options["all-proxy"],
                        "https": options["all-proxy"],
                    },
                )

            rule = self.store.rule_engine.find_match(url, rule_size)

            url_options = options.copy()
            url_queue = target_queue
            url_path = d["path"]
            url_connections = user_connections
            url_speed_limit = getattr(target_queue, "speed_limit", 0)

            is_schedule_active = (
                url_queue.schedule_enabled and url_queue.is_scheduled_now()
            )

            if rule:
                if rule.queue:
                    for q in self.store.queues:
                        if q.name == rule.queue:
                            url_queue = q
                            break
                    else:
                        url_queue = self._get_or_create_queue(rule.queue)

                if rule.folder:
                    url_path = expand_path(rule.folder)

                if rule.connections:
                    url_connections = rule.connections
                    url_options["split"] = str(rule.connections)
                    url_options["max-connection-per-server"] = str(rule.connections)

                if rule.speed_limit:
                    url_speed_limit = rule.speed_limit

                url_options["dir"] = url_path

                print(
                    f"🎯 [Rules] '{rule.name}' matched for {url[:50]}... "
                    f"→ queue='{url_queue.name}', folder='{url_path}', "
                    f"conn={url_connections}, speed={url_speed_limit}"
                )

            url_is_direct = url_queue.name == "__direct__"
            if not url_is_direct and url_queue.paused and not is_schedule_active:
                url_options["pause"] = "true"

            # ── Submit to aria2 ──
            gid = self.aria2.add_url(url, url_options)
            if not gid:
                print(f"❌ [Add] aria2.add_url returned None for URL: {url!r}")
                continue

            # Register the URL so later URLs in this same batch are
            # also deduplicated against it.
            existing_urls[url] = url_queue.name

            download_id = uuid.uuid4().hex[:16]

            url_queue.downloads.append(download_id)

            clean_name = self._extract_filename(url)
            full_path = os.path.join(url_path, clean_name)

            if url_is_direct or not url_queue.paused or is_schedule_active:
                initial_status = "active"
                if is_schedule_active and url_queue.paused:
                    url_queue.paused = False
                    url_queue.manually_paused = False
            else:
                initial_status = "paused"

            # Common per-download fields, shared by the persistent
            # downloads_info and the runtime _all_downloads dict.
            common_fields = {
                "id": download_id,
                "aria2_gid": gid,
                "url": url,
                "name": clean_name,
                "totalLength": 0,
                "completedLength": 0,
                "status": initial_status,
                "files": [{"path": full_path}],
                "category": "📁 Other",
                "download_type": "normal",
                "save_path": url_path,
                "matched_rule": rule.name if rule else None,
                "rule_speed_limit": (
                    rule.speed_limit if rule and rule.speed_limit else 0
                ),
                "speed_limit": 0,
                "proxy_url": url_options.get("all-proxy", ""),
                # C5 fix: persist every option a re-add would need.
                "connections": url_connections,
                "min_split_size": url_options.get("min-split-size", "1M"),
                "stream_piece_selector": url_options.get(
                    "stream-piece-selector", "geom"
                ),
                "header": url_options.get("header", []),
            }

            url_queue.downloads_info[download_id] = dict(common_fields)

            runtime_fields = dict(common_fields)
            runtime_fields.update(
                {
                    "downloadSpeed": 0,
                    "connections": 0,
                    "errorMessage": "",
                    "size_fetch_attempts": 0,
                }
            )
            self._all_downloads[download_id] = runtime_fields

            if is_schedule_active:
                try:
                    status = self.aria2.get_status(gid)
                    if status and status.get("status") in ("paused", "waiting"):
                        self.worker.resume_requested.emit(gid)
                        self._all_downloads[download_id]["status"] = "active"
                        if download_id in url_queue.downloads_info:
                            url_queue.downloads_info[download_id]["status"] = "active"
                except Exception as e:
                    print(f"⚠️ Could not resume {download_id}: {e}")

            # Per-download speed limit (overrides queue + global)
            per_download_speed = self._to_int(d.get("per_download_speed", 0))
            if per_download_speed > 0:
                self._all_downloads[download_id]["speed_limit"] = per_download_speed
                url_queue.downloads_info[download_id][
                    "speed_limit"
                ] = per_download_speed
                self._worker_set_speed_limit(download_id, per_download_speed)
            else:
                # Fall back to queue speed limit
                final_speed = url_speed_limit or getattr(url_queue, "speed_limit", 0)
                if final_speed > 0:
                    self._worker_set_speed_limit(download_id, final_speed)

            new_gids.append(download_id)
            added += 1

        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._refresh_table()
        self._update_queue_buttons()
        self._update_shutdown_button_state()

        if is_direct:
            for download_id in new_gids:
                try:
                    dl = self._all_downloads.get(download_id, {})
                    aria2_gid = dl.get("aria2_gid")
                    if not aria2_gid:
                        continue

                    status = self.aria2.get_status(aria2_gid)
                    if status and status.get("status") in ("waiting", "paused"):
                        self.worker.resume_requested.emit(aria2_gid)
                        self._all_downloads[download_id]["status"] = "active"
                        if download_id in target_queue.downloads_info:
                            target_queue.downloads_info[download_id][
                                "status"
                            ] = "active"
                except Exception as e:
                    print(f"⚠️ Could not resume {download_id}: {e}")
            self.store.save()

            for download_id in new_gids:
                QTimer.singleShot(
                    300,
                    lambda did=download_id: self._open_progress_dialog(did),
                )

        if is_direct:
            msg = f"✅ Added {added} download(s) to Direct Downloads (started)"
        elif target_queue.paused:
            msg = f"✅ Added {added} download(s) to '{target_queue.name}' (paused)"
        else:
            msg = f"✅ Added {added} download(s) to '{target_queue.name}' (downloading)"

        self.tray.showMessage(
            "FelfelDM", msg, QSystemTrayIcon.MessageIcon.Information, 2000
        )

        self._refresh_table()

    def _build_details_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("details_panel")
        panel.setMinimumHeight(100)
        panel.setMaximumHeight(190)
        panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QHBoxLayout(panel)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(16)

        # ── Empty-state label (shown when nothing is selected) ───────────
        self.empty_label = QLabel("Select a download to view details")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setObjectName("details_empty")
        self.empty_label.setVisible(True)
        lay.addWidget(self.empty_label)

        # ── Details container ───────────────────────────────────────────
        self.details_container = QWidget()
        self.details_container.setVisible(False)
        details_lay = QHBoxLayout(self.details_container)
        details_lay.setContentsMargins(0, 0, 0, 0)
        details_lay.setSpacing(16)

        # ─────────────────────────────────────────────────────────────
        # Left column: download info (card) — takes most of the width
        # ─────────────────────────────────────────────────────────────
        self.info_card = QFrame()
        self.info_card.setObjectName("details_card")
        self.info_card.setFrameShape(QFrame.Shape.NoFrame)

        card_lay = QVBoxLayout(self.info_card)
        card_lay.setContentsMargins(16, 12, 16, 12)
        card_lay.setSpacing(8)

        info_grid = QGridLayout()
        info_grid.setSpacing(8)
        info_grid.setHorizontalSpacing(14)
        info_grid.setContentsMargins(0, 0, 0, 0)
        info_grid.setColumnStretch(0, 0)  # icon
        info_grid.setColumnStretch(1, 0)  # label
        info_grid.setColumnStretch(2, 1)  # value

        # Icon name candidates: first themed icon that resolves wins.
        rows = [
            ("File", "name", ["text-x-generic", "document-new"]),
            ("Size", "size", ["drive-harddisk", "drive-harddisk-symbolic"]),
            ("Downloaded", "downloaded", ["download", "go-bottom", "arrow-down"]),
            ("Status", "status", ["dialog-information", "emblem-info"]),
            ("Path", "path", ["folder", "folder-open"]),
            ("Reason", "reason", ["dialog-warning", "emblem-warning"]),
        ]

        self.detail_labels = {}
        self.detail_icon_labels = {}

        for row_idx, (label_text, key, icon_candidates) in enumerate(rows):
            # -- icon --
            icon_label = QLabel()
            icon_label.setFixedSize(20, 20)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icon = self._resolve_theme_icon(icon_candidates)
            if icon is not None:
                icon_label.setPixmap(icon.pixmap(18, 18))
            else:
                icon_label.setText("•")
                icon_label.setStyleSheet("color: palette(mid); font-size: 18px;")
            info_grid.addWidget(
                icon_label, row_idx, 0, alignment=Qt.AlignmentFlag.AlignVCenter
            )
            self.detail_icon_labels[key] = icon_label

            # -- label (bolder, slightly larger) --
            lbl = QLabel(f"{label_text}:")
            lbl.setProperty("role", "muted")
            lbl.setMinimumWidth(96)
            info_grid.addWidget(
                lbl, row_idx, 1, alignment=Qt.AlignmentFlag.AlignVCenter
            )

            # -- value (larger, selectable) --
            val = QLabel("—")
            val.setObjectName(f"detail_{key}")
            val.setProperty("role", "value")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            val.setWordWrap(False)
            info_grid.addWidget(
                val, row_idx, 2, alignment=Qt.AlignmentFlag.AlignVCenter
            )
            self.detail_labels[key] = val

        card_lay.addLayout(info_grid)
        card_lay.addStretch()

        # Give the info card much more room than the action column.
        details_lay.addWidget(self.info_card, stretch=5)

        # ─────────────────────────────────────────────────────────────
        # Right column: compact action buttons (single column, small)
        # ─────────────────────────────────────────────────────────────
        action_widget = QWidget()
        action_lay = QVBoxLayout(action_widget)
        action_lay.setSpacing(6)
        action_lay.setContentsMargins(0, 0, 0, 0)

        def _mk_action(icon_name, text, slot):
            btn = QPushButton(get_icon(icon_name), text)
            btn.clicked.connect(slot)
            btn.setMinimumHeight(30)
            btn.setMaximumHeight(30)
            btn.setMinimumWidth(120)
            btn.setMaximumWidth(120)
            btn.setIconSize(QSize(14, 14))
            btn.setEnabled(False)
            btn.setProperty("compact", "true")
            return btn

        self.detail_pause_btn = _mk_action(
            "media-playback-pause", "Pause", self._toggle_pause_resume
        )
        action_lay.addWidget(self.detail_pause_btn)

        self.detail_cancel_btn = _mk_action(
            "edit-delete", "Cancel", self._remove_selected
        )
        self.detail_cancel_btn.setProperty("variant", "danger")
        action_lay.addWidget(self.detail_cancel_btn)

        self.detail_open_btn = _mk_action(
            "folder",
            "Open Folder",
            lambda: self._open_folder(self._selected_gid()),
        )
        action_lay.addWidget(self.detail_open_btn)

        self.detail_copy_btn = _mk_action(
            "edit-copy",
            "Copy URL",
            lambda: self._copy_link(self._selected_gid()),
        )
        action_lay.addWidget(self.detail_copy_btn)

        action_lay.addStretch()

        # Give the action column just enough room — no more.
        details_lay.addWidget(action_widget, stretch=0)

        lay.addWidget(self.details_container)
        return panel

    def _resolve_theme_icon(self, candidates: list):
        """Return the first QIcon from `candidates` that resolves in the
        current theme, or None if none of them exist. Used to avoid relying
        on a single icon name that may be missing in some icon themes."""
        for name in candidates:
            icon = get_icon(name)
            if icon is not None and not icon.isNull():
                return icon
        return None

    def _refresh_empty_state(self, *args) -> None:
        """Show a hint over the table while it has no rows."""
        label = getattr(self, "empty_state", None)
        if label is None:
            return
        if self.model.rowCount() > 0:
            label.setVisible(False)
            return
        query = self.search_box.text().strip() if hasattr(self, "search_box") else ""
        if query:
            label.setText(f"No downloads match “{query}”")
        else:
            label.setText(
                "No downloads here yet\n\n"
                "Press Ctrl+N to add one, or drop a link onto this window"
            )
        label.setVisible(True)

    def _toggle_details_panel(self, checked: bool = False) -> None:
        """Toggle details panel visibility"""
        if not hasattr(self, "details_panel") or self.details_panel is None:
            return

        self._details_visible = not self._details_visible
        self.details_panel.setVisible(self._details_visible)

        if hasattr(self, "btn_show_details"):

            self.btn_show_details.blockSignals(True)
            self.btn_show_details.setChecked(self._details_visible)
            self.btn_show_details.blockSignals(False)

        if self._details_visible:
            self._update_details_panel()

    def _show_details_empty(self, message: str) -> None:
        """Show the empty label with a custom message and hide the details container."""
        if hasattr(self, "empty_label"):
            self.empty_label.setText(message)
            self.empty_label.setVisible(True)
        if hasattr(self, "details_container"):
            self.details_container.setVisible(False)

    def _update_details_panel(self) -> None:
        """Update details panel with selected download info."""
        if not self.table.selectionModel():
            self._show_details_empty("Select a download to view details")
            return

        rows = self.table.selectionModel().selectedRows()

        if len(rows) == 0:
            self._show_details_empty("Select a download to view details")
            return

        if len(rows) > 1:
            self._show_details_empty(
                f"{len(rows)} downloads selected — select a single one for details"
            )
            return

        gid = self.model.get_gid(rows[0].row())
        if not gid or gid not in self._all_downloads:
            self._show_details_empty("Select a download to view details")
            return

        if hasattr(self, "empty_label"):
            self.empty_label.setVisible(False)
        if hasattr(self, "details_container"):
            self.details_container.setVisible(True)

        data = self._all_downloads[gid]

        if hasattr(self, "detail_labels"):

            self.detail_labels["name"].setText(data.get("name", "Unknown"))

            try:
                total = int(data.get("totalLength", 0))
            except (ValueError, TypeError):
                total = 0
            self.detail_labels["size"].setText(format_size(total))

            try:
                downloaded = int(data.get("completedLength", 0))
            except (ValueError, TypeError):
                downloaded = 0
            self.detail_labels["downloaded"].setText(format_size(downloaded))

            status = data.get("status", "unknown")
            status_texts = {
                "active": "Downloading",
                "downloading": "Downloading",
                "waiting": "Waiting",
                "paused": "Paused",
                "complete": "Complete",
                "completed": "Complete",
                "error": "Error",
                "removed": "Removed",
            }
            status_display = status_texts.get(status, status.title())
            self.detail_labels["status"].setText(status_display)

            status_colors = {
                "active": "#27ae60",
                "downloading": "#27ae60",
                "waiting": "#f39c12",
                "paused": "#f39c12",
                "complete": "#3498db",
                "completed": "#3498db",
                "error": "#e74c3c",
            }
            color = status_colors.get(status, "#888")
            self.detail_labels["status"].setStyleSheet(
                f"font-size: 12px; color: {color};"
            )

            from utils.helpers import get_error_reason

            if status in ("error", "retrying"):
                reason_text = get_error_reason(data.get("errorMessage", ""))
            else:
                reason_text = "—"

            self.detail_labels["reason"].setText(reason_text)
            if status == "error":
                self.detail_labels["reason"].setStyleSheet(
                    "font-size: 12px; color: #e74c3c;"
                )
            elif status == "retrying":
                self.detail_labels["reason"].setStyleSheet(
                    "font-size: 12px; color: #f39c12;"
                )
            else:
                self.detail_labels["reason"].setStyleSheet("font-size: 12px;")

            files = data.get("files", [])
            if files and files[0].get("path"):
                path = os.path.dirname(files[0]["path"])
                self.detail_labels["path"].setText(path)
            else:
                self.detail_labels["path"].setText("—")

        if hasattr(self, "detail_pause_btn"):
            real_status = data.get("status", "")
            download_type = data.get("download_type", "normal")

            if real_status in ["active", "waiting", "downloading"]:
                self.detail_pause_btn.setEnabled(True)
                self.detail_pause_btn.setText("Pause")
                self.detail_pause_btn.setIcon(get_icon("media-playback-pause"))
            elif real_status == "paused":
                self.detail_pause_btn.setEnabled(True)
                self.detail_pause_btn.setText("Resume")
                self.detail_pause_btn.setIcon(get_icon("media-playback-start"))
            elif real_status == "error":
                # Errored downloads can be retried (which re-adds them
                # with a fresh gid), even if they're marked permanent.
                self.detail_pause_btn.setEnabled(True)
                self.detail_pause_btn.setText("Retry")
                self.detail_pause_btn.setIcon(get_icon("view-refresh"))
            elif real_status == "retrying":
                self.detail_pause_btn.setEnabled(False)
                self.detail_pause_btn.setText("Retrying...")
                self.detail_pause_btn.setIcon(get_icon("view-refresh"))
            elif real_status in ("complete", "completed"):
                self.detail_pause_btn.setEnabled(False)
                self.detail_pause_btn.setText("Completed")
                self.detail_pause_btn.setIcon(get_icon("emblem-default"))
            else:
                self.detail_pause_btn.setEnabled(False)
                self.detail_pause_btn.setText("Pause")
                self.detail_pause_btn.setIcon(get_icon("media-playback-pause"))

        if hasattr(self, "detail_cancel_btn"):
            real_status = data.get("status", "")
            # Cancel is available for anything that isn't already
            # complete/retrying — a retrying download is already being
            # handled by the retry logic.
            if real_status in [
                "active",
                "waiting",
                "downloading",
                "paused",
                "error",
            ]:
                self.detail_cancel_btn.setEnabled(True)
            else:
                self.detail_cancel_btn.setEnabled(False)

        if hasattr(self, "detail_open_btn"):
            # Only enable "Open Folder" if the download started (some
            # bytes downloaded or file exists on disk).
            completed = self._to_int(data.get("completedLength", 0))
            self.detail_open_btn.setEnabled(completed > 0)
        if hasattr(self, "detail_copy_btn"):
            self.detail_copy_btn.setEnabled(True)

    def _setup_shortcuts(self) -> None:
        """Set up keyboard shortcuts.

        Table-local keys (Space/Delete) are scoped to the widget so they
        don't fire while the user is typing in the search box or
        interacting with the details panel.
        """
        table_context = Qt.ShortcutContext.WidgetWithChildrenShortcut

        for key, slot in (
            ("Space", self._toggle_pause_resume),
            ("Delete", self._remove_selected),
            ("Shift+Delete", self._remove_with_files),
        ):
            shortcut = QShortcut(QKeySequence(key), self.table, slot)
            shortcut.setContext(table_context)

        QShortcut(QKeySequence("Ctrl+P"), self, self._pause_selected)
        QShortcut(QKeySequence("Ctrl+R"), self, self._resume_selected)

        QShortcut(QKeySequence("Ctrl+D"), self, self._toggle_details_panel)
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence("Escape"), self, self._clear_search)

        QShortcut(QKeySequence("Ctrl+Tab"), self, self._next_queue)
        QShortcut(QKeySequence("Ctrl+Shift+Tab"), self, self._prev_queue)

        QShortcut(QKeySequence("F5"), self, self._refresh_table)
        QShortcut(QKeySequence("F1"), self, self._show_shortcuts)

    def _show_shortcuts(self) -> None:
        """Show keyboard shortcuts dialog"""
        shortcuts = [
            ("Ctrl+N", "Add Download"),
            ("Space", "Pause/Resume selected"),
            ("Ctrl+P", "Pause selected"),
            ("Ctrl+R", "Resume selected"),
            ("Delete", "Remove selected"),
            ("Shift+Delete", "Remove and delete files"),
            ("Ctrl+D", "Toggle details panel"),
            ("Ctrl+F", "Focus search"),
            ("Escape", "Clear search"),
            ("Ctrl+Tab", "Next queue"),
            ("Ctrl+Shift+Tab", "Previous queue"),
            ("Ctrl+,", "Settings"),
            ("F5", "Refresh"),
            ("F1", "Show shortcuts"),
            ("Ctrl+E", "Export Downloads"),
            ("Ctrl+L", "Show logs"),
        ]

        msg = "<h3>Keyboard Shortcuts</h3><br>"
        for key, action in shortcuts:
            msg += f"<b>{key}</b> — {action}<br>"

        QMessageBox.information(self, "Shortcuts", msg)

    def _focus_search(self) -> None:
        """Focus the search box"""
        if hasattr(self, "search_box"):
            self.search_box.setFocus()
            self.search_box.selectAll()

    def _clear_search(self) -> None:
        """Clear search box and restore focus to table"""
        if hasattr(self, "search_box"):
            self.search_box.clear()
            self.table.setFocus()

    def _next_queue(self) -> None:
        """Switch to next queue"""
        if self.queue_list.count() > 0:
            current = self.queue_list.currentRow()
            next_idx = (current + 1) % self.queue_list.count()
            self.queue_list.setCurrentRow(next_idx)

    def _prev_queue(self) -> None:
        """Switch to previous queue"""
        if self.queue_list.count() > 0:
            current = self.queue_list.currentRow()
            prev_idx = (current - 1) % self.queue_list.count()
            self.queue_list.setCurrentRow(prev_idx)

    def _remove_with_files(self) -> None:

        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return

        gids_to_remove = [
            self.model.get_gid(idx.row())
            for idx in selected
            if self.model.get_gid(idx.row())
        ]
        if not gids_to_remove:
            return

        # ── STEP 1: Stop aria2 first, but ONLY after the user confirms ──
        # We still need to confirm before doing anything destructive.
        # So we collect the file list first, show the dialog, and only
        # then stop aria2.
        entries = self._collect_files_for_gids(gids_to_remove)
        if entries:
            from ui.dialogs import DeleteFilesConfirmationDialog

            dlg = DeleteFilesConfirmationDialog(entries, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                print("🗑️ [Delete] Cancelled by user")
                return
        else:
            print("🗑️ [Delete] No files to delete")

        # ── STEP 2: Force-remove each gid from aria2 first ──
        for gid in gids_to_remove:
            try:
                aria2_gid = self._get_aria2_gid(gid) or gid
                self.aria2.force_remove(aria2_gid)
                print(f"🗑️ [Delete] force_remove sent for {aria2_gid[:12]}")
            except Exception as e:
                print(f"⚠️ [Delete] force_remove failed for {gid}: {e}")
            try:
                self.aria2._call("aria2.removeDownloadResult", [gid])
            except Exception:
                pass

        # ── STEP 3: Give aria2 a moment to release the file handles ──
        # We poll until the gids are no longer reported by aria2, with
        # a hard cap so the UI can't hang.
        import time as _time

        deadline = _time.time() + 2.0
        remaining = set()
        while _time.time() < deadline:
            remaining = set()
            for gid in gids_to_remove:
                try:
                    status = self.aria2.get_status(gid)
                    if status and status.get("status") not in (None, "removed"):
                        remaining.add(gid)
                except Exception:
                    pass
            if not remaining:
                break
            _time.sleep(0.1)

        if remaining:
            print(
                f"⚠️ [Delete] {len(remaining)} download(s) still active in "
                f"aria2 after 2s; proceeding to delete files anyway"
            )

        # ── STEP 4: Now delete the files ──
        # Re-collect paths (aria2 may have just released the files) and
        # delete them with the same safe checks as before.
        if entries:
            paths = [e["path"] for e in entries]
            deleted = 0
            for path in paths:
                try:
                    if not os.path.exists(path):
                        continue
                    if os.path.isdir(path):
                        print(f"⚠️ [Delete] Refusing to delete directory: {path}")
                        continue
                    if not os.path.isfile(path):
                        continue
                    os.remove(path)
                    deleted += 1
                    print(f"🗑️ DELETED: {os.path.basename(path)}")
                except PermissionError as e:
                    print(f"⚠️ Permission denied: {path}: {e}")
                except OSError as e:
                    print(f"⚠️ Delete failed {path}: {e}")
                except Exception as e:
                    print(f"⚠️ Unexpected error deleting {path}: {e}")
            print(f"✅ Deleted {deleted} file(s)")

        # ── STEP 5: Remove from UI + store ──
        self._close_progress_dialogs_for(gids_to_remove)
        # This action is explicitly "remove AND delete files", so the
        # yt-dlp worker is asked to clean up whatever it produced.
        self._cancel_youtube_workers_for(gids_to_remove, delete_files=True)

        for gid in gids_to_remove:
            for q in self.store.queues:
                if gid in q.downloads:
                    q.downloads.remove(gid)
                if gid in q.downloads_info:
                    del q.downloads_info[gid]
            if gid in self._all_downloads:
                del self._all_downloads[gid]

        self.store.save()
        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_buttons()

    def _add_download(self) -> None:
        """Open the unified Add Download dialog (toolbar / Ctrl+N / Ctrl+U)."""
        self._open_or_update_add_dialog()

    def _remove_selected(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.information(self, "Info", "No downloads selected.")
            return

        gids_to_remove = [
            self.model.get_gid(idx.row())
            for idx in selected
            if self.model.get_gid(idx.row())
        ]
        if not gids_to_remove:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Remove Downloads")
        dlg.setMinimumWidth(500)
        dlg.setModal(True)

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(QLabel(f"Remove {len(gids_to_remove)} download(s)?"))
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

        result = {"value": None}

        def on_remove_only():
            result["value"] = "remove_only"
            dlg.accept()

        def on_remove_files():
            result["value"] = "remove_files"
            dlg.accept()

        def on_cancel():
            result["value"] = "cancel"
            dlg.reject()

        btn_remove_only.clicked.connect(on_remove_only)
        btn_remove_files.clicked.connect(on_remove_files)
        btn_cancel.clicked.connect(on_cancel)
        btn_remove_only.setDefault(True)

        dlg.exec()

        if result["value"] in (None, "cancel"):
            return

        delete_files = result["value"] == "remove_files"

        # If the user chose "Remove & Delete Files", show the confirmation
        # dialog FIRST — before touching any UI state — so cancelling is safe.
        if delete_files:
            if not self._delete_files_with_confirmation(gids_to_remove):
                return

        # Close any progress dialogs for these downloads first.
        self._close_progress_dialogs_for(gids_to_remove)

        # YouTube downloads are handled by a yt-dlp subprocess, not aria2.
        # Removing them from the list without cancelling the worker left the
        # process running (it is started in its own session) while the store
        # record was gone, so it kept writing files and -- because the
        # youtube store was never flushed -- the entry reappeared on restart.
        raw_gids = [self._get_aria2_gid(g) or g for g in gids_to_remove]
        self._cancel_youtube_workers_for(gids_to_remove, delete_files=delete_files)

        # Now remove from UI + aria2
        for gid in gids_to_remove:
            for q in self.store.queues:
                if gid in q.downloads:
                    q.downloads.remove(gid)
                if gid in q.downloads_info:
                    del q.downloads_info[gid]
            self._all_downloads.pop(gid, None)
            self._retrying_gids.discard(gid)
            self._size_unknown.discard(gid)

        try:
            self._worker_remove_multi([g for g in raw_gids if g])
        except Exception as e:
            print(f"⚠️ Batch remove failed: {e}")
            for gid in gids_to_remove:
                try:
                    self._worker_remove(gid)
                except Exception:
                    pass

        self._reset_speed_if_idle()
        self.store.save()
        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_buttons()

    def _cancel_youtube_workers_for(
        self, gids: List[str], delete_files: bool = False
    ) -> None:
        """Stop the yt-dlp worker behind any YouTube download in `gids`.

        aria2 removal does nothing for YouTube items (there is no aria2 gid),
        so without this the subprocess keeps running in the background.
        `delete_files` decides whether the worker also removes what it
        produced.
        """
        if not hasattr(self, "worker") or not self.worker:
            return

        for gid in gids:
            data = self._all_downloads.get(gid)
            if data is None:
                # Fall back to the persisted record: a queued YouTube item
                # may not be in the runtime dict yet.
                try:
                    if self.store.get_youtube_download(gid):
                        data = {"download_type": "youtube"}
                except Exception:
                    data = None
            if data is None or data.get("download_type") != "youtube":
                continue

            # Suppress the stats-snapshot handler from resurrecting this
            # item while the worker is still winding down.
            self._cancelling_youtube.add(gid)

            if gid in self._youtube_dialogs:
                try:
                    self._youtube_dialogs[gid].close()
                except Exception:
                    pass
                self._youtube_dialogs.pop(gid, None)

            try:
                if delete_files:
                    self.worker.cancel_youtube_download(gid)
                else:
                    self.worker.cancel_youtube_download_without_delete(gid)
            except Exception as e:
                print(f"⚠️ [Remove] Could not cancel YouTube worker {gid[:12]}: {e}")

            # Drop the persisted YouTube record so it cannot come back after
            # a restart.
            try:
                self.store.delete_youtube_download(gid)
            except Exception as e:
                print(f"⚠️ [Remove] Could not delete YouTube record {gid[:12]}: {e}")

            # Keep the guard for a while: a stats snapshot taken before the
            # cancel can still arrive and would re-create the row as
            # "downloading" -- a ghost nothing ever updates, which keeps the
            # tray icon green forever.
            QTimer.singleShot(5000, lambda g=gid: self._cancelling_youtube.discard(g))

    def _reset_speed_if_idle(self) -> None:
        has_active = any(
            self._all_downloads.get(g, {}).get("status") in ("active", "downloading")
            for g in self._all_downloads
        )
        if not has_active:
            self._speed_samples.clear()
            self._smooth_speed = 0
            self._last_calculated_global_speed = 0
            if hasattr(self, "speed_status_label"):
                self.speed_status_label.setText("0 B/s")

    def _download_has_started(self, info: dict) -> bool:
        """True when a download actually began, so it may have written files.

        A download that is only queued (or errored before any byte moved)
        must never have files attributed to it.
        """
        if not info:
            return False
        status = info.get("status", "")
        if status in ("active", "downloading", "complete", "completed"):
            return True
        return self._to_int(info.get("completedLength", 0)) > 0

    def _collect_files_for_gids(self, gids: List[str]) -> List[Dict[str, Any]]:
        """Build a list of files that WOULD be deleted for the given gids.

        Each entry is:
            {
                "gid": download_id,
                "path": absolute file path,
                "name": basename,
                "size": int (bytes) or 0,
                "kind": "main" | "sidecar",
                "exists": bool,
            }
        """
        entries: List[Dict[str, Any]] = []
        seen_paths: set = set()

        for gid in gids:
            file_paths: List[str] = []

            info = None
            for q in self.store.queues:
                if gid in q.downloads_info:
                    info = q.downloads_info[gid]
                    break

            runtime = self._all_downloads.get(gid)
            if info is None:
                info = runtime
            if info is None:
                continue

            # ── 1. Collect the file paths aria2 actually reported ──
            # A download that was only queued has a *predicted* path here
            # (built from the URL) but no file on disk yet, and it keeps
            # that path even after aria2 starts reporting it. So a path is
            # only treated as deletable when the download has actually
            # started AND the file exists. Without both checks a
            # never-started download could claim a pre-existing same-named
            # file in the user's folder and offer to delete it.
            started = self._download_has_started(info)
            candidate_paths: List[str] = []

            for f in info.get("files", []) or []:
                p = f.get("path")
                if p and p not in candidate_paths:
                    candidate_paths.append(p)

            # Also consider the runtime dict if it has additional paths not
            # present in downloads_info (rare, but possible right after a
            # re-add).
            runtime_info = self._all_downloads.get(gid)
            if runtime_info is not None:
                for f in runtime_info.get("files", []) or []:
                    p = f.get("path")
                    if p and p not in candidate_paths:
                        candidate_paths.append(p)

            if started:
                file_paths = [p for p in candidate_paths if os.path.isfile(p)]
            else:
                file_paths = []

            # ── 2. Add .aria2 sidecars for the known main files ──
            # aria2 always writes "<target>.aria2" next to the target
            # while the download is in progress or paused. We only add
            # it if the main file path is already known — never as a
            # free-floating guess.
            aria2_sidecars: List[str] = []
            for p in file_paths:
                sidecar = p + ".aria2"
                if sidecar not in aria2_sidecars:
                    aria2_sidecars.append(sidecar)

            # ── 3. Build entries ──
            for p in file_paths:
                if p in seen_paths:
                    continue
                seen_paths.add(p)
                exists = os.path.exists(p)
                try:
                    size = os.path.getsize(p) if exists else 0
                except OSError:
                    size = 0
                entries.append(
                    {
                        "gid": gid,
                        "path": p,
                        "name": os.path.basename(p),
                        "size": size,
                        "kind": "main",
                        "exists": exists,
                    }
                )

            for p in aria2_sidecars:
                if p in seen_paths:
                    continue
                seen_paths.add(p)
                exists = os.path.exists(p)
                try:
                    size = os.path.getsize(p) if exists else 0
                except OSError:
                    size = 0
                entries.append(
                    {
                        "gid": gid,
                        "path": p,
                        "name": os.path.basename(p),
                        "size": size,
                        "kind": "sidecar",
                        "exists": exists,
                    }
                )

        return entries

    def _delete_files_with_confirmation(self, gids: List[str]) -> bool:

        entries = self._collect_files_for_gids(gids)
        if not entries:
            print("🗑️ [Delete] No files to delete")
            return True

        from ui.dialogs import DeleteFilesConfirmationDialog

        dlg = DeleteFilesConfirmationDialog(entries, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            print("🗑️ [Delete] Cancelled by user")
            return False

        paths = dlg.get_paths_to_delete()
        if not paths:
            print("🗑️ [Delete] Nothing selected")
            return True

        deleted = 0
        for path in paths:
            try:
                # Re-validate: must be a regular file, must exist.
                if not os.path.exists(path):
                    continue
                if os.path.isdir(path):
                    print(f"⚠️ [Delete] Refusing to delete directory: {path}")
                    continue
                if not os.path.isfile(path):
                    continue

                os.remove(path)
                deleted += 1
                print(f"🗑️ DELETED: {os.path.basename(path)}")
            except PermissionError as e:
                print(f"⚠️ Permission denied: {path}: {e}")
            except OSError as e:
                print(f"⚠️ Delete failed {path}: {e}")
            except Exception as e:
                print(f"⚠️ Unexpected error deleting {path}: {e}")

        print(f"✅ Deleted {deleted} file(s)")
        return True

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

        self._show_singleton_dialog("youtube_download", dlg)

    def _add_youtube_to_queue(self, download_data: Dict[str, Any]) -> None:
        print("🎯 _add_youtube_to_queue CALLED")

        queue_name = download_data.get("queue_id", "Default")

        target_queue = self._get_or_create_queue(queue_name)

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
                "format_spec": yt_options.get("format_spec", "bv+ba/b"),
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
            "save_path": download_data["save_path"],
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
            "save_path": download_data["save_path"],
        }

        self.store.save()

        is_direct = queue_name == "__direct__"
        if is_direct:
            target_queue.paused = False
            self._all_downloads[download_id]["status"] = "downloading"
            target_queue.downloads_info[download_id]["status"] = "downloading"

            self.store.update_youtube_status(download_id, "downloading")

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

        if is_direct:
            QTimer.singleShot(
                300, lambda did=download_id: self._open_youtube_progress_dialog(did)
            )

        self._queue_list_dirty = True
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
            print(f"⚠️ [MainWindow] No worker available")
            return

        data = self.store.get_youtube_download(download_id)
        if not data:
            print(f"⚠️ [MainWindow] No data for {download_id}")
            return

        worker_exists = False
        try:
            with self.worker.youtube_lock:
                worker_exists = download_id in self.worker.youtube_workers
        except Exception:
            worker_exists = False

        if worker_exists:
            print(f"⏭️ [MainWindow] Worker already exists for {download_id}")
            return

        print(f"🎬 [MainWindow] Starting YouTube download: {download_id}")
        self.worker.add_youtube_download(
            {
                "id": download_id,
                "url": data["url"],
                "save_path": data["save_path"],
                "yt_options": data.get("yt_options", {}),
                "proxy": data.get("proxy"),
                "queue_id": data.get("queue_id"),
                # Explicit intent: this is a start request, so the worker
                # must not inherit a stale "paused" status from the store.
                "status": "downloading",
            }
        )

    def _pause_youtube_download(self, download_id: str) -> None:
        if not hasattr(self, "worker") or not self.worker:
            return

        self.worker.pause_youtube_download(download_id)

        if download_id in self._all_downloads:
            self._all_downloads[download_id]["status"] = "paused"

        for q in self.store.queues:
            if download_id in q.downloads_info:
                q.downloads_info[download_id]["status"] = "paused"
                break

        self.store.save()
        self._update_queue_buttons()
        self._refresh_table()

    def _resume_youtube_download(self, download_id: str) -> None:
        if not hasattr(self, "worker") or not self.worker:
            return

        worker_exists = False
        try:
            with self.worker.youtube_lock:
                worker_exists = download_id in self.worker.youtube_workers
        except Exception:
            worker_exists = False

        if worker_exists:
            print(f"▶️ [MainWindow] Resuming existing worker: {download_id}")
            self.worker.resume_youtube_download(download_id)
        else:
            print(f"🎬 [MainWindow] No active worker, starting fresh: {download_id}")
            data = self.store.get_youtube_download(download_id)
            if not data:
                print(f"⚠️ [MainWindow] No data for {download_id}")
                return
            self.worker.add_youtube_download(
                {
                    "id": download_id,
                    "url": data["url"],
                    "save_path": data["save_path"],
                    "yt_options": data.get("yt_options", {}),
                    "proxy": data.get("proxy"),
                    "queue_id": data.get("queue_id"),
                    # Resume is also an explicit "run now" request.
                    "status": "downloading",
                }
            )

        if download_id in self._all_downloads:
            self._all_downloads[download_id]["status"] = "downloading"

        for q in self.store.queues:
            if download_id in q.downloads_info:
                q.downloads_info[download_id]["status"] = "downloading"
                break

        self.store.save()
        self._update_queue_buttons()
        self._refresh_table()

    def _cancel_youtube_download(self, download_id: str) -> None:
        print(f"🗑️ [MainWindow] _cancel_youtube_download CALLED for: {download_id}")
        self._cancelling_youtube.add(download_id)
        print(
            f"🗑️ [MainWindow] _all_downloads count BEFORE: {len(self._all_downloads)}"
        )

        if not hasattr(self, "worker"):
            print(f"⚠️ [MainWindow] No worker")
            return

        print(f"🗑️ [MainWindow] Updating UI first...")

        if download_id in self._youtube_dialogs:
            try:
                self._youtube_dialogs[download_id].close()
            except Exception:
                pass
            self._youtube_dialogs.pop(download_id, None)

        self.store.delete_youtube_download(download_id)
        self.store.save()

        if download_id in self._all_downloads:
            del self._all_downloads[download_id]

        for q in self.store.queues:
            if download_id in q.downloads:
                q.downloads.remove(download_id)
            if download_id in q.downloads_info:
                del q.downloads_info[download_id]
        self.store.save()

        print(f"🗑️ [MainWindow] Calling worker.cancel_youtube_download...")
        try:
            self.worker.cancel_youtube_download(download_id)
        except Exception as e:
            print(f"⚠️ [MainWindow] Error in worker.cancel_youtube_download: {e}")

        self._reset_speed_if_idle()

        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_buttons()

        print(f"🗑️ [MainWindow] _all_downloads count AFTER: {len(self._all_downloads)}")
        print(f"🗑️ [MainWindow] Cancel complete for: {download_id}")
        QTimer.singleShot(
            5000, lambda did=download_id: self._cancelling_youtube.discard(did)
        )

    def _on_youtube_progress(self, download_id: str, progress: int) -> None:
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["progress"] = progress
            self._all_downloads[download_id]["status"] = "downloading"
            self._refresh_table()

    def _on_youtube_status(self, download_id: str, status: str) -> None:
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["status"] = status
            self._update_queue_buttons()
            self._refresh_table()

    def _on_youtube_speed(self, download_id: str, speed: str, eta: str) -> None:
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["speed"] = speed
            self._all_downloads[download_id]["eta"] = eta
            self._all_downloads[download_id]["downloadSpeed"] = self._parse_speed(speed)
            self._refresh_table()

    def _on_youtube_size_fetched(self, download_id: str, size: int) -> None:
        if size <= 0:
            self._size_unknown.add(download_id)
        else:
            self._size_unknown.discard(download_id)
        if download_id in self._all_downloads:
            self._all_downloads[download_id]["totalLength"] = max(size, 0)
            self._refresh_table()

    def _on_youtube_finished(
        self, download_id: str, success: bool, message: str
    ) -> None:
        print(f"🎬 [MainWindow] YouTube finished: {download_id} success={success}")

        if download_id in self._youtube_dialogs:
            dialog = self._youtube_dialogs[download_id]
            try:
                dialog.update_finished(success, message)
            except RuntimeError:
                self._youtube_dialogs.pop(download_id, None)

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

        self._refresh_table()

    def _open_youtube_progress_dialog(self, download_id: str) -> None:
        try:
            if not download_id:
                return

            if download_id in self._youtube_dialogs:
                dialog = self._youtube_dialogs[download_id]
                try:
                    if dialog.isVisible():
                        dialog.raise_()
                        dialog.activateWindow()
                        return
                    else:
                        dialog.deleteLater()
                        del self._youtube_dialogs[download_id]
                except RuntimeError:
                    del self._youtube_dialogs[download_id]

            data = self.store.get_youtube_download(download_id)
            if not data:
                QMessageBox.warning(self, "Error", "Download not found")
                return

            dialog = YouTubeProgressDialog(
                url=data["url"],
                output_path=data["save_path"],
                format_type=data.get("yt_options", {}).get("format", "mp4"),
                cookie_file=data.get("yt_options", {}).get("cookies_path"),
                video_info=data.get("video_info", {}),
                parent=None,
                proxy_url=data.get("proxy"),
                download_id=download_id,
            )

            dialog.setWindowFlags(
                Qt.WindowType.Window
                | Qt.WindowType.WindowCloseButtonHint
                | Qt.WindowType.WindowMinimizeButtonHint
            )
            dialog.setWindowModality(Qt.WindowModality.NonModal)

            dialog.pause_requested.connect(self._pause_youtube_download)
            dialog.resume_requested.connect(self._resume_youtube_download)
            dialog.cancel_requested.connect(self._cancel_youtube_download)

            dialog.finished.connect(
                lambda result, did=download_id: self._on_youtube_dialog_closed(
                    did, result
                )
            )

            self._youtube_dialogs[download_id] = dialog
            dialog.show()
            self._center_dialog_on_screen(dialog)

            video_title = (
                data.get("yt_options", {}).get("title") or data.get("name") or ""
            )
            if video_title:
                dialog.setWindowTitle(video_title)

            if download_id in self._all_downloads:
                dl_data = self._all_downloads[download_id]
                status = dl_data.get("status", "pending")
                progress = dl_data.get("progress", 0)
                speed = dl_data.get("speed", "")
                eta = dl_data.get("eta", "")

                dialog.update_progress(progress, speed, eta)

                if status == "paused":
                    dialog.update_pause_state(True)
                elif status == "downloading":
                    dialog.update_pause_state(False)
                elif status == "completed":
                    dialog.update_finished(True, "Download completed!")

        except Exception as e:
            print(f"❌ Error opening YouTube dialog: {e}")

    def _on_youtube_dialog_closed(self, download_id: str, result=None) -> None:
        if download_id in self._youtube_dialogs:
            dialog = self._youtube_dialogs.pop(download_id)
            try:
                dialog.deleteLater()
            except RuntimeError:
                pass

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.store.settings, self)
        self._show_singleton_dialog(
            "app_settings", dlg, on_accepted=self._process_settings
        )

    def _process_settings(self, dlg: "SettingsDialog") -> None:
        old_ssl = self.store.settings.get("disable_ssl_verify", False)
        old_port = self.store.settings.get("aria2_port", 6800)
        old_host = self.store.settings.get("aria2_host", "http://localhost")
        old_secret = self.store.settings.get("aria2_secret", "")

        s = dlg.get_settings()
        self.store.settings.update(s)
        self.store.save()

        theme = self.store.settings.get("theme", "auto")
        setup_style(QApplication.instance(), theme)

        new_ssl = self.store.settings.get("disable_ssl_verify", False)
        new_port = self.store.settings.get("aria2_port", 6800)
        new_host = self.store.settings.get("aria2_host", "http://localhost")
        new_secret = self.store.settings.get("aria2_secret", "")

        needs_restart = (
            old_ssl != new_ssl
            or old_port != new_port
            or old_host != new_host
            or old_secret != new_secret
        )

        if needs_restart:

            reply = QMessageBox.information(
                self,
                "Restart Required",
                "Some settings (SSL, Port, Host, Secret) require restarting aria2.\n\n"
                "Please restart FelfelDM for changes to take effect.\n\n"
                "Do you want to restart now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.quit_app()
                self.tray.showMessage(
                    "FelfelDM",
                    "✅ aria2 restarted with new settings",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )
            else:
                self.tray.showMessage(
                    "FelfelDM",
                    "⚠️ Some settings require restart.\nPlease restart FelfelDM later.",
                    QSystemTrayIcon.MessageIcon.Warning,
                    3000,
                )

        else:
            q = self._current_queue()
            has_queue_limit = q and q.speed_limit > 0

            if has_queue_limit:
                self.aria2.change_global_option({"max-overall-download-limit": "0"})
                print(f"⚡ [SpeedLimit] Queue limit wins over global")
                self._apply_queue_speed_limit(q)
            else:
                self._apply_global_speed_limit()

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

    def _apply_settings_to_aria2(self) -> bool:
        try:
            max_tries = self.store.settings.get("max_tries", 0)

            q = self._current_queue()
            if q and q.name != "__direct__" and q.max_concurrent > 0:
                max_concurrent = q.max_concurrent
                print(
                    f"📊 Using queue-specific concurrency: {max_concurrent} (queue: {q.name})"
                )
            else:
                max_concurrent = self.store.settings.get("max_concurrent", 5)
                print(f"📊 Using global concurrency: {max_concurrent}")

            options = {
                "max-concurrent-downloads": str(max_concurrent),
                "max-tries": str(max_tries),
            }

            if self.store.settings.get("disable_ssl_verify", False):
                options["check-certificate"] = "false"
            else:
                options["check-certificate"] = "true"

            self.aria2.change_global_option(options)
            return True
        except Exception as e:
            print(f"⚠️ Error applying settings: {e}")
            return False

    def _apply_global_speed_limit(self) -> None:
        limit = self.store.settings.get("speed_limit", 0)
        aria_limit = f"{limit}K" if limit > 0 else "0"
        try:
            self.aria2.change_global_option({"max-overall-download-limit": aria_limit})
            print(f"✅ [SpeedLimit] Global limit set to {aria_limit}")
        except Exception as e:
            print(f"⚠️ [SpeedLimit] Failed to set global limit: {e}")

    def _get_effective_speed_limit(self, download_id: str, q: Optional[Queue]) -> int:

        data = self._all_downloads.get(download_id, {})
        rule_speed = data.get("rule_speed_limit", 0)
        if rule_speed > 0:
            return rule_speed

        if q and q.speed_limit > 0:
            return q.speed_limit

        return 0

    def _apply_queue_speed_limit(self, q: Optional[Queue]) -> None:
        """Apply speed limits with priority: per-download > queue > global.

        - Downloads with their own speed_limit get that limit.
        - Remaining active downloads share the queue speed limit
          (if the queue has one).
        - If neither queue nor per-download limit is set, the aria2
          global limit applies (managed elsewhere).
        """
        if not q or not self.aria2:
            return

        # Split active downloads by whether they have a per-download limit
        limited = []
        unlimited = []

        for download_id in q.downloads:
            data = self._all_downloads.get(download_id, {})
            status = data.get("status", "")
            if status not in ("active", "downloading"):
                continue

            if data.get("speed_limit", 0) > 0:
                limited.append(download_id)
            else:
                unlimited.append(download_id)

        # 1. Apply each per-download limit directly
        for download_id in limited:
            speed = self._all_downloads[download_id].get("speed_limit", 0)
            if speed > 0:
                self._worker_set_speed_limit(download_id, speed)

        # 2. Remaining active downloads share the queue limit
        if q.speed_limit > 0 and unlimited:
            n = len(unlimited)
            per_download = max(1, q.speed_limit // n)
            print(
                f"⚡ [SpeedLimit] Queue '{q.name}': {q.speed_limit}K split "
                f"over {n} download(s) → {per_download}K each "
                f"({len(limited)} per-download limit(s) untouched)"
            )
            for download_id in unlimited:
                self._worker_set_speed_limit(download_id, per_download)
        elif not q.speed_limit and unlimited:
            # No queue limit and no per-download limit: let aria2's
            # global limit (or none) apply
            for download_id in unlimited:
                self._worker_set_speed_limit(download_id, 0)

    def _set_download_speed_limit(self, download_id: str, speed_kb: int) -> None:
        """Apply a per-download speed limit.

        speed_kb = 0 means "no per-download limit" — the download falls
        back to the queue speed limit (or global if the queue has none).
        """
        print(f"🔧 [SpeedLimit] CALLED: {download_id[:12]} → {speed_kb} KB/s")
        if not download_id or download_id not in self._all_downloads:
            return

        # Save in memory
        self._all_downloads[download_id]["speed_limit"] = speed_kb

        # Save in the persistent per-download info
        for q in self.store.queues:
            if download_id in q.downloads_info:
                q.downloads_info[download_id]["speed_limit"] = speed_kb
                break

        # Apply immediately via aria2
        aria2_gid = self._get_aria2_gid(download_id)
        if aria2_gid:
            limit_str = f"{speed_kb}K" if speed_kb > 0 else "0"
            try:
                self.aria2.change_option(aria2_gid, {"max-download-limit": limit_str})
                print(f"⚡ [SpeedLimit] {download_id[:12]} → {limit_str}")
            except Exception as e:
                print(f"⚠️ [SpeedLimit] Failed to set per-download limit: {e}")

        # Re-evaluate the queue so other downloads adjust their share
        q = self._current_queue()
        if q:
            self._apply_queue_speed_limit(q)

        self.store.mark_dirty()
        self._refresh_table()

    def _apply_proxy_to_aria2(self) -> None:
        proxy = self.proxy_manager.get_proxy_for_queue(None)
        if proxy and proxy.enabled and proxy.is_valid():
            if self.aria2.set_global_proxy(proxy) is not None:
                print(f"✅ Global proxy applied")
            else:
                print("⚠️ Failed to apply proxy")
        else:
            self.aria2.change_global_option({"all-proxy": ""})
            print("✅ Proxy disabled")

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

    def _toggle_shutdown(self, checked: bool) -> None:
        self.store.settings["shutdown_after_finish"] = checked
        self.store.save()

        if not checked and self._shutdown_dialog:
            self._shutdown_dialog.reject()
            self._shutdown_dialog = None
            self._shutdown_dialog_shown = False
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
            self._check_already_complete()

    def _check_already_complete(self) -> None:
        if not self._startup_complete:
            return

        if not self.shutdown_cb.isChecked() or self._shutdown_dialog_shown:
            return

        total = 0
        complete = 0

        for q in self.store.queues:
            for gid in q.downloads:
                total += 1
                status = self._all_downloads.get(gid, {}).get("status", "")

                if status in ["active", "waiting", "downloading"]:
                    return

                if status in ["complete", "completed", "error", "removed"]:
                    complete += 1

        if total == 0:
            return

        if complete == total:
            if not self._shutdown_dialog_shown:
                self._shutdown_dialog_shown = True
                self.tray.showMessage(
                    "🌶️ FelfelDM",
                    "✅ All downloads completed!\n🛑 System will shut down in 20 seconds.",
                    QSystemTrayIcon.MessageIcon.Information,
                    5000,
                )
                self._show_shutdown_countdown()

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

        # Issue the actual poweroff request BEFORE tearing the app down.
        # quit_app() ends with sys.exit(0), which kills this process
        # immediately — any code placed after that call never runs, which
        # was the bug: the app quit cleanly but the machine never powered
        # off because that call came first.
        self._request_system_poweroff()

        self.quit_app()

    def _request_system_poweroff(self) -> None:
        try:
            from PyQt6.QtDBus import QDBusInterface, QDBusConnection

            bus = QDBusConnection.systemBus()
            logind = QDBusInterface(
                "org.freedesktop.login1",
                "/org/freedesktop/login1",
                "org.freedesktop.login1.Manager",
                bus,
            )

            if logind.isValid():
                can = logind.call("CanPowerOff").arguments()
                if can and can[0] == "yes":
                    print("✅ [Shutdown] DBus PowerOff")
                    logind.call("PowerOff", False)
                    return
                else:
                    print(f"⚠️ [Shutdown] DBus cannot poweroff: {can}")
        except Exception as e:
            print(f"⚠️ [Shutdown] DBus failed: {e}")

        print("🔄 [Shutdown] Falling back to systemctl")
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

    def _open_progress_dialog(self, gid: str) -> None:
        dl_data = self._all_downloads.get(gid, {})

        if gid in self._progress_dialogs:
            dialog = self._progress_dialogs[gid]
            try:
                if dialog.isVisible():
                    dialog.raise_()
                    dialog.activateWindow()
                    return
                else:
                    dialog.deleteLater()
                    del self._progress_dialogs[gid]
            except RuntimeError:
                del self._progress_dialogs[gid]

        dialog = DownloadProgressDialog(gid, dl_data, parent=None, main_window=self)
        name = dl_data.get("name", "")
        if name:
            dialog.setWindowTitle(name)

        dialog.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
        )
        dialog.setWindowModality(Qt.WindowModality.NonModal)

        dialog.pause_requested.connect(self._pause_from_dialog)
        dialog.resume_requested.connect(self._resume_from_dialog)
        dialog.cancel_requested.connect(self._cancel_from_dialog)
        dialog.cancel_with_delete_requested.connect(
            self._cancel_with_delete_from_dialog
        )
        dialog.speed_limit_changed.connect(self._set_download_speed_limit)

        dialog.finished.connect(
            lambda result, g=gid: self._on_progress_dialog_closed(g, result)
        )

        self._progress_dialogs[gid] = dialog
        dialog.show()
        self._center_dialog_on_screen(dialog)

        if dl_data.get("totalLength", 0) == 0:
            dialog.info_labels["size"].setText("Getting size...")

    def _on_progress_dialog_closed(self, gid: str, result=None) -> None:
        if gid in self._progress_dialogs:
            dialog = self._progress_dialogs.pop(gid)
            try:
                dialog.deleteLater()
            except RuntimeError:
                pass

    def _close_progress_dialogs_for(self, gids: list) -> None:
        """Close any open DownloadProgressDialog for the given download ids.

        Called before removing a download from the UI/state so its progress
        window never lingers around showing stale data.
        """
        for gid in gids:
            if not gid:
                continue
            dialog = self._progress_dialogs.pop(gid, None)
            if dialog is None:
                continue
            try:
                dialog.close()
            except RuntimeError:
                pass
            try:
                dialog.deleteLater()
            except RuntimeError:
                pass

    def _pause_from_dialog(self, gid: str) -> None:
        if not gid or gid not in self._all_downloads:
            return

        real_status = self._all_downloads[gid].get("status", "")
        if real_status in ["active", "waiting", "downloading"]:
            self._worker_pause(gid)
            self._all_downloads[gid]["status"] = "paused"
            self._all_downloads[gid]["downloadSpeed"] = 0

            self._pending_status[gid] = (
                "paused",
                time.time() + 5.0,
            )
            self.store.save()
            self._refresh_table()
            self._update_queue_buttons()

    def _resume_from_dialog(self, gid: str) -> None:
        if not gid or gid not in self._all_downloads:
            return

        real_status = self._all_downloads[gid].get("status", "")
        download_type = self._all_downloads[gid].get("download_type", "normal")

        if download_type == "youtube":
            self._resume_youtube_download(gid)
            return

        if real_status == "error":
            print(f"🔄 Retrying error download from dialog: {gid}")
            self._retry_single_download(gid, manual=True)
            return

        if real_status == "paused":
            self._worker_resume(gid)
            self._all_downloads[gid]["status"] = "active"

            self._pending_status[gid] = (
                "active",
                time.time() + 5.0,
            )

            self.store.mark_dirty()
            self._refresh_table()
            self._update_queue_buttons()
            return

        if real_status in ["waiting", "stopped"]:
            self._worker_resume(gid)
            self._all_downloads[gid]["status"] = "active"
            self.store.mark_dirty()
            self._refresh_table()
            self._update_queue_buttons()

    def _cancel_from_dialog(self, gid: str) -> None:
        try:
            self._worker_remove(gid)
        except Exception:
            pass

        # Close the progress dialog (this method IS the cancel handler, so
        # the dialog is still open — pop and close it here).
        self._close_progress_dialogs_for([gid])

        for q in self.store.queues:
            if gid in q.downloads:
                q.downloads.remove(gid)

        if gid in self._all_downloads:
            del self._all_downloads[gid]

        self._reset_speed_if_idle()

        self.store.save()
        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._progress_dialog = None

    def _cancel_with_delete_from_dialog(self, gid: str) -> None:
        """Cancel a download and delete its files.

        Same ordering fix as _remove_with_files: stop aria2 FIRST,
        wait for the file handles to be released, THEN delete.
        """
        # Ask for confirmation FIRST, before touching aria2 or the UI.
        entries = self._collect_files_for_gids([gid])
        if entries:
            from ui.dialogs import DeleteFilesConfirmationDialog

            dlg = DeleteFilesConfirmationDialog(entries, parent=self)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                print("🗑️ [Delete] Cancelled by user")
                return

        # ── Force-remove from aria2 FIRST ──
        try:
            aria2_gid = self._get_aria2_gid(gid) or gid
            self.aria2.force_remove(aria2_gid)
            print(f"🗑️ force_remove sent for {aria2_gid[:12]}")
        except Exception as e:
            print(f"❌ force_remove failed: {e}")
            try:
                self._worker_remove(gid)
            except Exception:
                pass

        # ── Wait for aria2 to actually release the file handles ──
        import time as _time

        deadline = _time.time() + 2.0
        while _time.time() < deadline:
            try:
                status = self.aria2.get_status(gid)
                if not status or status.get("status") in (None, "removed"):
                    break
            except Exception:
                break
            _time.sleep(0.1)

        # ── Now delete the files ──
        if entries:
            paths = [e["path"] for e in entries]
            deleted = 0
            for path in paths:
                try:
                    if not os.path.exists(path):
                        continue
                    if os.path.isdir(path):
                        print(f"⚠️ [Delete] Refusing to delete directory: {path}")
                        continue
                    if not os.path.isfile(path):
                        continue
                    os.remove(path)
                    deleted += 1
                    print(f"🗑️ DELETED: {os.path.basename(path)}")
                except OSError as e:
                    print(f"⚠️ Delete failed {path}: {e}")
            print(f"✅ Deleted {deleted} file(s)")

        QApplication.processEvents()

        # Close the progress dialog for this download.
        self._close_progress_dialogs_for([gid])

        for q in self.store.queues:
            if gid in q.downloads:
                q.downloads.remove(gid)
            if gid in q.downloads_info:
                del q.downloads_info[gid]

        if gid in self._all_downloads:
            del self._all_downloads[gid]

        self._reset_speed_if_idle()

        self.store.save()
        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._progress_dialog = None

    def _pause_selected(self) -> None:
        """Pause every selected download that is currently active/waiting."""
        if not self.table.selectionModel():
            return

        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return

        gids = [self.model.get_gid(r.row()) for r in rows]
        gids = [g for g in gids if g]

        youtube_gids = []
        normal_gids = []

        for gid in gids:
            if gid not in self._all_downloads:
                continue
            dtype = self._all_downloads[gid].get("download_type", "normal")
            status = self._all_downloads[gid].get("status", "")

            if status not in ("active", "downloading"):
                continue

            if dtype == "youtube":
                youtube_gids.append(gid)
            else:
                normal_gids.append(gid)

        for gid in youtube_gids:
            self._pause_youtube_download(gid)

        for gid in normal_gids:
            self._all_downloads[gid]["status"] = "paused"
            self._all_downloads[gid]["downloadSpeed"] = 0
            self._pending_status[gid] = ("paused", time.time() + 5.0)

        if normal_gids:
            self._worker_pause_multi(normal_gids)

        self._refresh_table()
        self._update_queue_buttons()

    def _resume_selected(self) -> None:
        """Resume every selected download that is currently paused/waiting."""
        if not self.table.selectionModel():
            return

        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return

        gids = [self.model.get_gid(r.row()) for r in rows]
        gids = [g for g in gids if g]

        for gid in gids:
            if gid not in self._all_downloads:
                continue

            dtype = self._all_downloads[gid].get("download_type", "normal")
            status = self._all_downloads[gid].get("status", "")

            if dtype == "youtube":
                if status == "paused":
                    self._resume_youtube_download(gid)
                continue

            if status == "error":
                self._retry_single_download(gid, manual=True)
                continue

            if status == "paused":
                self._worker_resume(gid)
                self._all_downloads[gid]["status"] = "active"
                self._pending_status[gid] = ("active", time.time() + 5.0)

        self.store.mark_dirty()
        self._refresh_table()
        self._update_queue_buttons()

    def _retry_single_download(self, gid: str, manual: bool = False) -> None:
        """Retry a download.

        manual=True means the user explicitly clicked Retry: ask for
        confirmation, then reset the automatic retry budget to 0 so the
        download gets a fresh set of max_retry_attempts.

        manual=False (called by the delayed-retry scheduler) keeps the
        current count and enforces the cap silently.
        """
        if not gid or gid not in self._all_downloads:
            return

        if gid in self._retrying_gids:
            print(f"⏳ Already retrying {gid}")
            return

        max_retries = self.store.settings.get("max_retry_attempts", 5)
        error_count = self._to_int(self._all_downloads[gid].get("error_count", 0))

        if manual:
            # Ask the user before resetting. Text makes it clear that the
            # counter will start over, so they know what they're opting into.
            reply = QMessageBox.question(
                self,
                "Retry Download",
                "Do you want to try this download again?\n\n"
                "The retry counter will be reset to 0, so automatic retries "
                f"will be available again (up to {max_retries}).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

            if error_count > 0:
                print(
                    f"🖐️ [Retry] Manual retry for {gid[:12]}: "
                    f"resetting error_count {error_count} → 0"
                )
            self._all_downloads[gid]["error_count"] = 0
            for q in self.store.queues:
                if gid in q.downloads_info:
                    q.downloads_info[gid]["error_count"] = 0
                    break
            error_count = 0
        elif error_count >= max_retries:
            # Automatic retry exhausted — stop silently, don't nag the user.
            print(
                f"⏹️ [Retry] Automatic retries exhausted for {gid[:12]} "
                f"({error_count}/{max_retries})"
            )
            return

        print(f"🔄 Retrying {gid} (attempt {error_count + 1}/{max_retries})")

        self._all_downloads[gid]["status"] = "waiting"
        self._all_downloads[gid]["errorMessage"] = ""
        self._all_downloads[gid]["error_count"] = error_count + 1

        self._retrying_gids.add(gid)

        self.worker.re_add_requested.emit(gid)

        self._refresh_table()
        self._update_queue_buttons()

    def _re_add_download(self, gid: str) -> Optional[str]:
        if self.worker is None:
            return None
        self.worker.re_add_requested.emit(gid)
        return gid

    def _toggle_pause_resume(self) -> None:
        """Toggle pause/resume for all selected downloads.

        Logic:
        - If any is active/waiting → pause those (leave paused/error alone).
        - Else if any is paused → resume those (retry errored ones).
        - Else if exactly one error → retry it.
        - Otherwise → nothing.
        """
        if not self.table.selectionModel():
            return

        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return

        gids = [self.model.get_gid(r.row()) for r in rows]
        gids = [g for g in gids if g]
        if not gids:
            return

        active_gids = []
        paused_gids = []
        error_gids = []

        for gid in gids:
            status = self._all_downloads.get(gid, {}).get("status", "")
            if status in ("active", "downloading"):
                active_gids.append(gid)
            elif status == "paused":
                paused_gids.append(gid)
            elif status == "error":
                error_gids.append(gid)

        if active_gids:
            self._pause_selected()
        elif paused_gids:
            self._resume_selected()
        elif len(error_gids) == 1:
            self._retry_single_download(error_gids[0], manual=True)

    def _open_folder(self, gid: str) -> None:
        try:
            folder_path = self._find_download_folder(gid)
            if folder_path and os.path.exists(folder_path):
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder_path))
            else:
                QMessageBox.warning(self, "Error", f"Folder not found:\n{folder_path}")
        except Exception as e:
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
                dl_save_path = info.get("save_path") or q.save_path
                if dl_save_path and os.path.exists(dl_save_path):
                    return dl_save_path

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

    def _context_menu(self, pos: QPoint) -> None:
        if not self.table.selectionModel():
            return

        rows = self.table.selectionModel().selectedRows()

        # No selection: sort-only menu
        if len(rows) == 0:
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

        # Multiple selection: bulk menu
        if len(rows) > 1:
            menu = QMenu(self)
            n = len(rows)

            # Gather statuses
            statuses = []
            for r in rows:
                gid = self.model.get_gid(r.row())
                if not gid:
                    continue
                status = self._all_downloads.get(gid, {}).get("status", "")
                if status:
                    statuses.append(status)

            has_active = any(s in ("active", "downloading") for s in statuses)
            has_paused = any(s == "paused" for s in statuses)
            has_error = any(s == "error" for s in statuses)

            if has_active:
                menu.addAction(
                    get_icon("media-playback-pause"),
                    f"Pause {n} downloads",
                    self._pause_selected,
                )
            if has_paused:
                menu.addAction(
                    get_icon("media-playback-start"),
                    f"Resume {n} downloads",
                    self._resume_selected,
                )
            if has_error and n == 1:
                menu.addAction(
                    get_icon("view-refresh"),
                    "Retry",
                    lambda: self._retry_single_download(
                        self.model.get_gid(rows[0].row()), manual=True
                    ),
                )

            menu.addSeparator()
            menu.addAction(
                get_icon("go-next"),
                f"Move {n} to Queue...",
                self._move_selected_to_queue,
            )
            menu.addSeparator()
            menu.addAction(
                get_icon("edit-delete"),
                f"Remove {n} downloads",
                self._remove_selected,
            )
            menu.exec(self.table.viewport().mapToGlobal(pos))
            return
        # Single selection: existing per-download menu
        gid = self.model.get_gid(rows[0].row())
        if not gid:
            return

        dl_data = self._all_downloads.get(gid, {})
        download_type = dl_data.get("download_type", "normal")
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
        elif real_status == "error":
            menu.addAction(
                get_icon("view-refresh"),
                "Retry",
                lambda: self._retry_single_download(gid, manual=True),
            )

        menu.addSeparator()
        menu.addAction(
            get_icon("folder"), "Open Folder", lambda: self._open_folder(gid)
        )
        menu.addAction(get_icon("edit-copy"), "Copy URL", lambda: self._copy_link(gid))
        menu.addSeparator()
        menu.addAction(get_icon("edit-delete"), "Remove", self._remove_selected)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _add_queue(self) -> None:
        name, ok = QInputDialog.getText(self, "New Queue", "Queue name:")
        if not ok:
            return

        name = (name or "").strip()
        if not name:
            return

        if name == "Default":
            QMessageBox.warning(self, "Error", "Queue name 'Default' is reserved.")
            return

        # A queue name is used as a dictionary key for schedules and proxies,
        # so duplicates would silently shadow each other.
        if any(q.name == name for q in self.store.queues):
            QMessageBox.warning(
                self, "Error", f"A queue named '{name}' already exists."
            )
            return

        new_queue = Queue(name, paused=True)
        self.store.queues.append(new_queue)
        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_buttons()

    def _edit_queue(self) -> None:
        q = self._current_queue()
        if not q or q.name == "__direct__":
            return

        dlg = QueueSettingsDialog(q, self)
        self._show_singleton_dialog(
            f"queue_settings:{id(q)}",
            dlg,
            on_accepted=lambda dlg, q=q: self._process_edit_queue(dlg, q),
        )

    def _process_edit_queue(self, dlg: "QueueSettingsDialog", q: Queue) -> None:
        d = dlg._cached_data
        if not d:
            return

        new_name = (d.get("name") or "").strip()
        if not new_name:
            QMessageBox.warning(self, "Error", "Queue name is required.")
            return

        # "Default" is reserved for NEW queues — but editing the existing
        # Default queue without renaming it is fine, so only reject the
        # name when the queue is actually being renamed TO it.
        if new_name == "Default" and q.name != "Default":
            QMessageBox.warning(self, "Error", "Queue name 'Default' is reserved.")
            return

        # Renaming onto an existing queue name would make the two share a
        # schedule/proxy key and shadow each other.
        if new_name != q.name and any(
            other.name == new_name for other in self.store.queues
        ):
            QMessageBox.warning(
                self, "Error", f"A queue named '{new_name}' already exists."
            )
            return

        old_name = q.name
        q.name = new_name
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

        # Drop the old name's proxy entry, otherwise a rename leaves a stale
        # key behind that can be handed out for the previous name.
        if old_name != q.name:
            self.proxy_manager.remove_queue_proxy(old_name)

        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_buttons()
        self._apply_settings_to_aria2()

        if q.speed_limit > 0:
            self.aria2.change_global_option({"max-overall-download-limit": "0"})
            print(f"⚡ [SpeedLimit] Global disabled (queue '{q.name}' has limit)")
        self._load_schedules()
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
            self._queue_list_dirty = True
            self._refresh_queue_list()
            self._update_queue_buttons()

    def _move_queue_up(self) -> None:
        current_row = self.queue_list.currentRow()
        if current_row <= 0:
            return

        self.store.queues.insert(current_row - 1, self.store.queues.pop(current_row))
        self._current_queue_idx = current_row - 1

        self.store.save()
        self._queue_list_dirty = True
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
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self.queue_list.setCurrentRow(self._current_queue_idx)
        self._on_queue_changed(self._current_queue_idx)

    def _move_selected_to_queue(self) -> None:
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            return

        gids_to_move = [
            self.model.get_gid(idx.row())
            for idx in selected
            if self.model.get_gid(idx.row())
        ]
        if not gids_to_move:
            return

        source_queue = self._current_queue()
        if not source_queue:
            return

        target_queues = [
            q
            for q in self.store.queues
            if q.name != source_queue.name and q.name != "__direct__"
        ]
        if not target_queues:
            QMessageBox.warning(self, "Error", "No other queues available.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Move to Queue")
        dlg.setMinimumWidth(400)

        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"Move {len(gids_to_move)} download(s) to:"))
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

        for gid in gids_to_move:
            if gid in source_queue.downloads:
                source_queue.downloads.remove(gid)

            if gid not in target_queue.downloads:
                target_queue.downloads.append(gid)

            if gid in source_queue.downloads_info:
                info = source_queue.downloads_info.pop(gid)
                target_queue.downloads_info[gid] = info

            was_paused = self._all_downloads.get(gid, {}).get("status") == "paused"

            if target_queue.paused:
                if not was_paused:
                    self._worker_pause(gid)
                if gid in self._all_downloads:
                    self._all_downloads[gid]["status"] = "paused"
                    self._all_downloads[gid]["downloadSpeed"] = 0
                if gid in target_queue.downloads_info:
                    target_queue.downloads_info[gid]["status"] = "paused"
            else:
                if was_paused:
                    self._worker_resume(gid)
                if gid in self._all_downloads:
                    self._all_downloads[gid]["status"] = "active"
                if gid in target_queue.downloads_info:
                    target_queue.downloads_info[gid]["status"] = "active"

        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._refresh_table()
        self._update_queue_buttons()

        self._apply_queue_speed_limit(target_queue)

    def _restore_downloads(self) -> None:
        print("🔄 Loading downloads from storage...")

        original_on_error = self.aria2.on_error
        self.aria2.on_error = None

        try:
            if not self.aria2.is_connected():
                print("⏳ Waiting for aria2 to connect...")
                for attempt in range(15):
                    time.sleep(0.5)
                    if self.aria2.is_connected():
                        print(f"✅ aria2 connected after {attempt+1} attempts")
                        break

            active_gids = set()
            waiting_gids = set()
            stopped_gids = set()
            live_gids = set()
            try:
                for dl in self.aria2.tell_active() or []:
                    if dl.get("gid"):
                        active_gids.add(dl["gid"])
                        live_gids.add(dl["gid"])
                for dl in self.aria2.tell_waiting() or []:
                    if dl.get("gid"):
                        waiting_gids.add(dl["gid"])
                        live_gids.add(dl["gid"])
                for dl in self.aria2.tell_stopped(0, 300) or []:
                    if dl.get("gid"):
                        stopped_gids.add(dl["gid"])
                        live_gids.add(dl["gid"])
                pass
            except Exception as e:
                print(f"⚠️ [Restore] Could not fetch aria2 status: {e}")

            auto_clear = self.store.settings.get("auto_clear_completed", False)
            restored_count = 0
            needs_save = False

            for q in self.store.queues:
                to_remove = []

                for download_id in q.downloads:
                    info = q.downloads_info.get(download_id, {})
                    status = info.get("status", "")

                    if auto_clear and status in ["complete", "completed"]:
                        to_remove.append(download_id)
                        needs_save = True
                        continue

                    if not info:
                        info = {
                            "name": "Unknown",
                            "status": "paused",
                            "totalLength": 0,
                            "completedLength": 0,
                            "files": [],
                            "category": "📁 Other",
                            "download_type": "normal",
                        }
                        q.downloads_info[download_id] = info
                        needs_save = True

                    total_length = int(info.get("totalLength", 0))
                    if total_length == 0:
                        files = info.get("files", [])
                        if files and files[0].get("length"):
                            try:
                                total_length = int(files[0]["length"])
                            except (ValueError, TypeError):
                                pass

                    info_status = info.get("status", "")
                    completed_length = int(info.get("completedLength", 0))
                    files = info.get("files", [])
                    download_type = info.get("download_type", "normal")
                    category = info.get("category", "📁 Other")
                    name = info.get("name", "Unknown")
                    aria2_gid = info.get("aria2_gid")

                    if not files or not files[0].get("path"):
                        dl_save_path = info.get("save_path") or q.save_path
                        if name and dl_save_path:
                            files = [{"path": os.path.join(dl_save_path, name)}]

                    if name == "Unknown":
                        if files and files[0].get("path"):
                            name = os.path.basename(files[0]["path"])
                    if name == "Unknown":
                        url = info.get("url", "")
                        if url:
                            name = url.split("/")[-1].split("?")[0]

                    if info_status in ["complete", "completed"]:
                        final_status = "complete"
                    elif aria2_gid and aria2_gid in live_gids:

                        final_status = "paused"
                    else:

                        if info_status in ["complete", "completed"]:
                            final_status = "complete"
                        else:
                            final_status = "error"
                            print(
                                f"⚠️ [Restore] {download_id[:12]} has dead GID "
                                f"({aria2_gid}) → marking as error for re-add"
                            )

                    matched_rule_name = info.get("matched_rule")
                    rule_speed = info.get("rule_speed_limit", 0)

                    url = info.get("url", "")
                    if url and download_type == "normal":
                        try:
                            _rule = self.store.rule_engine.find_match(url)
                            if _rule:
                                matched_rule_name = _rule.name
                                if _rule.speed_limit:
                                    rule_speed = _rule.speed_limit
                        except Exception as e:
                            print(f"⚠️ [Restore] Rule match failed for {url}: {e}")

                    self._all_downloads[download_id] = {
                        "id": download_id,
                        "aria2_gid": aria2_gid,
                        "gid": aria2_gid,
                        "name": name,
                        "status": final_status,
                        "totalLength": total_length,
                        "completedLength": completed_length,
                        "downloadSpeed": 0,
                        "connections": 0,
                        "files": files,
                        "errorMessage": "",
                        "category": category,
                        "size_fetch_attempts": (1 if total_length > 0 else 0),
                        "error_count": 0,
                        "download_type": download_type,
                        "matched_rule": matched_rule_name,
                        "rule_speed_limit": rule_speed,
                        "proxy_url": info.get("proxy_url", ""),
                    }

                    q.downloads_info[download_id]["status"] = final_status
                    q.downloads_info[download_id]["totalLength"] = total_length
                    q.downloads_info[download_id]["aria2_gid"] = aria2_gid
                    q.downloads_info[download_id]["matched_rule"] = matched_rule_name
                    q.downloads_info[download_id]["rule_speed_limit"] = rule_speed
                    restored_count += 1

                for download_id in to_remove:
                    q.downloads.remove(download_id)
                    if download_id in q.downloads_info:
                        del q.downloads_info[download_id]
                    if download_id in self._all_downloads:
                        del self._all_downloads[download_id]

            if needs_save:
                self.store.save()

            print(f"✅ Loaded {restored_count} download(s)")
            print(f"📊 _all_downloads has {len(self._all_downloads)} entries")

            for download_id, data in self._all_downloads.items():
                if data.get("status") not in ("complete", "error", "removed"):
                    data["status"] = "paused"

                    # Short TTL: this only needs to cover the gap until the
                    # first stats poll arrives. The previous 999999s value
                    # pinned every restored download to "Paused" in the UI
                    # for ~11.5 days, even while aria2 reported it active.
                    self._pending_status[download_id] = (
                        "paused",
                        time.time() + 10.0,
                    )

            for q in self.store.queues:
                q.paused = True
                q.manually_paused = True
            self.store.save()

            print(
                f"⏸️ [Restore] All downloads set to paused "
                f"({len(self._all_downloads)} items)"
            )

        finally:
            self.aria2.on_error = original_on_error

    def _pause_all_aria2_downloads(self) -> None:
        print("⏸️ Pausing all downloads in aria2...")

        if not self.aria2.is_connected():
            print("⚠️ aria2 not connected, skipping pause")
            return

        all_gids = []
        for q in self.store.queues:
            for gid in q.downloads:
                all_gids.append(gid)
        ui_gids = set(all_gids)

        paused_count = 0
        if all_gids:
            try:
                if self.aria2.pause_multi(all_gids):
                    paused_count = len(all_gids)
            except Exception as e:
                print(f"⚠️ Bulk pause on restore failed: {e}")

        try:
            active_downloads = self.aria2.tell_active() or []
            for dl in active_downloads:
                gid = dl.get("gid")
                if gid and gid not in ui_gids:
                    print(f"🗑️ Pausing orphan download: {gid}")
                    try:
                        self.aria2.pause(gid)
                        self.aria2.remove(gid)
                        self.aria2._call("aria2.removeDownloadResult", [gid])
                    except Exception as e:
                        print(f"⚠️ Could not remove orphan {gid}: {e}")
        except Exception as e:
            print(f"⚠️ Error cleaning orphan downloads: {e}")

        for q in self.store.queues:
            q.paused = True
            q.manually_paused = True

        self.store.save()
        print(f"✅ Paused {paused_count} download(s) in aria2")

    def _clear_completed_downloads(self) -> None:
        q = self._current_queue()
        if not q:
            return

        completed_gids = [
            gid
            for gid in q.downloads
            if gid in self._all_downloads
            and self._all_downloads[gid].get("status", "") in ["complete", "completed"]
        ]

        if not completed_gids:
            QMessageBox.information(self, "Info", "No completed downloads to clear.")
            return

        if (
            QMessageBox.question(
                self,
                "Clear Completed",
                f"Remove {len(completed_gids)} completed download(s)?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.No
        ):
            return

        self._close_progress_dialogs_for(completed_gids)

        for gid in completed_gids:
            try:
                self._worker_remove(gid)
            except Exception:
                pass

            if gid in q.downloads:
                q.downloads.remove(gid)
            if gid in self._all_downloads:
                del self._all_downloads[gid]

        self.store.save()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._refresh_table()
        self._update_queue_buttons()

    def _update_youtube_dialogs(self, youtube_downloads: List[Dict]) -> None:
        for yt_data in youtube_downloads:
            if not isinstance(yt_data, dict):
                continue

            yt_id = yt_data.get("id")
            if not yt_id:
                continue

            if yt_id in self._cancelling_youtube:
                print(f"⏭️ [MainWindow] Skipping cancelling download: {yt_id[:8]}")
                continue

            # Never resurrect a row that is neither in the UI nor in a queue.
            if yt_id not in self._all_downloads and not any(
                yt_id in q.downloads for q in self.store.queues
            ):
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
                    "files": [],
                    "errorMessage": "",
                    "category": "🎬 YouTube",
                    "download_type": "youtube",
                }

            if saved_data and saved_data.get("status") != status:
                self.store.update_youtube_status(yt_id, status)

            self._update_open_youtube_dialog(
                yt_id, status, progress, speed, eta, total_size
            )

        # Self-heal: a YouTube row that still claims to be active although
        # the worker no longer knows it can never finish, and it would keep
        # the tray icon green. Mark it paused so the user can resume/remove.
        reported = {d.get("id") for d in youtube_downloads if isinstance(d, dict)}
        for did, info in self._all_downloads.items():
            if (
                info.get("download_type") == "youtube"
                and info.get("status") in ("active", "downloading")
                and did not in reported
                and did not in self._cancelling_youtube
            ):
                info["status"] = "paused"
                info["speed"] = ""
                info["downloadSpeed"] = 0

    def _update_open_youtube_dialog(
        self,
        download_id: str,
        status: str,
        progress: int,
        speed: str,
        eta: str,
        total_size: int,
    ) -> None:
        if download_id not in self._youtube_dialogs:
            return

        dialog = self._youtube_dialogs[download_id]

        try:
            dialog.update_progress(progress, speed, eta)

            if status == "paused":
                dialog.update_pause_state(True)
            elif status in ("downloading", "active"):
                dialog.update_pause_state(False)

            if status in ("completed", "complete"):
                dialog.update_finished(True, "Download completed successfully!")
            elif status == "error":
                msg = self._all_downloads.get(download_id, {}).get(
                    "errorMessage", "Download failed"
                )
                dialog.update_finished(False, msg)
        except RuntimeError:
            self._youtube_dialogs.pop(download_id, None)

    def _handle_re_add_result(self, result: dict) -> None:
        """Apply the outcome of a re-add to the download it belongs to.

        The worker reports the download id together with the result, so
        several retries in flight at once can never be mixed up.
        """
        req_id = result.get("id")
        new_gid = result.get("new")

        download_id = None
        if req_id in self._all_downloads:
            download_id = req_id
        else:
            for did, ddata in self._all_downloads.items():
                if ddata.get("aria2_gid") == req_id:
                    download_id = did
                    break

        if not result.get("success") or not isinstance(new_gid, str):
            reason = result.get("error") or "re-add failed"
            print(f"❌ [Retry] Re-add failed for {str(req_id)[:12]}: {reason}")
            if download_id:
                # Release the "already retrying" lock.
                self._retrying_gids.discard(download_id)

                # Record the failure message (only if we don't already
                # have one — the original error may be more informative).
                if not self._all_downloads[download_id].get("errorMessage"):
                    self._all_downloads[download_id][
                        "errorMessage"
                    ] = f"Retry failed: {reason}"

                # C2 fix: a re-add failure is transient (aria2 busy,
                # momentary RPC drop, etc.), so schedule another retry
                # instead of leaving the download in 'error' forever.
                # _schedule_retry enforces the max_retries cap itself.
                error_count = self._to_int(
                    self._all_downloads[download_id].get("error_count", 0)
                )
                self._schedule_retry(download_id, error_count)
                self._refresh_table()
                self._update_queue_buttons()
            return

        if not download_id:
            print(f"⚠️ [Retry] No download found for new_gid={new_gid}")
            try:
                self.aria2.remove(new_gid)
            except Exception:
                pass
            return

        old_gid = self._all_downloads[download_id].get("aria2_gid")

        self._all_downloads[download_id]["aria2_gid"] = new_gid
        self._all_downloads[download_id]["status"] = "active"

        for q in self.store.queues:
            if download_id in q.downloads_info:
                q.downloads_info[download_id]["aria2_gid"] = new_gid
                q.downloads_info[download_id]["status"] = "active"
                break

        self.store.save()

        self._retrying_gids.discard(download_id)

        print(
            f"✅ [Retry] Complete: id={download_id[:12]} "
            f"aria2_gid: {old_gid} -> {new_gid}"
        )

        QTimer.singleShot(100, lambda g=new_gid: self.worker.resume_requested.emit(g))

        self._refresh_table()
        self._queue_list_dirty = True
        self._refresh_queue_list()
        self._update_queue_buttons()

    def _on_worker_operation_result(self, operation: str, result: Any) -> None:
        """Handle results from worker operations (re_add, add_url, etc.)"""

        if operation == "re_add":
            if not isinstance(result, dict):
                return
            self._handle_re_add_result(result)

        elif operation == "add_url" and result is not None:
            print(f"✅ Add URL result: {result}")
        else:
            print(f"ℹ️ [Worker] Operation result: {operation} -> {result}")

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
                    pixmap.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio)
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

        update_btn = QPushButton(get_icon("system-software-update"), "Update")
        update_btn.setMinimumWidth(160)
        update_btn.clicked.connect(lambda: (dialog.accept(), self._update()))

        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(100)
        close_btn.clicked.connect(dialog.accept)

        btn_layout.addStretch()
        btn_layout.addWidget(update_btn)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        dialog.exec()

    def _update(self) -> None:
        """Open the update dialog to install the latest version."""
        key = "update_dialog"
        existing = self._open_dialogs.get(key)
        if existing is not None:
            try:
                if existing.isVisible():
                    existing.raise_()
                    existing.activateWindow()
                    return
            except RuntimeError:
                self._open_dialogs.pop(key, None)

        from ui.update_dialog import UpdateDialog

        dlg = UpdateDialog(parent=self)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._open_dialogs[key] = dlg

        def _cleanup(*_):
            if self._open_dialogs.get(key) is dlg:
                self._open_dialogs.pop(key, None)

        dlg.finished.connect(_cleanup)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def closeEvent(self, event: QCloseEvent) -> None:
        # ── Is anything actively downloading? ──
        has_active = False
        for q in self.store.queues:
            for gid in q.downloads:
                if gid in self._all_downloads:
                    status = self._all_downloads[gid].get("status", "")
                    if status in ("active", "waiting", "downloading"):
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
                QMessageBox.StandardButton.No,
            )
            # C41 fix: "No" must keep the window open, not hide it.
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

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

        # ── No active downloads: hide to tray, or quit if no tray ──
        if hasattr(self, "tray") and self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            self.quit_app()
            event.accept()

    def quit_app(self) -> None:
        """Quit the application for real (tray → Quit, or no tray).

        C43 fix: iterate _youtube_dialogs.values(), not .items() — the
        old code passed (key, value) tuples to .close(), and every
        close silently failed inside the except block.

        C44 fix: call worker.stop() explicitly, then wait for the
        thread to finish. quit() is a no-op on a QThread with a custom
        run(), so the old code left BackendWorker polling forever and
        yt-dlp children (which use start_new_session=True) survived
        the app's exit and kept writing to .part files.
        """
        print("🛑 Shutting down...")

        # ── 1. Stop the scheduler (only on real quit) ──
        if hasattr(self, "schedule_thread") and self.schedule_thread:
            try:
                self.schedule_thread.stop()
            except Exception as e:
                print(f"⚠️ Error stopping scheduler: {e}")

        # ── 2. Stop retry timers ──
        if self._countdown_timer:
            self._countdown_timer.stop()
        for t in self._retry_timers.values():
            try:
                t.stop()
            except Exception:
                pass
        self._retry_timers.clear()
        self._retry_state.clear()
        self._retrying_gids.clear()

        # ── 3. Stop the speed-update timer ──
        if hasattr(self, "speed_update_timer") and self.speed_update_timer:
            self.speed_update_timer.stop()

        # ── 4. Splash screen ──
        theme_setting: str = self.store.settings.get("theme", "auto")
        is_dark: bool = self._detect_theme(theme_setting)
        shutdown_dialog = SplashScreen(is_dark=is_dark)
        shutdown_dialog.show()
        QApplication.processEvents()

        # ── 5. Ask backend to save session + pause downloads ──
        shutdown_dialog.update_status("Saving session...", 10)
        try:
            if self.worker:
                self.worker.save_session_requested.emit()
        except Exception:
            pass

        shutdown_dialog.update_status("Pausing downloads...", 20)
        for q in self.store.queues:
            for gid in q.downloads:
                try:
                    if gid in self._all_downloads:
                        status = self._all_downloads[gid].get("status", "")
                        if status in ("active", "waiting", "downloading"):
                            if self.worker:
                                self._worker_pause(gid)
                            self._all_downloads[gid]["status"] = "paused"
                            self._all_downloads[gid]["downloadSpeed"] = 0
                except Exception:
                    pass
            q.paused = True

        shutdown_dialog.update_status("Saving data...", 35)
        try:
            self._save_downloads_info()
            self.store.save()
        except Exception as e:
            print(f"⚠️ Error saving data: {e}")

        # ── 6. Close all progress dialogs ──
        shutdown_dialog.update_status("Closing dialogs...", 45)
        for gid, dialog in list(self._progress_dialogs.items()):
            try:
                dialog.close()
                dialog.deleteLater()
            except Exception:
                pass
        self._progress_dialogs.clear()

        # C43 fix: values(), not items().
        for dlg in list(self._youtube_dialogs.values()):
            try:
                dlg.close()
                dlg.deleteLater()
            except Exception:
                pass
        self._youtube_dialogs.clear()

        # ── 7. Stop BackendWorker properly (C44 fix) ──
        shutdown_dialog.update_status("Stopping backend...", 55)
        if hasattr(self, "worker") and self.worker:
            try:
                # Ask the worker loop to exit and cancel all yt-dlp
                # children so they don't survive as orphans.
                self.worker.stop()
            except Exception as e:
                print(f"⚠️ Error stopping worker: {e}")
            try:
                self.worker.wait(3000)
            except Exception:
                pass

        # ── 8. Shutdown aria2 ──
        shutdown_dialog.update_status("Stopping aria2...", 70)
        try:
            if self.aria2:
                self.aria2.save_session()
                self._stop_own_aria2()
        except Exception as e:
            print(f"⚠️ Error during aria2 shutdown: {e}")

        # ── 9. Flush datastore ──
        shutdown_dialog.update_status("Closing data store...", 85)
        if hasattr(self.store, "shutdown"):
            try:
                self.store.shutdown()
            except Exception as e:
                print(f"⚠️ Error closing datastore: {e}")

        # ── 10. Stop the local extension server ──
        # Never stopped before: the port stayed bound until the process was
        # reaped, so a quick restart could hit "address already in use" and
        # the extension saw a dead server it still believed was up.
        shutdown_dialog.update_status("Stopping local server...", 92)
        if getattr(self, "local_server", None) is not None:
            try:
                self.local_server.stop()
            except Exception as e:
                print(f"⚠️ Error stopping local server: {e}")
            self.local_server = None

        shutdown_dialog.update_status("👋 Goodbye...", 100)
        if hasattr(self, "tray"):
            try:
                self.tray.hide()
            except Exception:
                pass

        QApplication.processEvents()

        print("🛑 Shutdown complete")
        import sys

        sys.exit(0)

    def _save_downloads_info(self) -> None:
        for q in self.store.queues:
            for gid in q.downloads:
                if gid in self._all_downloads:
                    dl = self._all_downloads[gid]
                    if gid not in q.downloads_info:
                        q.downloads_info[gid] = {}

                    name = dl.get("name", "")
                    if not name or name == "Unknown":
                        name = q.downloads_info[gid].get("name", "")
                    if not name or name == "Unknown":
                        files = dl.get("files", [])
                        if files and files[0].get("path"):
                            name = os.path.basename(files[0]["path"])
                    if not name or name == "Unknown":
                        url = q.downloads_info[gid].get("url", "")
                        if url:
                            name = url.split("/")[-1].split("?")[0]
                    if not name:
                        name = "Unknown"

                    total_length = dl.get("totalLength", 0)
                    if total_length == 0:

                        total_length = q.downloads_info[gid].get("totalLength", 0)
                    if total_length == 0:

                        files = dl.get("files", [])
                        if files and files[0].get("length"):
                            try:
                                total_length = int(files[0]["length"])
                            except (ValueError, TypeError):
                                pass
                    if total_length == 0:

                        try:
                            if self.aria2 and self.aria2.is_connected():
                                status_data = self.aria2.get_status(gid)
                                if status_data:
                                    aria2_total = int(status_data.get("totalLength", 0))
                                    if aria2_total > 0:
                                        total_length = aria2_total
                        except:
                            pass

                    q.downloads_info[gid].update(
                        {
                            "url": q.downloads_info[gid].get("url", ""),
                            "name": name,
                            "totalLength": total_length,
                            "completedLength": dl.get("completedLength", 0),
                            "status": dl.get("status", "unknown"),
                            "files": dl.get("files", []),
                            "category": dl.get("category", "📁 Other"),
                            "error_count": dl.get("error_count", 0),
                            "errorMessage": dl.get("errorMessage", ""),
                            "download_type": dl.get("download_type", "normal"),
                        }
                    )

    @pyqtSlot(list)
    def _add_from_extension(self, urls: List[str]) -> None:
        """Add URLs coming from the browser extension.

        If the Add Download dialog is already open, the URLs are merged
        into the existing editor; otherwise a new dialog is opened
        pre-filled with them.
        """
        if not urls:
            return
        self._open_or_update_add_dialog(urls)

    def _is_retriable_error(self, error_msg: str) -> bool:
        if not error_msg:
            return True
        msg = error_msg.lower()
        return not any(p in msg for p in self._PERMANENT_ERROR_PATTERNS)

    def _on_download_error(self, download_id: str, error_msg: str) -> None:
        data = self._all_downloads.get(download_id)
        if not data:
            return

        if data.get("download_type") == "youtube":
            return

        if download_id in self._retrying_gids:
            return

        if download_id in self._retry_state:
            return

        if data.get("status") == "retrying":
            return

        print(
            f"🔴 [Error] _on_download_error for {download_id[:12]}, "
            f"msg={error_msg[:100]!r}"
        )

        if not error_msg or not error_msg.strip():
            print(
                f"⏭️ [Retry] Empty error for {download_id[:12]} — "
                f"letting aria2 retry"
            )
            return

        error_lower = error_msg.lower()
        transient_errors = [
            "timeout",
            "connection",
            "network",
            "temporary",
            "reset by peer",
            "timed out",
            "no route",
            "unreachable",
            "no uri available",
            "name resolution",
            "could not contact dns",
            "dns servers",
            "could not resolve",
            "unable to resolve",
            "resource temporarily",
            "try again",
            "service unavailable",
            "bad gateway",
            "gateway timeout",
            "internal server error",
            "tls packet",
            "error decoding",
            "eof from the server",
            "got eof",
            "ssl/tls handshake failure",
            "handshake failure",
            "error in the pull function",
            "pull function",
        ]

        if not any(t in error_lower for t in transient_errors):
            # Permanent-looking error: still schedule a retry, but let
            # _schedule_retry's _is_retriable_error() decide whether to
            # actually reschedule.
            print(
                f"🔴 [Retry] Permanent error for {download_id[:12]} — "
                f"scheduling retry"
            )
            self._retrying_gids.add(download_id)
            if error_msg:
                data["errorMessage"] = error_msg
            error_count = self._to_int(data.get("error_count", 0))
            self._schedule_retry(download_id, error_count)
            return

        # ── Transient error path ──
        print(
            f"⏭️ [Retry] Transient error for {download_id[:12]} — "
            f"will retry: {error_msg[:60]}"
        )

        aria2_gid = data.get("aria2_gid")

        # If we don't even know the aria2 gid, we can't query status —
        # go straight to scheduling a retry.
        if not aria2_gid or not self.aria2:
            print(
                f"⚠️ [Retry] No aria2_gid for {download_id[:12]} — " f"scheduling retry"
            )
            self._retrying_gids.add(download_id)
            if error_msg:
                data["errorMessage"] = error_msg
            error_count = self._to_int(data.get("error_count", 0))
            self._schedule_retry(download_id, error_count)
            return

        # Query aria2 status to see what it actually thinks.
        status_data = None
        try:
            status_data = self.aria2.get_status(aria2_gid)
        except Exception as e:
            print(f"⚠️ [Retry] Could not check status for {aria2_gid[:12]}: {e}")

        # C1 fix: if the RPC failed (status_data is None) or returned an
        # unexpected status, do NOT silently return — schedule a retry.
        # Previously this fell through to a bare `return`, leaving the
        # download stuck in 'error' forever.
        if not status_data:
            print(
                f"⚠️ [Retry] aria2 status unavailable for "
                f"{aria2_gid[:12]} — scheduling retry"
            )
            self._retrying_gids.add(download_id)
            if error_msg:
                data["errorMessage"] = error_msg
            error_count = self._to_int(data.get("error_count", 0))
            self._schedule_retry(download_id, error_count)
            return

        real_status = status_data.get("status", "")
        print(f"🔍 [Retry] aria2 status for {aria2_gid[:12]}: {real_status}")

        if real_status == "error":
            print(
                f"🔄 [Retry] aria2 gave up — scheduling re-add for "
                f"{download_id[:12]}"
            )
            self._retrying_gids.add(download_id)
            error_count = self._to_int(data.get("error_count", 0))
            self._schedule_retry(download_id, error_count)
            return

        if real_status in ("paused", "stopped", "waiting"):
            try:
                self.aria2.resume(aria2_gid)
                data["status"] = "active"
                print(f"▶️ [Retry] Unpaused {aria2_gid[:12]}")
            except Exception as e:
                print(f"⚠️ [Retry] Resume failed for {aria2_gid[:12]}: {e}")
                # Resume failed: schedule a retry.
                self._retrying_gids.add(download_id)
                if error_msg:
                    data["errorMessage"] = error_msg
                error_count = self._to_int(data.get("error_count", 0))
                self._schedule_retry(download_id, error_count)
            return

        if real_status == "active":
            print(f"⏳ [Retry] aria2 is still active for {aria2_gid[:12]}")
            return

        # Unknown status: schedule a retry.
        print(
            f"⚠️ [Retry] Unknown aria2 status '{real_status}' for "
            f"{aria2_gid[:12]} — scheduling retry"
        )
        self._retrying_gids.add(download_id)
        if error_msg:
            data["errorMessage"] = error_msg
        error_count = self._to_int(data.get("error_count", 0))
        self._schedule_retry(download_id, error_count)

    def _schedule_retry(self, download_id: str, attempt: int) -> None:
        data = self._all_downloads.get(download_id)
        if not data:
            return

        error_msg = data.get("errorMessage", "")

        if not self._is_retriable_error(error_msg):
            print(
                f"⛔ [Retry] Permanent error for {download_id[:12]}: {error_msg[:60]}"
            )
            data["status"] = "error"
            self._retrying_gids.discard(download_id)
            return

        max_tries = self.store.settings.get("max_retry_attempts", 5)
        next_attempt = attempt + 1

        if next_attempt > max_tries:
            print(f"⛔ [Retry] Max tries reached for {download_id[:12]}")
            data["status"] = "error"
            self._retrying_gids.discard(download_id)
            return

        retry_delay = max(1, int(self.store.settings.get("retry_delay", 5)))

        old_timer = self._retry_timers.pop(download_id, None)
        if old_timer:
            old_timer.stop()

        self._retry_state[download_id] = {
            "deadline": time.time() + retry_delay,
            "attempt": next_attempt,
            "max_tries": max_tries,
        }

        data["status"] = "retrying"
        data["downloadSpeed"] = 0
        data["status_detail"] = (
            f"🔄 Retrying in {retry_delay}s... ({next_attempt}/{max_tries})"
        )

        self._pending_status[download_id] = (
            "retrying",
            time.time() + retry_delay + 2.0,
        )

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda d=download_id: self._do_delayed_retry(d))
        timer.start(retry_delay * 1000)
        self._retry_timers[download_id] = timer

        if self._countdown_timer and not self._countdown_timer.isActive():
            self._countdown_timer.start()

        self._refresh_table()
        print(
            f"⏱️ [Retry] Scheduled {download_id[:12]} in {retry_delay}s "
            f"(attempt {next_attempt}/{max_tries})"
        )

    def _do_delayed_retry(self, download_id: str) -> None:
        timer = self._retry_timers.pop(download_id, None)
        if timer:
            timer.stop()

        self._retry_state.pop(download_id, None)

        self._retrying_gids.discard(download_id)

        if download_id not in self._all_downloads:
            return

        self._all_downloads[download_id].pop("status_detail", None)

        print(f"🔄 [Retry] Executing delayed retry for {download_id[:12]}")
        self._retry_single_download(download_id)

    def _maybe_reset_error_counts(self) -> None:
        """Reset a download's failed-attempt counter once it has been
        downloading healthily for `retry_reset_after` seconds.

        "Healthy" means: status is active, no retry is pending, and
        completedLength actually advanced during the window (so a stalled
        or still-connecting download never earns a reset).
        """
        reset_after = self._to_int(self.store.settings.get("retry_reset_after", 60))
        if reset_after <= 0:
            self._healthy_since.clear()
            return

        now = time.time()

        for download_id in list(self._healthy_since):
            if download_id not in self._all_downloads:
                self._healthy_since.pop(download_id, None)

        for download_id, data in self._all_downloads.items():
            if data.get("download_type") == "youtube":
                continue

            if self._to_int(data.get("error_count", 0)) <= 0:
                self._healthy_since.pop(download_id, None)
                continue

            healthy = (
                data.get("status") in ("active", "downloading")
                and download_id not in self._retry_state
                and download_id not in self._retrying_gids
            )
            if not healthy:
                self._healthy_since.pop(download_id, None)
                continue

            completed = self._to_int(data.get("completedLength", 0))
            entry = self._healthy_since.get(download_id)

            if entry is None or completed < entry[1]:
                self._healthy_since[download_id] = (now, completed)
                continue

            since, base_completed = entry
            if now - since < reset_after:
                continue

            if completed > base_completed:
                old_count = self._to_int(data.get("error_count", 0))
                data["error_count"] = 0
                for q in self.store.queues:
                    if download_id in q.downloads_info:
                        q.downloads_info[download_id]["error_count"] = 0
                        break
                self._healthy_since.pop(download_id, None)
                self.store.mark_dirty()
                print(
                    f"✅ [Retry] {download_id[:12]} healthy for {reset_after}s — "
                    f"error_count reset {old_count} -> 0"
                )
            else:
                # Active but no data moved during the whole window: not healthy.
                self._healthy_since[download_id] = (now, completed)

    def _tick_retry_countdown(self) -> None:
        if not self._retry_state:
            if self._countdown_timer:
                self._countdown_timer.stop()
            return

        now = time.time()
        finished = []
        any_change = False

        for download_id, info in list(self._retry_state.items()):
            remaining = int(info["deadline"] - now)
            if remaining <= 0:
                finished.append(download_id)
                continue

            data = self._all_downloads.get(download_id)
            if data:
                new_detail = (
                    f"🔄 Retrying in {remaining}s... "
                    f"({info['attempt']}/{info['max_tries']})"
                )
                if data.get("status_detail") != new_detail:
                    data["status_detail"] = new_detail
                    data["status"] = "retrying"

                    self._pending_status[download_id] = (
                        "retrying",
                        time.time() + 3.0,
                    )
                    any_change = True

        for download_id in finished:
            self._retry_state.pop(download_id, None)

        if any_change:
            self._refresh_table()

    def _get_aria2_status(self, gid: str) -> Optional[Dict]:
        try:
            if hasattr(self, "aria2") and self.aria2:
                return self.aria2.tell_status(gid)
        except Exception as e:
            print(f"⚠️ Could not get aria2 status for {gid}: {e}")
        return None

    def _play_completion_sound(self) -> None:
        """Play sound when download completes"""
        if not self.store.settings.get("sound_enabled", True):
            return

        sound_path = self.store.settings.get("sound_path", "")

        if not sound_path or not os.path.exists(sound_path):

            default_sounds = [
                "/usr/share/sounds/freedesktop/stereo/complete.oga",
                "/usr/share/sounds/freedesktop/stereo/complete.wav",
                "/usr/share/sounds/alsa/Noise.wav",
                "/usr/share/sounds/gnome/default/alerts/glass.ogg",
            ]
            for s in default_sounds:
                if os.path.exists(s):
                    sound_path = s
                    break
            else:
                return

        try:
            from PyQt6.QtMultimedia import QSound

            QSound.play(sound_path)
            print(f"🔊 Playing sound: {sound_path}")
            return
        except ImportError:
            pass

        try:
            import subprocess

            players = [
                ["paplay", sound_path],
                ["aplay", sound_path],
                ["ffplay", "-nodisp", "-autoexit", sound_path],
                ["mpv", "--no-video", sound_path],
            ]
            for player in players:
                try:
                    subprocess.Popen(
                        player, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    print(f"🔊 Playing via {' '.join(player)}")
                    return
                except FileNotFoundError:
                    continue
        except:
            pass

        print(f"⚠️ Could not play sound: {sound_path}")

    def _export_downloads(self):
        """Open export dialog"""
        queues_with_downloads = [q for q in self.store.queues if q.downloads]
        if not queues_with_downloads:
            QMessageBox.information(self, "Export", "No downloads to export.")
            return

        dialog = ExportDialog(queues_with_downloads, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            success, message = self.export_manager.export_downloads(
                data["queue"], data["format"], data["path"], data["include_headers"]
            )

            if success:
                self.tray.showMessage(
                    "FelfelDM",
                    f"✅ {message}",
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
            else:
                QMessageBox.critical(self, "Export Failed", message)
