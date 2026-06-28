# Requires: websocket-client>=1.4.0
"""WebSocket client with SSL pinning and auto-reconnect."""

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
from queue import Queue

import websocket
from PyQt6.QtCore import QObject, pyqtSignal

from core.ssl_utils import create_ssl_context

logger: logging.Logger = logging.getLogger(__name__)


class WebSocketClient(QObject):
    stats_updated = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)

    def __init__(
        self,
        host: str,
        port: int,
        secret: str,
        cert_file: Optional[Path] = None,
        fingerprint: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.host: str = host
        self.port: int = port
        self.secret: str = secret
        self.cert_file: Optional[Path] = cert_file
        self.fingerprint: Optional[str] = fingerprint
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._connected: bool = False
        self._reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 60.0

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("WebSocket client started")

    def stop(self) -> None:
        self._running = False
        if self._ws:
            self._ws.close()
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("WebSocket client stopped")

    def _run(self) -> None:
        while self._running:
            if self.host.startswith("https"):
                ws_url = f"wss://127.0.0.1:{self.port}/jsonrpc"
            else:
                ws_url = f"ws://127.0.0.1:{self.port}/jsonrpc"

            sslopt = {}
            if ws_url.startswith("wss"):
                try:
                    ssl_context = create_ssl_context(
                        cert_file=self.cert_file,
                        fingerprint=self.fingerprint,
                    )
                    sslopt = {"context": ssl_context}
                except Exception as e:
                    logger.error("SSL context failed: %s", e)
                    self.connection_changed.emit(False)
                    time.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)
                    continue

            self._ws = websocket.WebSocketApp(
                ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                subprotocols=["jsonrpc"],
            )

            self._ws.run_forever(sslopt=sslopt, ping_interval=30, ping_timeout=10)

            if not self._running:
                break

            logger.warning("WebSocket disconnected, reconnecting in %.1fs", self._reconnect_delay)
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    def _on_open(self, ws) -> None:
        logger.info("WebSocket connected")
        self._connected = True
        self._reconnect_delay = 1.0
        self.connection_changed.emit(True)
        self._send_request("aria2.subscribe", ["system.multicall"])

    def _on_message(self, ws, message) -> None:
        try:
            data = json.loads(message)
            method = data.get("method")
            if method and method.startswith("aria2.on"):
                params = data.get("params", [])
                if params and len(params) > 0:
                    gid = params[0].get("gid")
                    if gid:
                        event_type = method.replace("aria2.on", "").lower()
                        self.stats_updated.emit({"event": event_type, "gid": gid})
        except Exception as e:
            logger.error("Message error: %s", e)

    def _on_error(self, ws, error) -> None:
        logger.error("WebSocket error: %s", error)
        self._connected = False
        self.connection_changed.emit(False)

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        logger.info("WebSocket closed")
        self._connected = False
        self.connection_changed.emit(False)

    def _send_request(self, method: str, params: List[Any]) -> str:
        if not self._ws or not self._connected:
            return ""

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": [f"token:{self.secret}"] + params,
        }

        try:
            self._ws.send(json.dumps(payload))
            return request_id
        except Exception:
            return ""

    def is_connected(self) -> bool:
        return self._connected
