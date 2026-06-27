# Requires: PyQt6>=6.4.0

"""
Background worker for WebSocket client, status updates, health monitoring,
and dynamic segmentation using max-connection-per-server.
"""

import logging
from typing import Optional, Dict, Any, List
from PyQt6.QtCore import QThread, pyqtSignal, QTimer

from core.aria2_rpc import Aria2RPC
from core.data_store import DataStore
from core.websocket_client import WebSocketClient
from core.session_manager import SessionManager
from core.monitor import Aria2Monitor

logger: logging.Logger = logging.getLogger(__name__)


class BackendWorker(QThread):
    """
    Worker thread that manages WebSocket connection, periodic status updates,
    health monitoring, and dynamic segmentation.
    """

    stats_updated = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)

    def __init__(
        self,
        aria2: Aria2RPC,
        store: DataStore,
        session_mgr: SessionManager,
        aria2_manager: 'Aria2Manager',
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
        self.poll_interval = self.store.settings.get("poll_interval", 5000)  # Reduced to 5s
        self._adjust_connections_timer: Optional[QTimer] = None
        self._is_reconnecting = False
        # Track average speed per GID for dynamic adjustment
        self._speed_history: Dict[str, List[int]] = {}

    def run(self) -> None:
        logger.info("BackendWorker started")
        # Initialize WebSocket client
        host = self.store.settings.get("aria2_host", "https://127.0.0.1")
        port = self.store.settings.get("aria2_port", 6800)
        secret = self.store.get_aria2_secret()
        cert_file = self.aria2_manager.get_certificate_path()
        fingerprint = self.aria2_manager.get_certificate_fingerprint()

        # self._ws_client = WebSocketClient(
        #     host, port, secret,
        #     cert_file=cert_file,
        #     fingerprint=fingerprint,
        # )
        #self._ws_client.connection_changed.connect(self._on_ws_connection_changed)
        # self._ws_client.start()

        # Health monitor
        self._monitor = Aria2Monitor(self.aria2, self.store, self.session_mgr, self.aria2_manager)
        self._monitor.start()

        # Timer for periodic status fetch (fallback, reduced frequency)
        self._poll_timer = QTimer()
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(self.poll_interval)

        # Timer for dynamic connection adjustment (every 3 seconds)
        self._adjust_connections_timer = QTimer()
        self._adjust_connections_timer.timeout.connect(self._adjust_connections)
        self._adjust_connections_timer.start(3000)

        self.exec()

        # Cleanup
        if self._ws_client:
            self._ws_client.stop()
            self._ws_client = None
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None
        if self._adjust_connections_timer:
            self._adjust_connections_timer.stop()
            self._adjust_connections_timer = None
        if self._monitor:
            self._monitor.stop()
        logger.info("BackendWorker stopped")

    def _on_ws_connection_changed(self, connected: bool) -> None:
        self.connection_changed.emit(connected)

    def _poll(self) -> None:
        if not self.running:
            return
        try:
            # Use multicall to reduce requests
            calls = [
                {"methodName": "aria2.tellActive", "params": []},
                {"methodName": "aria2.tellWaiting", "params": [0, 1000]},
                {"methodName": "aria2.tellStopped", "params": [0, 1000]},
                {"methodName": "aria2.getGlobalStat", "params": []},
            ]
            results = self.aria2.multicall(calls)
            if results and len(results) == 4:
                active = results[0][0] if results[0] else []
                waiting = results[1][0] if results[1] else []
                stopped = results[2][0] if results[2] else []
                stat = results[3][0] if results[3] else {}

                self.stats_updated.emit({
                    "connected": True,
                    "stat": stat,
                    "active": active,
                    "waiting": waiting,
                    "stopped": stopped,
                })
        except Exception as e:
            logger.error("Poll error: %s", e)

    def _adjust_connections(self) -> None:
        """Dynamically adjust max-connection-per-server based on download speed."""
        if not self.running:
            return
        try:
            active = self.aria2.tell_active()
            for dl in active:
                gid = dl.get("gid")
                if not gid:
                    continue
                speed = int(dl.get("downloadSpeed", 0))
                current_connections = int(dl.get("connections", 0))
                total_length = int(dl.get("totalLength", 0))
                completed_length = int(dl.get("completedLength", 0))

                # Skip if download is complete or near completion
                if total_length > 0 and (total_length - completed_length) < 1024 * 1024:
                    continue

                # Update speed history
                if gid not in self._speed_history:
                    self._speed_history[gid] = []
                self._speed_history[gid].append(speed)
                if len(self._speed_history[gid]) > 10:
                    self._speed_history[gid].pop(0)
                avg_speed = sum(self._speed_history[gid]) / len(self._speed_history[gid])

                # Dynamic adjustment based on average speed
                # Target: use more connections if speed is high, fewer if low
                if avg_speed < 50 * 1024 and current_connections > 4:
                    new_connections = max(4, current_connections - 2)
                elif avg_speed > 500 * 1024 and current_connections < 16:
                    new_connections = min(16, current_connections + 2)
                else:
                    continue

                if new_connections != current_connections:
                    logger.debug(
                        "Adjusting connections for %s: %d -> %d (avg speed: %.1f KB/s)",
                        gid, current_connections, new_connections, avg_speed / 1024
                    )
                    self.aria2.change_option(
                        gid,
                        {"max-connection-per-server": str(new_connections)}
                    )

        except Exception as e:
            logger.error("Error in dynamic segmentation: %s", e)

    def stop(self) -> None:
        self.running = False
        if self._poll_timer:
            self._poll_timer.stop()
            self._poll_timer = None
        if self._adjust_connections_timer:
            self._adjust_connections_timer.stop()
            self._adjust_connections_timer = None
        if self._ws_client:
            self._ws_client.stop()
            self._ws_client = None
        if self._monitor:
            self._monitor.stop()
        self.quit()
        self.wait()
        logger.info("BackendWorker stop requested")
