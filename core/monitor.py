"""Aria2 health monitor with auto-recovery and sleep/wake detection."""

import logging
import time
from typing import Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.aria2_rpc import Aria2RPC
from core.aria2_manager import Aria2Manager
from core.data_store import DataStore
from core.session_manager import SessionManager
from core.error_handler import ErrorHandler

logger: logging.Logger = logging.getLogger(__name__)


class Aria2Monitor(QObject):
    connection_changed = pyqtSignal(bool)

    def __init__(
        self,
        aria2: Aria2RPC,
        store: DataStore,
        session_mgr: SessionManager,
        aria2_manager: Aria2Manager,
    ) -> None:
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.session_mgr = session_mgr
        self.aria2_manager = aria2_manager
        self._timer: Optional[QTimer] = None
        self._running = False
        self._error_handler = ErrorHandler()
        self._failure_count = 0
        self._max_failures = 3
        self._last_restart_time = 0
        self._restart_cooldown = 30
        self._was_sleeping = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._timer = QTimer()
        self._timer.timeout.connect(self._check_health)
        self._timer.start(5000)
        logger.info("Aria2Monitor started")

    def stop(self) -> None:
        self._running = False
        if self._timer:
            self._timer.stop()
            self._timer = None
        logger.info("Aria2Monitor stopped")

    def _check_health(self) -> None:
        if not self._running:
            return
        try:
            stat = self.aria2.get_global_stat()
            if stat is None:
                raise Exception("No response from aria2")
            self._failure_count = 0
            self.connection_changed.emit(True)
        except Exception as e:
            logger.error("Aria2 health check failed: %s", e)
            self._failure_count += 1
            self.connection_changed.emit(False)

            # Auto-recovery for retryable errors
            error_code = self._extract_error_code(e)
            if error_code is not None:
                recovery_action = self._error_handler.get_recovery_action(
                    error_code, {"context": "health_check"}
                )
                if recovery_action.get("retry"):
                    logger.info("Auto-recovery: %s", recovery_action.get("message"))
                    return

            now = time.time()
            if now - self._last_restart_time < self._restart_cooldown:
                logger.warning("Restart cooldown active, waiting...")
                return

            if self._failure_count >= self._max_failures:
                logger.warning("Too many failures (%d), attempting restart...", self._failure_count)
                self._attempt_restart()
                self._failure_count = 0

    def _extract_error_code(self, exception: Exception) -> Optional[int]:
        error_str = str(exception)
        for code in [3, 10, 14, 17, 20, 22]:
            if str(code) in error_str:
                return code
        return None

    def _attempt_restart(self) -> None:
        self._last_restart_time = time.time()
        if self.aria2_manager.restart():
            logger.info("Aria2 restarted successfully.")
            new_secret = self.aria2_manager.get_secret()
            self.aria2.set_secret(new_secret)
            new_fingerprint = self.aria2_manager.get_certificate_fingerprint()
            if new_fingerprint:
                self.aria2.fingerprint = new_fingerprint
            self.aria2.cert_file = self.aria2_manager.get_certificate_path()
            self.aria2._ensure_session()

            gids = self.session_mgr.load_session()
            if gids:
                logger.info("Resuming %d downloads after restart", len(gids))
                for gid in gids:
                    try:
                        status = self.aria2.tell_status(gid, ["gid"])
                        if status and status.get("gid"):
                            self.aria2.unpause(gid)
                    except Exception as e:
                        logger.warning("Failed to resume GID %s: %s", gid, e)
            self.connection_changed.emit(True)
        else:
            logger.critical("Failed to restart aria2.")

    def on_system_sleep(self) -> None:
        self._was_sleeping = True
        logger.info("System entering sleep mode")

    def on_system_wake(self) -> None:
        logger.info("System waking from sleep mode")
        if self._was_sleeping:
            self._was_sleeping = False
            self._check_health()
            self._refresh_session_after_wake()

    def _refresh_session_after_wake(self) -> None:
        try:
            gids = self.session_mgr.load_session()
            if gids:
                logger.info("Refreshing %d downloads after wake", len(gids))
                for gid in gids:
                    status = self.aria2.tell_status(gid, ["gid", "status"])
                    if status and status.get("status") == "paused":
                        self.aria2.unpause(gid)
        except Exception as e:
            logger.error("Failed to refresh session after wake: %s", e)
