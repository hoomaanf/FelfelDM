# =============================================================================
# core/aria2_rpc_async.py
# =============================================================================
import asyncio
import json
import logging
from typing import Optional, List, Any, Dict
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)


class AsyncAria2RPC:
    """Asynchronous client for aria2 RPC using aiohttp."""

    def __init__(self, host: str = "127.0.0.1", port: int = 6800, secret: str = "", verify_ssl: bool = True):
        self.host = host
        self.port = port
        self.secret = secret
        self.verify_ssl = verify_ssl
        self._id = 1
        self._semaphore = asyncio.Semaphore(10)  # limit concurrent requests
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> None:
        if self._session is None:
            connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
            self._session = aiohttp.ClientSession(connector=connector)

    async def _call(self, method: str, params: Optional[List] = None) -> Optional[Any]:
        """Perform an RPC call with atomic id generation (no separate lock)."""
        await self._ensure_session()
        call_id = self._id
        self._id += 1  # atomic in asyncio if not interrupted

        payload = {
            "jsonrpc": "2.0",
            "id": call_id,
            "method": method,
            "params": params or []
        }
        if self.secret:
            payload["params"].insert(0, f"token:{self.secret}")

        # Handle IPv6
        if self.host and ':' in self.host:
            url = f"http://[{self.host}]:{self.port}/jsonrpc"
        else:
            url = f"http://{self.host}:{self.port}/jsonrpc"

        async with self._semaphore:
            try:
                async with self._session.post(url, json=payload, ssl=self.verify_ssl) as resp:
                    if resp.status != 200:
                        logger.error("RPC error: %d %s", resp.status, await resp.text())
                        return None
                    data = await resp.json()
                    if "error" in data:
                        logger.error("RPC error: %s", data["error"])
                        return None
                    return data.get("result")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("RPC exception: %s", e)
                return None

    async def get_global_stat(self) -> Dict[str, Any]:
        """Get global statistics."""
        return await self._call("aria2.getGlobalStat") or {}

    async def add_uri(self, uris: List[str], options: Optional[Dict] = None) -> Optional[str]:
        """Add download with URIs."""
        params = [uris]
        if options:
            params.append(options)
        return await self._call("aria2.addUri", params)

    async def add_magnet(self, magnet: str, options: Optional[Dict] = None) -> Optional[str]:
        """Add magnet link."""
        params = [magnet]
        if options:
            params.append(options)
        return await self._call("aria2.addMagnet", params)

    async def remove(self, gid: str) -> Optional[str]:
        """Remove download."""
        return await self._call("aria2.remove", [gid])

    async def pause(self, gid: str) -> Optional[str]:
        """Pause download."""
        return await self._call("aria2.pause", [gid])

    async def unpause(self, gid: str) -> Optional[str]:
        """Unpause download."""
        return await self._call("aria2.unpause", [gid])

    async def tell_status(self, gid: str) -> Optional[Dict]:
        """Get status of a download."""
        return await self._call("aria2.tellStatus", [gid])

    async def batch_call(self, calls: List[Dict]) -> Optional[List]:
        """
        Perform multiple calls in one request using system.multicall.
        Each call should be a dict with keys: "method", "params" (optional).
        Returns a list of results in the same order.
        """
        if not calls:
            return []
        # Build multicall params
        multicall_params = []
        for call in calls:
            method = call.get("method")
            params = call.get("params", [])
            if not method:
                logger.warning("Skipping call with no method")
                continue
            multicall_params.append({
                "methodName": method,
                "params": params
            })
        if not multicall_params:
            return []
        result = await self._call("system.multicall", [multicall_params])
        if result is None:
            return None
        # system.multicall returns a list where each element is either the result or an error dict
        # We'll extract results or log errors
        results = []
        for item in result:
            if isinstance(item, dict) and "error" in item:
                logger.error("Multicall error: %s", item["error"])
                results.append(None)
            else:
                results.append(item)
        return results

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None
