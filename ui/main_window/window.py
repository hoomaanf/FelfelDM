"""MainWindow: composes the mixins and owns construction and the by-name Qt slots."""

import time
from typing import Any, Dict, List, Optional, Set

from PyQt6.QtCore import QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QApplication, QDialog, QMainWindow, QMessageBox

from core import (
    Aria2RPC,
    BackendWorker,
    DataStore,
    QueueOperationWorker,
    ScheduleManagerThread,
)
from core.local_server import LocalServer
from core.proxy_manager import ProxyManager
from ui.dialogs import DownloadProgressDialog
from ui.export_manager import ExportManager
from ui.splash import SplashScreen
from ui.widgets import DropOverlay
from ui.youtube_progress import YouTubeProgressDialog
from utils.helpers import is_ytdlp_supported
from ui.main_window.ui_builders import UIBuilderMixin
from ui.main_window.details_panel import DetailsPanelMixin
from ui.main_window.table_view import TableViewMixin
from ui.main_window.status_display import StatusDisplayMixin
from ui.main_window.stats_sync import StatsSyncMixin
from ui.main_window.aria2_control import Aria2ControlMixin
from ui.main_window.queues import QueuesMixin
from ui.main_window.add_download import AddDownloadMixin
from ui.main_window.youtube import YouTubeMixin
from ui.main_window.progress_dialogs import ProgressDialogsMixin
from ui.main_window.download_actions import DownloadActionsMixin
from ui.main_window.retry import RetryMixin
from ui.main_window.removal import RemovalMixin
from ui.main_window.file_actions import FileActionsMixin
from ui.main_window.settings_dialogs import SettingsDialogsMixin
from ui.main_window.shutdown import ShutdownMixin
from ui.main_window.lifecycle import LifecycleMixin


class MainWindow(
    UIBuilderMixin,
    DetailsPanelMixin,
    TableViewMixin,
    StatusDisplayMixin,
    StatsSyncMixin,
    Aria2ControlMixin,
    QueuesMixin,
    AddDownloadMixin,
    YouTubeMixin,
    ProgressDialogsMixin,
    DownloadActionsMixin,
    RetryMixin,
    RemovalMixin,
    FileActionsMixin,
    SettingsDialogsMixin,
    ShutdownMixin,
    LifecycleMixin,
    QMainWindow,
):
    """Main application window.

    The behaviour lives in the mixins (one module per responsibility). Qt slots
    invoked by name (QMetaObject.invokeMethod) must be defined on the QObject
    subclass itself, so they stay here.
    """

    _aria2_error_signal = pyqtSignal(str)

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

    @pyqtSlot()
    def _delayed_ui_update(self) -> None:
        self._refresh_table()
        self._update_queue_status()
        self._update_queue_buttons()

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

    @pyqtSlot(str, str)
    def _open_dialog_from_extension(self, url: str, kind: str = "") -> None:
        if not url:
            return

        lower = url.lower()
        if lower.startswith("magnet:") or lower.endswith(".torrent"):
            QMessageBox.warning(
                self,
                "Not Supported",
                "BitTorrent downloads are not supported in this version.",
            )
            return

        if kind == "youtube":
            self._open_youtube_dialog_with_url(url)
            return

        try:
            from urllib.parse import urlparse

            host = urlparse(url).hostname or ""
            host = host.lower()
            if (
                host == "youtu.be"
                or host.endswith(".youtube.com")
                or host == "youtube.com"
                or host.endswith(".youtube-nocookie.com")
                or host == "music.youtube.com"
            ):
                self._open_youtube_dialog_with_url(url)
                return
        except Exception:
            pass

        if is_ytdlp_supported(url):
            self._open_youtube_dialog_with_url(url)
            return

        self._open_or_update_add_dialog([url])
