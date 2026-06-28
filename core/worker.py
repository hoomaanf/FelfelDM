# Requires: PyQt6>=6.4.0
"""Background worker with WebSocket, polling fallback, and dynamic connections."""

import logging
import time
from typing import Optional, Dict, Any, List

from PyQt6.QtCore import QThread, pyqtSignal, QTimer

from core.aria2_rpc import Aria2RPC
from core.data_store import DataStore
from core.websocket_client import WebSocketClient
from core.session_manager import SessionManager
from core.monitor import Aria2Monitor

logger: logging.Logger = logging.getLogger(__name__)


class BackendWorker(QThread):
    stats_updated = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)

    def __init__(
        self,
        aria2: Aria2RPC,
        store: DataStore,
        session_mgr: SessionManager,
        aria2_manager: "Aria2Manager",
    ) -> None:
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.session_mgr = session_mgr
        self.aria2_manager = aria2_manager
        self.running = True
        self._poll_timer: Optional[QTimer] = None
        self._ws_client: Optional[WebSocketClient] = None
        self._monitor: Optional[Aria2Monitor] = None
        self.poll_interval = self.store.settings.get("poll_interval", 10000)
        self._adjust_connections_timer: Optional[QTimer] = None
        self._speed_history: Dict[str, List[int]] = {}
        self._last_poll_time = 0

    def run(self) -> None:
        logger.info("BackendWorker started")

        host = self.store.settings.get("aria2_host", "https://127.0.0.1")
        port = self.store.settings.get("aria2_port", 6800)
        secret = self.store.get_aria2_secret()
        cert_file = self.aria2_manager.get_certificate_path()
        fingerprint = self.aria2_manager.get_certificate_fingerprint()

        self._ws_client = WebSocketClient(host, port, secret, cert_file, fingerprint)
        self._ws_client.connection_changed.connect(self._on_ws_connection_changed)
        self._ws_client.stats_updated.connect(self._on_ws_stats_updated)
        self._ws_client.start()

        self._monitor = Aria2Monitor(self.aria2, self.store, self.session_mgr, self.aria2_manager)
        self._monitor.start()

        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(self.poll_interval)

        self._adjust_connections_timer = QTimer()
        self._adjust_connections_timer.timeout.connect(self._adjust_connections)
        self._adjust_connections_timer.start(5000)

        self.exec()

        if self._ws_client:
            self._ws_client.stop()
        if self._poll_timer:
            self._poll_timer.stop()
        if self._adjust_connections_timer:
            self._adjust_connections_timer.stop()
        if self._monitor:
            self._monitor.stop()

        logger.info("BackendWorker stopped")

    def _on_ws_connection_changed(self, connected: bool) -> None:
        self.connection_changed.emit(connected)
        if connected:
            logger.info("WebSocket connected - real-time updates active")
        else:
            logger.warning("WebSocket disconnected - falling back to polling")

    def _on_ws_stats_updated(self, data: Dict[str, Any]) -> None:
        self.stats_updated.emit(data)

    def _poll(self) -> None:
        if not self.running:
            return

        if self._ws_client and self._ws_client.is_connected():
            now = time.time()
            if now - self._last_poll_time < 30:
                return
            self._last_poll_time = now

        try:
            active = self.aria2.get_active_downloads()
            if active is not None:
                self.stats_updated.emit({"active": active, "source": "poll"})

            stat = self.aria2.get_global_stat()
            if stat is not None:
                self.stats_updated.emit({"global_stat": stat, "source": "poll"})

        except Exception as e:
            logger.error("Poll error: %s", e)

    def _adjust_connections(self) -> None:
        if not self.running:
            return

        try:
            active = self.aria2.get_active_downloads()
            if not active:
                return

            for download in active:
                gid = download.get("gid")
                if not gid:
                    continue

                speed = download.get("downloadSpeed", 0)
                if speed == 0:
                    continue

                if gid not in self._speed_history:
                    self._speed_history[gid] = []
                self._speed_history[gid].append(speed)

                if len(self._speed_history[gid]) > 10:
                    self._speed_history[gid] = self._speed_history[gid][-10:]

                avg_speed = sum(self._speed_history[gid]) / len(self._speed_history[gid])
                if avg_speed < 1024 * 50:
                    opts = self.aria2.get_options(gid)
                    if opts:
                        current = int(opts.get("max-connection-per-server", 1))
                        if current < 16:
                            new_val = min(current + 1, 16)
                            self.aria2.change_option(gid, {"max-connection-per-server": str(new_val)})
                            logger.debug("Increased connections for %s to %d", gid, new_val)

        except Exception as e:
            logger.debug("Connection adjustment error: %s", e)

    def stop(self) -> None:
        self.running = False
        if self._ws_client:
            self._ws_client.stop()
        if self._poll_timer:
            self._poll_timer.stop()
        if self._adjust_connections_timer:
            self._adjust_connections_timer.stop()
        if self._monitor:
            self._monitor.stop()
        self.quit()
        self.wait()
