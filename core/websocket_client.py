# core/websocket_client.py
"""
WebSocket client for real-time updates from aria2 with auto-reconnect
and SSL pinning. No insecure fallback.
"""

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
from queue import Queue, Empty

import websocket
from PyQt6.QtCore import QObject, pyqtSignal

from core.ssl_utils import create_ssl_context

logger: logging.Logger = logging.getLogger(__name__)


class WebSocketClient(QObject):
    """
    WebSocket client that connects to aria2's WebSocket endpoint and listens for events.
    Runs in a separate thread. Implements auto-reconnect with exponential backoff
    and SSL pinning. No insecure fallback.
    """

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
        self._message_queue: Queue = Queue()
        self._connected: bool = False
        self._callbacks: Dict[str, Callable] = {}
        self._reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 60.0

    def start(self) -> None:
        """Start the WebSocket connection in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("WebSocket client started.")

    def stop(self) -> None:
        """Stop the WebSocket client."""
        self._running = False
        if self._ws:
            self._ws.close()
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("WebSocket client stopped.")

    def _run(self) -> None:
        """Main loop with auto-reconnect."""
        while self._running:
            # Build WebSocket URL
            if self.host.startswith("https"):
                ws_url = f"wss://127.0.0.1:{self.port}/jsonrpc"
            else:
                ws_url = f"ws://127.0.0.1:{self.port}/jsonrpc"

            # Create SSL context with pinning - MUST succeed for wss
            if ws_url.startswith("wss"):
                try:
                    ssl_context = create_ssl_context(
                        cert_file=self.cert_file,
                        fingerprint=self.fingerprint,
                    )
                    sslopt = {"context": ssl_context}
                except Exception as e:
                    logger.error("Failed to create SSL context for WebSocket: %s", e)
                    # No insecure fallback - raise the exception
                    raise RuntimeError(f"WebSocket SSL setup failed: {e}") from e
            else:
                sslopt = {}

            self._ws = websocket.WebSocketApp(
                ws_url,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
                subprotocols=["jsonrpc"],
            )

            try:
                self._ws.run_forever(
                    sslopt=sslopt,
                    ping_interval=30,
                    ping_timeout=10,
                )
            except Exception as e:
                logger.error("WebSocket run_forever error: %s", e)

            if not self._running:
                break

            # Reconnect with backoff
            logger.warning("WebSocket disconnected, reconnecting in %.1f seconds", self._reconnect_delay)
            time.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_reconnect_delay)

    def _on_open(self, ws) -> None:
        """Callback on WebSocket open."""
        logger.info("WebSocket connected to aria2.")
        self._connected = True
        self._reconnect_delay = 1.0  # Reset backoff on successful connection
        self.connection_changed.emit(True)

    def _on_message(self, ws, message: str) -> None:
        """Callback on WebSocket message."""
        try:
            data = json.loads(message)
            # Forward to main thread via signal
            self.stats_updated.emit(data)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse WebSocket message: %s", e)

    def _on_error(self, ws, error) -> None:
        """Callback on WebSocket error."""
        logger.error("WebSocket error: %s", error)

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        """Callback on WebSocket close."""
        logger.info("WebSocket closed: %s - %s", close_status_code, close_msg)
        self._connected = False
        self.connection_changed.emit(False)

    def is_connected(self) -> bool:
        return self._connected

    def send_message(self, message: Dict[str, Any]) -> None:
        """Send a message over WebSocket."""
        if not self._ws or not self._connected:
            logger.warning("Cannot send message: WebSocket not connected")
            return
        try:
            self._ws.send(json.dumps(message))
        except Exception as e:
            logger.error("Failed to send WebSocket message: %s", e)
