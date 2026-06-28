# core/aria2_rpc.py
import logging
import ssl
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class Aria2RPC:
    """aria2 RPC client with batch call support via system.multicall and SSL validation."""

    def __init__(self, host: str = "http://localhost", port: int = 6800, secret: str = "",
                 verify_ssl: bool = True):
        self.url = f"{host}:{port}/jsonrpc"
        self.secret = secret
        self._id = 0
        self.on_error = None
        self.verify_ssl = verify_ssl
        self._session = requests.Session()
        if not verify_ssl:
            self._session.verify = False
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _call(self, method: str, params: Optional[List] = None) -> Optional[Any]:
        """Execute a single RPC call."""
        self._id += 1
        token = f"token:{self.secret}" if self.secret else None
        if token:
            p = [token] + (params or [])
        else:
            p = params or []

        payload = {
            "jsonrpc": "2.0",
            "id": str(self._id),
            "method": method,
            "params": p
        }

        try:
            r = self._session.post(self.url, json=payload, timeout=15)
            result = r.json()
            if "error" in result:
                err = result["error"]
                msg = f"aria2 error: {err.get('message', err)}"
                logger.warning(f"[{method}]: {msg}")
                if self.on_error:
                    self.on_error(msg)
                return None
            return result.get("result")
        except requests.exceptions.ConnectionError:
            msg = "aria2 disconnected"
            logger.warning(msg)
            if self.on_error:
                self.on_error(msg)
            return None
        except requests.exceptions.Timeout:
            msg = f"aria2 timeout [{method}]"
            logger.warning(msg)
            if self.on_error:
                self.on_error(msg)
            return None
        except Exception as e:
            msg = f"aria2 error: {e}"
            logger.warning(f"[{method}]: {msg}")
            if self.on_error:
                self.on_error(msg)
            return None

    def batch_call(self, calls: List[Dict[str, Any]]) -> List[Any]:
        """
        Execute multiple RPC calls in a single request using system.multicall.

        Args:
            calls: List of dicts with 'method' and optional 'params'

        Returns:
            List of results from each call, in the same order as calls.
            If a sub‑call fails, its entry will be None.
        """
        if not calls:
            return []

        params = []
        for call in calls:
            method = call.get("method")
            params_list = call.get("params", [])
            if self.secret:
                params_list = [f"token:{self.secret}"] + params_list
            params.append({
                "methodName": method,
                "params": params_list
            })

        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": str(self._id),
            "method": "system.multicall",
            "params": [params]
        }

        try:
            r = self._session.post(self.url, json=payload, timeout=15)
            result = r.json()
            if "error" in result:
                err = result["error"]
                msg = f"multicall error: {err.get('message', err)}"
                logger.warning(msg)
                if self.on_error:
                    self.on_error(msg)
                return [None] * len(calls)

            raw_results = result.get("result")
            if not isinstance(raw_results, list):
                logger.warning(f"Unexpected multicall response type: {type(raw_results)}")
                return [None] * len(calls)

            processed = []
            for idx, item in enumerate(raw_results[:len(calls)]):
                if isinstance(item, dict):
                    if "result" in item:
                        processed.append(item["result"])
                    elif "error" in item:
                        err = item["error"]
                        msg = f"subcall error at index {idx}: {err.get('message', err)}"
                        logger.warning(msg)
                        processed.append(None)
                    else:
                        processed.append(item)
                else:
                    processed.append(item)

            if len(processed) < len(calls):
                processed.extend([None] * (len(calls) - len(processed)))

            return processed
        except Exception as e:
            logger.warning(f"batch_call error: {e}")
            return [None] * len(calls)

    def add_url(self, url: str, options: Optional[Dict] = None) -> Optional[Any]:
        return self._call("aria2.addUri", [[url], options or {}])

    def pause(self, gid: str) -> Optional[Any]:
        return self._call("aria2.pause", [gid])

    def resume(self, gid: str) -> Optional[Any]:
        return self._call("aria2.unpause", [gid])

    def remove(self, gid: str) -> None:
        self._call("aria2.remove", [gid])
        self._call("aria2.removeDownloadResult", [gid])

    def change_global_option(self, options: Dict) -> Optional[Any]:
        return self._call("aria2.changeGlobalOption", [options])

    def get_global_stat(self) -> Optional[Dict]:
        return self._call("aria2.getGlobalStat")

    def tell_status(self, gid: str, keys: Optional[List[str]] = None) -> Optional[Dict]:
        if keys is None:
            keys = ["gid", "status", "totalLength", "completedLength",
                    "downloadSpeed", "connections", "files", "errorMessage"]
        return self._call("aria2.tellStatus", [gid, keys])

    def tell_active(self) -> List[Dict]:
        return self._call("aria2.tellActive") or []

    def tell_waiting(self, offset: int = 0, num: int = 1000) -> List[Dict]:
        return self._call("aria2.tellWaiting", [offset, num]) or []

    def tell_stopped(self, offset: int = 0, num: int = 1000) -> List[Dict]:
        return self._call("aria2.tellStopped", [offset, num]) or []

    def is_connected(self) -> bool:
        return self.get_global_stat() is not None

    def get_status(self, gid: str) -> Optional[str]:
        result = self.tell_status(gid, ["gid", "status"])
        if result:
            return result.get("status")
        return None

    def force_pause(self, gid: str) -> Optional[Any]:
        return self._call("aria2.forcePause", [gid])
