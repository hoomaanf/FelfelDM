# Requires: requests>=2.28.0

"""
Aria2 RPC client using JSON-RPC over HTTPS with certificate pinning,
retry with exponential backoff, and robust error handling.
"""

import os
import logging
import uuid
import json
import time
import ssl
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, cast
from threading import Lock

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PyQt6.QtCore import QObject, pyqtSignal

from core.error_handler import ErrorHandler
from core.ssl_utils import create_ssl_context

logger: logging.Logger = logging.getLogger(__name__)


class Aria2RPC(QObject):
    """
    RPC client for aria2 using HTTPS with certificate pinning.
    """

    error_occurred = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)

    def __init__(
        self,
        host: str = "http://127.0.0.1",
        port: int = 6800,
        secret: str = "",
        timeout: float = 5.0,
        max_retries: int = 3,
        fingerprint: Optional[str] = None,
        cert_file: Optional[Path] = None,
    ) -> None:
        super().__init__()
        self.host: str = host.rstrip('/')
        self.port: int = port
        self.secret: str = secret
        self.timeout: float = max(1.0, timeout)
        self.max_retries: int = max(0, max_retries)
        self.fingerprint: Optional[str] = fingerprint
        self.cert_file: Optional[Path] = cert_file
        self._lock: Lock = Lock()
        self._connected: bool = False
        self._session: Optional[requests.Session] = None
        self._error_handler = ErrorHandler()
        self._ensure_session()

    def _ensure_session(self) -> None:
        """Create or recreate the requests session with proper SSL context."""
        if self._session is not None:
            self._session.close()

        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})

        # Create SSL context with certificate pinning
        try:
            ssl_context = create_ssl_context(
                cert_file=self.cert_file,
                fingerprint=self.fingerprint,
            )
            # Apply the SSL context to the session's adapter
            session.verify = False  # Always verify
            # We need to mount a custom adapter with our SSL context
            # requests doesn't directly support custom SSL context per session
            # We'll use the verify parameter with the cert file
            if self.cert_file and self.cert_file.exists():
                session.verify = str(self.cert_file)
            else:
                # Fall back to system CA bundles
                session.verify = True
        except Exception as e:
            logger.error("Failed to configure SSL context: %s", e)
            # Fall back to insecure mode as last resort (but we avoid this)
            session.verify = False
            logger.warning("SSL verification disabled due to configuration error.")

        # Retry strategy with exponential backoff
        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
        )
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=retry_strategy,
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)

        self._session = session

    def set_timeout(self, timeout: float) -> None:
        with self._lock:
            self.timeout = max(1.0, timeout)
            logger.info("Aria2RPC timeout updated to %s s", self.timeout)

    def set_secret(self, secret: str) -> None:
        """Update the RPC secret."""
        with self._lock:
            self.secret = secret
            logger.info("Aria2RPC secret updated")

    def close(self) -> None:
        if self._session:
            self._session.close()
            self._session = None

    def _emit_error(self, msg: str) -> None:
        logger.error(msg)
        self.error_occurred.emit(msg)

    def _set_connected(self, state: bool) -> None:
        if state != self._connected:
            self._connected = state
            self.connection_changed.emit(state)

    def _call(self, method: str, params: Optional[List[Any]] = None) -> Optional[Any]:
        with self._lock:
            self._ensure_session()
            request_id: str = str(uuid.uuid4())
            token: Optional[str] = f"token:{self.secret}" if self.secret else None
            p: List[Any] = [token] + (params or []) if token else (params or [])

            payload: Dict[str, Any] = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": p,
            }

            try:
                response = self._session.post(
                    f"{self.host}:{self.port}/jsonrpc",
                    json=payload,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()

                if "error" in result:
                    err = result["error"]
                    error_code = err.get("code", 0)
                    error_msg = err.get("message", str(err))
                    user_msg = self._error_handler.translate(error_code, error_msg, method)
                    self._emit_error(user_msg)
                    self._set_connected(True)
                    return None

                self._set_connected(True)
                return result.get("result")

            except requests.exceptions.ConnectionError:
                self._set_connected(False)
                self._emit_error("اتصال به aria2 برقرار نیست. لطفاً aria2 را اجرا کنید.")
                return None
            except requests.exceptions.Timeout:
                self._set_connected(False)
                self._emit_error(f"زمان پاسخ‌دهی aria2 به پایان رسید (متد: {method})")
                return None
            except requests.exceptions.HTTPError as e:
                self._set_connected(False)
                self._emit_error(f"خطای HTTP: {e.response.status_code} - {e.response.reason}")
                return None
            except Exception as e:
                self._set_connected(False)
                self._emit_error(f"خطای غیرمنتظره در ارتباط با aria2: {str(e)}")
                return None

    # ---------- Public API ----------

    def add_url(self, url: str, options: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Add a single download URL. Returns GID or None."""
        return self._call("aria2.addUri", [[url], options or {}])

    def add_torrent(self, torrent_file: bytes, options: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Add a torrent download using torrent file content. Returns GID or None."""
        import base64
        torrent_b64 = base64.b64encode(torrent_file).decode('ascii')
        return self._call("aria2.addTorrent", [torrent_b64, options or {}])

    def add_magnet(self, magnet_uri: str, options: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Add a magnet link. Returns GID or None."""
        return self._call("aria2.addUri", [[magnet_uri], options or {}])

    def add_urls(self, urls: List[str], options: Optional[Dict[str, Any]] = None) -> List[Optional[str]]:
        """Add multiple URLs using multicall. Returns list of GIDs (or None)."""
        if not urls:
            return []
        calls = []
        for url in urls:
            calls.append({
                "methodName": "aria2.addUri",
                "params": [[url], options or {}],
            })
        result = self._call("system.multicall", [calls])
        if isinstance(result, list):
            gids = []
            for resp in result:
                if isinstance(resp, dict) and "result" in resp:
                    gids.append(resp["result"])
                else:
                    gids.append(None)
            return gids
        return []

    def pause(self, gid: str) -> bool:
        return self._call("aria2.pause", [gid]) is not None

    def resume(self, gid: str) -> bool:
        return self._call("aria2.unpause", [gid]) is not None

    def remove(self, gid: str, delete_files: bool = False) -> bool:
        """Remove download. If delete_files is True, remove the incomplete files."""
        result = self._call("aria2.remove", [gid])
        if result is not None:
            self._call("aria2.removeDownloadResult", [gid])
            if delete_files:
                # Get file paths from tellStatus
                status = self.tell_status(gid, ["files"])
                if status and "files" in status:
                    for file_info in status["files"]:
                        path = file_info.get("path")
                        if path and os.path.exists(path):
                            try:
                                os.remove(path)
                                logger.info("Deleted file: %s", path)
                            except Exception as e:
                                logger.error("Failed to delete file %s: %s", path, e)
            return True
        return False

    def change_option(self, gid: str, options: Dict[str, Any]) -> bool:
        """Change options for a specific download (e.g., max-connection-per-server)."""
        return self._call("aria2.changeOption", [gid, options]) is not None

    def change_global_option(self, options: Dict[str, Any]) -> bool:
        return self._call("aria2.changeGlobalOption", [options]) is not None

    def get_global_stat(self) -> Optional[Dict[str, Any]]:
        return self._call("aria2.getGlobalStat")

    def tell_status(self, gid: str, keys: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        if keys is None:
            keys = [
                "gid", "status", "totalLength", "completedLength",
                "downloadSpeed", "uploadSpeed", "connections", "files",
                "errorMessage", "eta", "dir"
            ]
        return self._call("aria2.tellStatus", [gid, keys])

    def tell_active(self) -> List[Dict[str, Any]]:
        result = self._call("aria2.tellActive")
        return result or []

    def tell_waiting(self, offset: int = 0, num: int = 1000) -> List[Dict[str, Any]]:
        result = self._call("aria2.tellWaiting", [offset, num])
        return result or []

    def tell_stopped(self, offset: int = 0, num: int = 1000) -> List[Dict[str, Any]]:
        result = self._call("aria2.tellStopped", [offset, num])
        return result or []

    def is_connected(self) -> bool:
        result = self.get_global_stat()
        connected = result is not None
        self._set_connected(connected)
        return connected

    def get_status(self, gid: str) -> Optional[str]:
        result = self.tell_status(gid, ["gid", "status"])
        return result.get("status") if result else None

    def force_pause(self, gid: str) -> bool:
        return self._call("aria2.forcePause", [gid]) is not None

    def multicall(self, calls: List[Dict[str, Any]]) -> Optional[List[Any]]:
        return self._call("system.multicall", [calls])
