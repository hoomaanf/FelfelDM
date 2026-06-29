# =============================================================================
# core/aria2_rpc_base.py
# =============================================================================
import json
import logging
from typing import Optional, List, Any, Dict

logger = logging.getLogger(__name__)


class BaseAria2RPC:
    """Base class for aria2 RPC clients with common functionality."""

    def __init__(self, host: str = "127.0.0.1", port: int = 6800,
                 secret: str = "", verify_ssl: bool = True) -> None:
        self.host = host
        self.port = port
        self.secret = secret
        self.verify_ssl = verify_ssl
        self._id = 1

    def _build_url(self) -> str:
        """Build the RPC URL with proper IPv6 handling."""
        if self.host and ':' in self.host:
            return f"http://[{self.host}]:{self.port}/jsonrpc"
        return f"http://{self.host}:{self.port}/jsonrpc"

    def _prepare_payload(self, method: str, params: Optional[List] = None) -> Dict[str, Any]:
        """Prepare JSON-RPC payload with id and token."""
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
        return payload

    def _handle_response(self, response_data: Any) -> Optional[Any]:
        """Extract result from response or log error."""
        if response_data is None:
            return None
        if isinstance(response_data, dict):
            if "error" in response_data:
                logger.error("RPC error: %s", response_data["error"])
                return None
            return response_data.get("result")
        # For multicall, return the list as is
        return response_data

    def _send_request(self, payload: Dict[str, Any]) -> Optional[Any]:
        """Send the request and return raw response. Must be overridden."""
        raise NotImplementedError

    def _call(self, method: str, params: Optional[List] = None) -> Optional[Any]:
        """Perform an RPC call and handle response."""
        payload = self._prepare_payload(method, params)
        response = self._send_request(payload)
        return self._handle_response(response)

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

    def change_global_option(self, options: Dict[str, Any]) -> Optional[bool]:
        """Change global options (e.g., speed limit)."""
        result = self._call("aria2.changeGlobalOption", [options])
        return result == "OK"

    def batch_call(self, calls: List[Dict]) -> Optional[List]:
        """
        Perform multiple calls using system.multicall.
        Each call: {"method": "aria2.getGlobalStat", "params": []}
        """
        if not calls:
            return []
        multicall_params = []
        for call in calls:
            method = call.get("method")
            params = call.get("params", [])
            if not method:
                continue
            multicall_params.append({
                "methodName": method,
                "params": params
            })
        if not multicall_params:
            return []
        result = self._call("system.multicall", [multicall_params])
        if result is None:
            return None
        # Extract results or log errors
        results = []
        for item in result:
            if isinstance(item, dict) and "error" in item:
                logger.error("Multicall error: %s", item["error"])
                results.append(None)
            else:
                results.append(item)
        return results
