# =============================================================================
# core/aria2_rpc.py
# =============================================================================
import json
import logging
from typing import Optional, List, Any, Dict
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


class Aria2RPC:
    """Synchronous client for aria2 RPC."""

    def __init__(self, host: str = "127.0.0.1", port: int = 6800, secret: str = "", verify_ssl: bool = True):
        self.host = host
        self.port = port
        self.secret = secret
        self.verify_ssl = verify_ssl
        self._id = 1

    def _build_url(self) -> str:
        """Build the RPC URL with proper IPv6 handling."""
        if self.host and ':' in self.host:
            # IPv6 address
            return f"http://[{self.host}]:{self.port}/jsonrpc"
        return f"http://{self.host}:{self.port}/jsonrpc"

    def _call(self, method: str, params: Optional[List] = None) -> Optional[Any]:
        """Perform an RPC call."""
        call_id = self._id
        self._id += 1

        payload = {
            "jsonrpc": "2.0",
            "id": call_id,
            "method": method,
            "params": params or []
        }
        if self.secret:
            payload["params"].insert(0, f"token:{self.secret}")

        url = self._build_url()
        try:
            resp = requests.post(url, json=payload, verify=self.verify_ssl, timeout=30)
            if resp.status_code != 200:
                logger.error("RPC error: %d %s", resp.status_code, resp.text)
                return None
            data = resp.json()
            if "error" in data:
                logger.error("RPC error: %s", data["error"])
                return None
            return data.get("result")
        except Exception as e:
            logger.error("RPC exception: %s", e)
            return None

    def get_global_stat(self) -> Dict[str, Any]:
        """Get global statistics."""
        return self._call("aria2.getGlobalStat") or {}

    def add_uri(self, uris: List[str], options: Optional[Dict] = None) -> Optional[str]:
        """Add download with URIs."""
        params = [uris]
        if options:
            params.append(options)
        return self._call("aria2.addUri", params)

    def add_magnet(self, magnet: str, options: Optional[Dict] = None) -> Optional[str]:
        """Add magnet link."""
        params = [magnet]
        if options:
            params.append(options)
        return self._call("aria2.addMagnet", params)

    def remove(self, gid: str) -> Optional[str]:
        """Remove download."""
        return self._call("aria2.remove", [gid])

    def pause(self, gid: str) -> Optional[str]:
        """Pause download."""
        return self._call("aria2.pause", [gid])

    def unpause(self, gid: str) -> Optional[str]:
        """Unpause download."""
        return self._call("aria2.unpause", [gid])

    def tell_status(self, gid: str) -> Optional[Dict]:
        """Get status of a download."""
        return self._call("aria2.tellStatus", [gid])

    def tell_active(self) -> Optional[List[Dict]]:
        """Get list of active downloads."""
        return self._call("aria2.tellActive")

    def tell_waiting(self, offset: int = 0, num: int = 100) -> Optional[List[Dict]]:
        """Get list of waiting downloads."""
        return self._call("aria2.tellWaiting", [offset, num])

    def tell_stopped(self, offset: int = 0, num: int = 100) -> Optional[List[Dict]]:
        """Get list of stopped downloads."""
        return self._call("aria2.tellStopped", [offset, num])
