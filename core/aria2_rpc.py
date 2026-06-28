# core/aria2_rpc.py
"""
aria2 RPC client with batch call support via system.multicall,
SSL validation, and connection caching.
"""

import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class Aria2RPC:
    """
    aria2 RPC client with batch call support via system.multicall and SSL validation.
    Uses a persistent requests.Session with keep-alive for connection caching.
    """

    DEFAULT_TIMEOUT: int = 15

    def __init__(
        self,
        host: str = "http://localhost",
        port: int = 6800,
        secret: str = "",
        verify_ssl: bool = True,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.url = f"{host}:{port}/jsonrpc"
        self.secret = secret
        self._id = 0
        self.on_error = None
        self.verify_ssl = verify_ssl
        self.timeout = timeout

        # Use a persistent session with keep-alive
        self._session = requests.Session()
        self._session.verify = verify_ssl
        # Enable keep-alive
        self._session.headers.update({"Connection": "keep-alive"})

        # Do NOT disable urllib3 warnings - we want users to see SSL issues
        if not verify_ssl:
            logger.warning(
                "SSL verification is disabled. This is insecure and should only be used for testing."
            )

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
            "params": p,
        }

        try:
            r = self._session.post(self.url, json=payload, timeout=self.timeout)
            result = r.json()
            if "error" in result:
                err = result["error"]
                msg = f"aria2 error: {err.get('message', err)}"
                logger.warning("[%s]: %s", method, msg)
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
            logger.warning("[%s]: %s", method, msg)
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
                "params": params_list,
            })

        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": str(self._id),
            "method": "system.multicall",
            "params": [params],
        }

        try:
            r = self._session.post(self.url, json=payload, timeout=self.timeout)
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
                logger.warning("Unexpected multicall response type: %s", type(raw_results))
                return [None] * len(calls)

            processed = []
            for idx, item in enumerate(raw_results[:len(calls)]):
                if isinstance(item, dict):
                    if "result" in item:
                        processed.append(item["result"])
                    elif "error" in item:
                        err = item["error"]
                        logger.warning("Sub-call %d failed: %s", idx, err.get("message", err))
                        processed.append(None)
                    else:
                        processed.append(None)
                else:
                    processed.append(None)

            # If we got fewer results than calls, pad with None
            while len(processed) < len(calls):
                processed.append(None)

            return processed

        except requests.exceptions.ConnectionError:
            msg = "aria2 disconnected during batch call"
            logger.warning(msg)
            if self.on_error:
                self.on_error(msg)
            return [None] * len(calls)
        except requests.exceptions.Timeout:
            msg = "aria2 timeout during batch call"
            logger.warning(msg)
            if self.on_error:
                self.on_error(msg)
            return [None] * len(calls)
        except Exception as e:
            msg = f"aria2 batch error: {e}"
            logger.warning(msg)
            if self.on_error:
                self.on_error(msg)
            return [None] * len(calls)

    def is_connected(self) -> bool:
        """Check if aria2 is reachable."""
        try:
            response = self._session.get(self.url, timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def add_url(self, url: str, options: Optional[Dict] = None) -> Optional[str]:
        """Add a download URL and return the GID."""
        params = [url]
        if options:
            params.append(options)
        result = self._call("aria2.addUri", params)
        return result

    def add_torrent(self, torrent_file: str, options: Optional[Dict] = None) -> Optional[str]:
        """Add a torrent file and return the GID."""
        import base64
        with open(torrent_file, "rb") as f:
            torrent_data = base64.b64encode(f.read()).decode("utf-8")
        params = [torrent_data]
        if options:
            params.append(options)
        result = self._call("aria2.addTorrent", params)
        return result

    def remove(self, gid: str) -> Optional[Any]:
        """Remove a download by GID."""
        return self._call("aria2.remove", [gid])

    def pause(self, gid: str) -> Optional[Any]:
        """Pause a download by GID."""
        return self._call("aria2.pause", [gid])

    def resume(self, gid: str) -> Optional[Any]:
        """Resume a download by GID."""
        return self._call("aria2.unpause", [gid])

    def tell_status(self, gid: str, fields: Optional[List[str]] = None) -> Optional[Dict]:
        """
        Get status of a download by GID.

        Args:
            gid: The GID of the download.
            fields: Optional list of fields to return. If None, returns all fields.

        Returns:
            Dictionary containing the download status, or None on error.
        """
        params = [gid]
        if fields:
            params.append(fields)
        return self._call("aria2.tellStatus", params)

    def get_global_stat(self) -> Optional[Dict]:
        """Get global statistics."""
        return self._call("aria2.getGlobalStat")

    def tell_active(self) -> Optional[List[Dict]]:
        """Get active downloads."""
        return self._call("aria2.tellActive")

    def tell_waiting(self, offset: int = 0, num: int = 1000) -> Optional[List[Dict]]:
        """Get waiting downloads."""
        return self._call("aria2.tellWaiting", [offset, num])

    def tell_stopped(self, offset: int = 0, num: int = 1000) -> Optional[List[Dict]]:
        """Get stopped downloads."""
        return self._call("aria2.tellStopped", [offset, num])

    def purge_download_result(self) -> Optional[Any]:
        """Purge completed/removed downloads from memory."""
        return self._call("aria2.purgeDownloadResult")

    def get_global_option(self) -> Optional[Dict]:
        """Get global options."""
        return self._call("aria2.getGlobalOption")

    def change_global_option(self, options: Dict) -> Optional[Any]:
        """Change global options."""
        return self._call("aria2.changeGlobalOption", [options])

    def set_secret(self, secret: str) -> None:
        """
        Update the RPC secret.

        Args:
            secret: The new RPC secret.
        """
        self.secret = secret
        logger.debug("RPC secret updated")

    def get_certificate_fingerprint(self) -> Optional[str]:
        """
        Get the certificate fingerprint from the current SSL context.

        Returns:
            The SHA-256 fingerprint as a hex string, or None if not available.
        """
        # This is a placeholder. In a real implementation, you would extract
        # the fingerprint from the SSL context of the session.
        # For now, we return None as the fingerprint is managed by Aria2Manager.
        return None

    def _ensure_session(self) -> None:
        """
        Ensure the session is valid and recreate it if necessary.
        Called after the secret or certificate changes.
        """
        # Recreate the session to pick up new SSL settings
        old_verify = self._session.verify
        old_headers = self._session.headers.copy()

        self._session.close()
        self._session = requests.Session()
        self._session.verify = old_verify
        self._session.headers.update(old_headers)
        self._session.headers.update({"Connection": "keep-alive"})

        logger.debug("RPC session recreated")

    def close(self) -> None:
        """Close the session."""
        self._session.close()
