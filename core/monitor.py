# core/monitor.py
"""
Aria2 health monitor: periodically checks and restarts if necessary.
"""

import logging
import threading
import time
from typing import Optional, List, Dict, Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from core.aria2_rpc import Aria2RPC
from core.aria2_manager import Aria2Manager
from core.data_store import DataStore
from core.session_manager import SessionManager

logger: logging.Logger = logging.getLogger(__name__)


class Aria2Monitor(QObject):
    """
    Monitors aria2 health and restarts it if it becomes unresponsive.
    Uses dependency injection for Aria2Manager to ensure consistency.
    """

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

    def start(self) -> None:
        """Start monitoring."""
        if self._running:
            return
        self._running = True
        self._timer = QTimer()
        self._timer.timeout.connect(self._check_health)
        self._timer.start(5000)  # Check every 5 seconds
        logger.info("Aria2Monitor started")

    def stop(self) -> None:
        """Stop monitoring."""
        self._running = False
        if self._timer:
            self._timer.stop()
            self._timer = None
        logger.info("Aria2Monitor stopped")

    def _check_health(self) -> None:
        """Check aria2 health and restart if needed."""
        if not self._running:
            return

        try:
            stat = self.aria2.get_global_stat()
            if stat is None:
                raise Exception("No response from aria2")
            # Health check passed
            self.connection_changed.emit(True)
        except Exception as e:
            logger.error("Aria2 health check failed: %s. Attempting restart...", e)
            self.connection_changed.emit(False)

            # Restart aria2 using the same manager instance
            if self.aria2_manager.restart():
                logger.info("Aria2 restarted successfully. Resuming active downloads.")

                # Update RPC client with new secret
                new_secret = self.aria2_manager.get_secret()
                self.aria2.set_secret(new_secret)

                # Ensure the session is recreated with new settings
                self.aria2._ensure_session()

                # Resume all active GIDs from session using batch call
                gids = self.session_mgr.load_gids()
                if gids:
                    # Build batch calls for each GID
                    batch_calls = []
                    for gid in gids:
                        batch_calls.append({
                            "method": "aria2.tellStatus",
                            "params": [gid, ["gid"]],  # just check existence
                        })
                    # Execute batch
                    results = self.aria2.batch_call(batch_calls)
                    for gid, result in zip(gids, results):
                        if result and result.get("gid"):
                            self.aria2.resume(gid)
                        else:
                            logger.warning("GID %s not found, skipping resume", gid)
            else:
                logger.critical("Failed to restart aria2. Manual intervention may be required.")
