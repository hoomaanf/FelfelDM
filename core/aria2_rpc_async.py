# core/aria2_rpc_async.py
"""
Async RPC client for aria2 using aiohttp.
Supports concurrent requests and batch calls with semaphore limiting.
"""

import base64
import logging
from typing import Any, Dict, List, Optional

import aiohttp
import asyncio

from core.constants import DEFAULT_TIMEOUT, DEFAULT_BATCH_TIMEOUT

logger = logging.getLogger(__name__)

# Maximum number of concurrent requests
MAX_CONCURRENT_REQUESTS = 20


class AsyncAria2RPC:
    """
    Asynchronous aria2 RPC client using aiohttp.
    Supports batch calls, connection pooling, and concurrency limiting.
    """

    def __init__(
        self,
        host: str = "http://localhost",
        port: int = 6800,
        secret: str = "",
        verify_ssl: bool = True,
        timeout: int = DEFAULT_TIMEOUT,
        connector_limit: int = 100,
    ) -> None:
        self.url = f"{host}:{port}/jsonrpc"
        self.secret = secret
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self._id = 0
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector_limit = connector_limit
        self._lock = asyncio.Lock()
        # Semaphore to limit concurrent requests
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure a session exists and return it."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=self._connector_limit,
                ssl=self.verify_ssl,
                force_close=False,
                enable_cleanup_closed=True,
            )
            timeout_obj = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout_obj,
            )
            logger.debug("AsyncRPC session created")
        return self._session

    async def _call(
        self,
        method: str,
        params: Optional[List] = None,
        timeout: Optional[int] = None,
    ) -> Optional[Any]:
        """
        Execute a single RPC call asynchronously with concurrency limiting.

        Args:
            method: RPC method name
            params: List of parameters
            timeout: Override the default timeout (in seconds)

        Returns:
            Result of the RPC call, or None on error
        """
        async with self._semaphore:
            async with self._lock:
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

                timeout_sec = timeout if timeout is not None else self.timeout

            try:
                session = await self._ensure_session()
                async with session.post(self.url, json=payload, timeout=timeout_sec) as response:
                    result = await response.json()
                    if "error" in result:
                        err = result["error"]
                        msg = f"aria2 error: {err.get('message', err)}"
                        logger.warning("[%s]: %s", method, msg)
                        return None
                    return result.get("result")
            except asyncio.TimeoutError:
                msg = f"aria2 timeout [{method}]"
                logger.warning(msg)
                return None
            except aiohttp.ClientConnectionError:
                msg = "aria2 disconnected"
                logger.warning(msg)
                return None
            except Exception as e:
                msg = f"aria2 error: {e}"
                logger.warning("[%s]: %s", method, msg)
                return None

    async def _prepare_multicall_params(self, calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare parameters for system.multicall."""
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
        return params

    async def batch_call(
        self,
        calls: List[Dict[str, Any]],
        timeout: Optional[int] = None,
    ) -> List[Any]:
        """
        Execute multiple RPC calls in a single request using system.multicall
        with concurrency limiting.
        """
        if not calls:
            return []

        async with self._semaphore:
            params = await self._prepare_multicall_params(calls)

            async with self._lock:
                self._id += 1
                payload = {
                    "jsonrpc": "2.0",
                    "id": str(self._id),
                    "method": "system.multicall",
                    "params": [params],
                }

                timeout_sec = timeout if timeout is not None else DEFAULT_BATCH_TIMEOUT

            try:
                session = await self._ensure_session()
                async with session.post(self.url, json=payload, timeout=timeout_sec) as response:
                    result = await response.json()
                    if "error" in result:
                        err = result["error"]
                        msg = f"multicall error: {err.get('message', err)}"
                        logger.warning(msg)
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

                    while len(processed) < len(calls):
                        processed.append(None)

                    return processed

            except asyncio.TimeoutError:
                msg = "aria2 timeout during batch call"
                logger.warning(msg)
                return [None] * len(calls)
            except aiohttp.ClientConnectionError:
                msg = "aria2 disconnected during batch call"
                logger.warning(msg)
                return [None] * len(calls)
            except Exception as e:
                msg = f"aria2 batch error: {e}"
                logger.warning(msg)
                return [None] * len(calls)

    async def add_url(self, url: str, options: Optional[Dict] = None) -> Optional[str]:
        """Add a download URL and return the GID."""
        params = [url]
        if options:
            params.append(options)
        result = await self._call("aria2.addUri", params)
        return result

    async def add_torrent(
        self,
        torrent_file: str,
        options: Optional[Dict] = None,
        selected_files: Optional[List[int]] = None,
    ) -> Optional[str]:
        """Add a torrent file and return the GID."""
        with open(torrent_file, "rb") as f:
            torrent_data = base64.b64encode(f.read()).decode("utf-8")

        params = [torrent_data]
        if options:
            if selected_files:
                options["select-file"] = ",".join(str(i) for i in selected_files)
            params.append(options)
        else:
            if selected_files:
                params.append({"select-file": ",".join(str(i) for i in selected_files)})

        result = await self._call("aria2.addTorrent", params)
        return result

    async def get_torrent_info(self, torrent_file: str) -> Optional[Dict[str, Any]]:
        """Get information about a torrent file."""
        with open(torrent_file, "rb") as f:
            torrent_data = base64.b64encode(f.read()).decode("utf-8")

        params = [torrent_data]
        result = await self._call("aria2.getTorrentInfo", params)
        return result

    async def remove(self, gid: str) -> Optional[Any]:
        return await self._call("aria2.remove", [gid])

    async def pause(self, gid: str) -> Optional[Any]:
        return await self._call("aria2.pause", [gid])

    async def resume(self, gid: str) -> Optional[Any]:
        return await self._call("aria2.unpause", [gid])

    async def tell_status(self, gid: str, fields: Optional[List[str]] = None) -> Optional[Dict]:
        params = [gid]
        if fields:
            params.append(fields)
        return await self._call("aria2.tellStatus", params)

    async def get_global_stat(self) -> Optional[Dict]:
        return await self._call("aria2.getGlobalStat")

    async def tell_active(self) -> Optional[List[Dict]]:
        return await self._call("aria2.tellActive")

    async def tell_waiting(self, offset: int = 0, num: int = 1000) -> Optional[List[Dict]]:
        return await self._call("aria2.tellWaiting", [offset, num])

    async def tell_stopped(self, offset: int = 0, num: int = 1000) -> Optional[List[Dict]]:
        return await self._call("aria2.tellStopped", [offset, num])

    async def purge_download_result(self) -> Optional[Any]:
        return await self._call("aria2.purgeDownloadResult")

    async def get_global_option(self) -> Optional[Dict]:
        return await self._call("aria2.getGlobalOption")

    async def change_global_option(self, options: Dict) -> Optional[Any]:
        return await self._call("aria2.changeGlobalOption", [options])

    async def change_option(self, gid: str, options: Dict) -> Optional[Any]:
        """Change options for a specific download."""
        return await self._call("aria2.changeOption", [gid, options])

    async def close(self) -> None:
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.debug("AsyncRPC session closed")
