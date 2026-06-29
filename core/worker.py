# core/worker.py
"""
Background worker that polls aria2 using batch calls.
Supports scheduling and async mode.
"""

import logging
import asyncio
from typing import Optional, Dict, Any

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QThread

from core.aria2_rpc import Aria2RPC
from core.aria2_rpc_async import AsyncAria2RPC
from core.data_store import DataStore
from core.constants import RPC_POLL_INTERVAL, SESSION_SAVE_INTERVAL

logger = logging.getLogger(__name__)


class BackendWorker(QObject):
    """
    Background worker that polls aria2 for stats and emits signals.
    Also handles scheduling and async mode.
    """

    stats_updated = pyqtSignal(dict)
    connection_changed = pyqtSignal(bool)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        aria2: Aria2RPC,
        store: DataStore,
        poll_interval: int = RPC_POLL_INTERVAL,
        use_async: bool = False,
    ) -> None:
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.poll_interval = poll_interval
        self.use_async = use_async
        self._timer: Optional[QTimer] = None
        self._running = False
        self._cached_connected = False
        self._connection_check_counter = 0

        # Async related
        self._async_aria2: Optional[AsyncAria2RPC] = None
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        self._async_thread: Optional[QThread] = None
        self._async_running = False

        # Scheduling timer (every minute)
        self._schedule_timer = QTimer()
        self._schedule_timer.timeout.connect(self._check_schedules)
        self._schedule_timer.start(60000)  # 1 minute

    def start(self) -> None:
        """Start the worker."""
        if self._running:
            return

        self._running = True

        if self.use_async:
            self._start_async()
        else:
            self._start_sync()

        logger.info("Worker started (async=%s)", self.use_async)

    def _start_sync(self) -> None:
        """Start synchronous polling."""
        self._timer = QTimer()
        self._timer.timeout.connect(self._poll)
        self._timer.start(self.poll_interval)

    def _start_async(self) -> None:
        """Start asynchronous polling with asyncio."""
        self._async_aria2 = AsyncAria2RPC(
            host=self.aria2.url.rsplit(':', 1)[0],  # extract host
            port=int(self.aria2.url.rsplit(':', 1)[1].split('/')[0]),
            secret=self.aria2.secret,
            verify_ssl=self.aria2.verify_ssl,
            timeout=self.aria2.timeout,
        )
        self._async_running = True
        self._async_thread = QThread()
        self.moveToThread(self._async_thread)
        self._async_thread.started.connect(self._run_async_loop)
        self._async_thread.start()

    def _run_async_loop(self) -> None:
        """Run the asyncio event loop for async polling."""
        self._async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._async_loop)
        self._async_loop.run_until_complete(self._async_poll_loop())

    async def _async_poll_loop(self) -> None:
        """Async polling loop."""
        while self._async_running:
            try:
                await self._async_poll()
            except Exception as e:
                logger.error("Async poll error: %s", e)
                self.error_occurred.emit(str(e))
            await asyncio.sleep(self.poll_interval / 1000.0)

    async def _async_poll(self) -> None:
        """Perform a single async poll cycle."""
        # Connection check
        connected = await self._async_check_connection()
        if connected != self._cached_connected:
            self._cached_connected = connected
            self.connection_changed.emit(connected)

        if not connected:
            return

        # Get stats via batch
        results = await self._async_aria2.batch_call([
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
                "connected": connected,
            }
            self.stats_updated.emit(stats)

    async def _async_check_connection(self) -> bool:
        try:
            result = await self._async_aria2.get_global_stat()
            return result is not None
        except Exception:
            return False

    def _poll(self) -> None:
        """Synchronous poll."""
        # Connection check (every 10 polls)
        self._connection_check_counter += 1
        if self._connection_check_counter >= 10:
            connected = self.aria2.is_connected()
            if connected != self._cached_connected:
                self._cached_connected = connected
                self.connection_changed.emit(connected)
            self._connection_check_counter = 0

        if not self._cached_connected:
            return

        # Get stats
        results = self.aria2.batch_call([
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

    def _check_schedules(self) -> None:
        """Check queue schedules and pause/resume accordingly."""
        for queue in self.store.queues:
            if queue.schedule_enabled:
                if queue.is_scheduled_now():
                    if queue.paused:
                        # Resume queue
                        queue.paused = False
                        self._resume_queue(queue)
                else:
                    if not queue.paused:
                        # Pause queue
                        queue.paused = True
                        self._pause_queue(queue)

    def _resume_queue(self, queue) -> None:
        """Resume all downloads in a queue."""
        for gid in queue.downloads:
            self.aria2.resume(gid)
        logger.debug("Resumed queue: %s", queue.name)

    def _pause_queue(self, queue) -> None:
        """Pause all downloads in a queue."""
        for gid in queue.downloads:
            self.aria2.pause(gid)
        logger.debug("Paused queue: %s", queue.name)

    def stop(self) -> None:
        """Stop the worker."""
        self._running = False
        if self._timer:
            self._timer.stop()
            self._timer = None

        if self._async_running:
            self._async_running = False
            if self._async_loop:
                self._async_loop.call_soon_threadsafe(self._async_loop.stop)
            if self._async_thread:
                self._async_thread.quit()
                self._async_thread.wait()
            if self._async_loop and not self._async_loop.is_closed():
                self._async_loop.run_until_complete(self._async_aria2.close())
                self._async_loop.close()

        self._schedule_timer.stop()
        logger.info("Worker stopped")

    def is_running(self) -> bool:
        return self._running
