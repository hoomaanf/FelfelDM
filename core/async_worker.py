# core/async_worker.py
"""
Async worker that runs asyncio event loop in a separate thread
and integrates with Qt signals.
"""

import asyncio
import logging
from typing import Optional, Dict, Any

from PyQt6.QtCore import QObject, pyqtSignal, QThread

from core.aria2_rpc_async import AsyncAria2RPC
from core.data_store import DataStore
from core.constants import RPC_POLL_INTERVAL

logger = logging.getLogger(__name__)


class AsyncWorker(QObject):
    """
    Asynchronous worker that polls aria2 using asyncio and emits stats.
    Runs in a separate thread with its own event loop.
    """

    stats_updated = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        aria2: AsyncAria2RPC,
        store: DataStore,
        poll_interval: int = RPC_POLL_INTERVAL,
    ) -> None:
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.poll_interval = poll_interval / 1000.0  # convert to seconds
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[QThread] = None
        self._cached_connected = False
        self._connection_check_counter = 0

    def start(self) -> None:
        """Start the worker in a separate thread with its own event loop."""
        if self._running:
            return

        self._running = True
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._run)
        self._thread.finished.connect(self._cleanup)
        self._thread.start()
        logger.info("AsyncWorker started")

    def _run(self) -> None:
        """Run the asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._poll_loop())

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            try:
                await self._poll()
            except Exception as e:
                logger.error("Polling error: %s", e)
                self.error_occurred.emit(str(e))
            await asyncio.sleep(self.poll_interval)

    async def _poll(self) -> None:
        """Perform a single poll cycle."""
        # Check connection status (every 10 polls to reduce traffic)
        self._connection_check_counter += 1
        if self._connection_check_counter >= 10:
            try:
                connected = await self._check_connection()
                if connected != self._cached_connected:
                    self._cached_connected = connected
                    self.connection_changed.emit(connected)
                self._connection_check_counter = 0
            except Exception:
                pass

        if not self._cached_connected:
            return

        # Get stats using batch call
        try:
            results = await self.aria2.batch_call([
                {"method": "aria2.getGlobalStat"},
                {"method": "aria2.tellActive"},
                {"method": "aria2.tellWaiting", "params": [0, 1000]},
                {"method": "aria2.tellStopped", "params": [0, 1000]},
            ])

            if len(results) >= 4:
                stats = {
                    "global": results[0],
                    "active": results[1] or [],
                    "waiting": results[2] or [],
                    "stopped": results[3] or [],
                    "connected": self._cached_connected,
                }
                self.stats_updated.emit(stats)
        except Exception as e:
            logger.warning("Failed to get stats: %s", e)

    async def _check_connection(self) -> bool:
        """Check if aria2 is reachable."""
        try:
            # Try to get global stat as a ping
            result = await self.aria2.get_global_stat()
            return result is not None
        except Exception:
            return False

    def stop(self) -> None:
        """Stop the worker and clean up."""
        self._running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread:
            self._thread.quit()
            self._thread.wait()

        # Close the async session
        if self._loop and not self._loop.is_closed():
            self._loop.run_until_complete(self.aria2.close())

        logger.info("AsyncWorker stopped")

    def _cleanup(self) -> None:
        """Clean up resources."""
        if self._loop and not self._loop.is_closed():
            self._loop.close()
        logger.debug("AsyncWorker cleaned up")

    def is_running(self) -> bool:
        return self._running
