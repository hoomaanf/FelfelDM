# =============================================================================
# core/aria2_rpc_async.py
# =============================================================================
import asyncio
import json
import logging
from typing import Optional, List, Any, Dict

import aiohttp

from core.aria2_rpc_base import BaseAria2RPC

logger = logging.getLogger(__name__)


class AsyncAria2RPC(BaseAria2RPC):
    """Asynchronous client for aria2 RPC using aiohttp."""

    def __init__(self, host: str = "127.0.0.1", port: int = 6800,
                 secret: str = "", verify_ssl: bool = True) -> None:
        super().__init__(host, port, secret, verify_ssl)
        self._semaphore = asyncio.Semaphore(10)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> None:
        if self._session is None:
            connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
            self._session = aiohttp.ClientSession(connector=connector)

    async def _send_request_async(self, payload: Dict[str, Any]) -> Optional[Any]:
        """Send request asynchronously using aiohttp."""
        await self._ensure_session()
        url = self._build_url()
        async with self._semaphore:
            try:
                async with self._session.post(url, json=payload, ssl=self.verify_ssl) as resp:
                    if resp.status != 200:
                        logger.error("RPC error: %d %s", resp.status, await resp.text())
                        return None
                    return await resp.json()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("RPC exception: %s", e)
                return None

    async def _call_async(self, method: str, params: Optional[List] = None) -> Optional[Any]:
        """Async version of _call."""
        payload = self._prepare_payload(method, params)
        response = await self._send_request_async(payload)
        return self._handle_response(response)

    # Async versions of all public methods
    async def get_global_stat(self) -> Dict[str, Any]:
        return await self._call_async("aria2.getGlobalStat") or {}

    async def add_uri(self, uris: List[str], options: Optional[Dict] = None) -> Optional[str]:
        params = [uris]
        if options:
            params.append(options)
        return await self._call_async("aria2.addUri", params)

    async def add_magnet(self, magnet: str, options: Optional[Dict] = None) -> Optional[str]:
        params = [magnet]
        if options:
            params.append(options)
        return await self._call_async("aria2.addMagnet", params)

    async def remove(self, gid: str) -> Optional[str]:
        return await self._call_async("aria2.remove", [gid])

    async def pause(self, gid: str) -> Optional[str]:
        return await self._call_async("aria2.pause", [gid])

    async def unpause(self, gid: str) -> Optional[str]:
        return await self._call_async("aria2.unpause", [gid])

    async def tell_status(self, gid: str) -> Optional[Dict]:
        return await self._call_async("aria2.tellStatus", [gid])

    async def tell_active(self) -> Optional[List[Dict]]:
        return await self._call_async("aria2.tellActive")

    async def tell_waiting(self, offset: int = 0, num: int = 100) -> Optional[List[Dict]]:
        return await self._call_async("aria2.tellWaiting", [offset, num])

    async def tell_stopped(self, offset: int = 0, num: int = 100) -> Optional[List[Dict]]:
        return await self._call_async("aria2.tellStopped", [offset, num])

    async def change_global_option(self, options: Dict[str, Any]) -> Optional[bool]:
        result = await self._call_async("aria2.changeGlobalOption", [options])
        return result == "OK"

    async def batch_call(self, calls: List[Dict]) -> Optional[List]:
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
        result = await self._call_async("system.multicall", [multicall_params])
        if result is None:
            return None
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
