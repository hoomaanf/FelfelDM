# Requires: requests>=2.28.0
"""Aria2 RPC client with certificate pinning and batch operations."""

import logging
import uuid
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from threading import Lock

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PyQt6.QtCore import QObject, pyqtSignal

from core.error_handler import ErrorHandler
from core.ssl_utils import create_ssl_context

logger: logging.Logger = logging.getLogger(__name__)


class Aria2RPC(QObject):
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
        self.host: str = host.rstrip("/")
        self.port: int = port
        self.secret: str = secret
        self.timeout: float = max(1.0, timeout)
        self.max_retries: int = max(0, max_retries)
        self.fingerprint: Optional[str] = fingerprint
        self.cert_file: Optional[Path] = cert_file
        self._lock: Lock = Lock()
        self._session: Optional[requests.Session] = None
        self._error_handler = ErrorHandler()
        self._ensure_session()

    def _ensure_session(self) -> None:
        if self._session is not None:
            self._session.close()

        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})

        if not self.cert_file or not self.cert_file.exists():
            raise RuntimeError("Certificate file is required for secure communication.")

        try:
            ssl_context = create_ssl_context(
                cert_file=self.cert_file,
                fingerprint=self.fingerprint,
            )
            session.verify = str(self.cert_file)
        except Exception as e:
            logger.error("Failed to configure SSL context: %s", e)
            raise RuntimeError(f"SSL configuration failed: {e}")

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
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        self._session = session

    def set_secret(self, secret: str) -> None:
        with self._lock:
            self.secret = secret
        logger.info("Aria2RPC secret updated")

    def close(self) -> None:
        if self._session:
            self._session.close()
            self._session = None

    def _emit_error(self, error_msg: str) -> None:
        self.error_occurred.emit(error_msg)

    def _request(self, method: str, params: List[Any]) -> Optional[Dict[str, Any]]:
        if self._session is None:
            self._ensure_session()

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": [f"token:{self.secret}"] + params,
        }

        url = f"{self.host}:{self.port}/jsonrpc"

        try:
            response = self._session.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                error_code = data["error"].get("code", -1)
                error_msg = data["error"].get("message", "Unknown error")
                friendly_msg = self._error_handler.translate(error_code, error_msg, method)
                self._emit_error(friendly_msg)
                return None
            return data.get("result")

        except requests.exceptions.SSLError as e:
            logger.error("SSL error: %s", e)
            self._emit_error(f"SSL error: {e}")
            self.connection_changed.emit(False)
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error("Connection error: %s", e)
            self.connection_changed.emit(False)
            return None
        except Exception as e:
            logger.error("Unexpected error: %s", e)
            return None

    def _batch_request(self, calls: List[Dict[str, Any]]) -> Optional[List[Any]]:
        if self._session is None:
            self._ensure_session()

        multicall_params = []
        for call in calls:
            method = call.get("methodName")
            params = call.get("params", [])
            multicall_params.append({
                "methodName": method,
                "params": [f"token:{self.secret}"] + params,
            })

        request_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "system.multicall",
            "params": multicall_params,
        }

        url = f"{self.host}:{self.port}/jsonrpc"

        try:
            response = self._session.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                error_code = data["error"].get("code", -1)
                error_msg = data["error"].get("message", "Unknown error")
                friendly_msg = self._error_handler.translate(error_code, error_msg, "system.multicall")
                self._emit_error(friendly_msg)
                return None
            return data.get("result", [])
        except Exception as e:
            logger.error("Batch request error: %s", e)
            return None

    # --- Core methods ---
    def add_url(self, urls: List[str], options: Optional[Dict[str, Any]] = None, position: Optional[int] = None) -> Optional[str]:
        params: List[Any] = [urls]
        if options:
            params.append(options)
        if position is not None:
            params.append(position)
        result = self._request("aria2.addUrl", params)
        return result if isinstance(result, str) else None

    def remove(self, gid: str) -> Optional[str]:
        result = self._request("aria2.remove", [gid])
        return result if isinstance(result, str) else None

    def force_remove(self, gid: str) -> Optional[str]:
        result = self._request("aria2.forceRemove", [gid])
        return result if isinstance(result, str) else None

    def pause(self, gid: str) -> Optional[str]:
        result = self._request("aria2.pause", [gid])
        return result if isinstance(result, str) else None

    def pause_all(self) -> Optional[str]:
        result = self._request("aria2.pauseAll", [])
        return result if isinstance(result, str) else None

    def unpause(self, gid: str) -> Optional[str]:
        result = self._request("aria2.unpause", [gid])
        return result if isinstance(result, str) else None

    def unpause_all(self) -> Optional[str]:
        result = self._request("aria2.unpauseAll", [])
        return result if isinstance(result, str) else None

    def tell_status(self, gid: str, keys: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        params: List[Any] = [gid]
        if keys:
            params.append(keys)
        result = self._request("aria2.tellStatus", params)
        return result if isinstance(result, dict) else None

    def get_options(self, gid: str) -> Optional[Dict[str, Any]]:
        result = self._request("aria2.getOptions", [gid])
        return result if isinstance(result, dict) else None

    def change_option(self, gid: str, options: Dict[str, Any]) -> Optional[str]:
        result = self._request("aria2.changeOption", [gid, options])
        return result if isinstance(result, str) else None

    def get_global_stat(self) -> Optional[Dict[str, Any]]:
        result = self._request("aria2.getGlobalStat", [])
        return result if isinstance(result, dict) else None

    def get_active_downloads(self) -> Optional[List[Dict[str, Any]]]:
        result = self._request("aria2.tellActive", [])
        return result if isinstance(result, list) else None

    def get_waiting_downloads(self, offset: int = 0, num: int = 100) -> Optional[List[Dict[str, Any]]]:
        result = self._request("aria2.tellWaiting", [offset, num])
        return result if isinstance(result, list) else None

    def get_stopped_downloads(self, offset: int = 0, num: int = 100) -> Optional[List[Dict[str, Any]]]:
        result = self._request("aria2.tellStopped", [offset, num])
        return result if isinstance(result, list) else None

    # --- Batch operations ---
    def pause_batch(self, gids: List[str]) -> Optional[List[str]]:
        if not gids:
            return []
        calls = [{"methodName": "aria2.pause", "params": [gid]} for gid in gids]
        results = self._batch_request(calls)
        if results is None:
            return None
        parsed = []
        for r in results:
            if isinstance(r, list) and len(r) > 0:
                parsed.append(r[0] if isinstance(r[0], str) else None)
            else:
                parsed.append(None)
        return parsed

    def unpause_batch(self, gids: List[str]) -> Optional[List[str]]:
        if not gids:
            return []
        calls = [{"methodName": "aria2.unpause", "params": [gid]} for gid in gids]
        results = self._batch_request(calls)
        if results is None:
            return None
        parsed = []
        for r in results:
            if isinstance(r, list) and len(r) > 0:
                parsed.append(r[0] if isinstance(r[0], str) else None)
            else:
                parsed.append(None)
        return parsed

    def remove_batch(self, gids: List[str]) -> Optional[List[str]]:
        if not gids:
            return []
        calls = [{"methodName": "aria2.remove", "params": [gid]} for gid in gids]
        results = self._batch_request(calls)
        if results is None:
            return None
        parsed = []
        for r in results:
            if isinstance(r, list) and len(r) > 0:
                parsed.append(r[0] if isinstance(r[0], str) else None)
            else:
                parsed.append(None)
        return parsed
