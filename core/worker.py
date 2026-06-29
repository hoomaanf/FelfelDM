# =============================================================================
# core/worker.py
# =============================================================================
import asyncio
import logging
import threading
from typing import Optional, Dict, Any

from PyQt6.QtCore import QObject, pyqtSignal, QThread

from core.aria2_rpc import Aria2RPC
from core.aria2_rpc_async import AsyncAria2RPC
from core.data_store import DataStore
from core.constants import RPC_POLL_INTERVAL

logger = logging.getLogger(__name__)


class BackendWorker(QObject):
    stats_updated = pyqtSignal(dict)
    download_added = pyqtSignal(str)
    download_removed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, aria2: Aria2RPC, store: DataStore, async_mode: bool = False):
        super().__init__()
        self.aria2 = aria2
        self.async_aria2 = AsyncAria2RPC(aria2.host, aria2.port, aria2.secret, aria2.verify_ssl)
        self.store = store
        self.async_mode = async_mode
        self._running = False
        self._cached_stats: Dict[str, Any] = {}
        self._stats_lock = threading.Lock()  # Protect _cached_stats
        self._poll_interval = RPC_POLL_INTERVAL

        # Thread for sync polling
        self._thread: Optional[QThread] = None
        # Thread for async polling
        self._async_thread: Optional[QThread] = None
        # Async task reference for cancellation (if needed)
        self._async_task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Start polling in a separate thread."""
        if self._running:
            return
        self._running = True
        if self.async_mode:
            self._start_async()
        else:
            self._start_sync()

    def _start_sync(self) -> None:
        """Start synchronous polling in a dedicated QThread."""
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._poll_loop_sync)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _poll_loop_sync(self) -> None:
        """Polling loop running in background thread."""
        while self._running:
            self._poll_sync()
            self._thread.msleep(self._poll_interval * 1000)  # convert to ms

    def _poll_sync(self) -> None:
        """Perform a single poll (synchronous) with thread-safe cache update."""
        try:
            stats = self.aria2.get_global_stat()
            with self._stats_lock:
                self._cached_stats = stats
            self.stats_updated.emit(stats)
        except Exception as e:
            logger.error("Poll error: %s", e)
            self.error_occurred.emit(f"Poll error: {e}")

    def _start_async(self) -> None:
        """Start asynchronous polling using asyncio event loop."""
        self._async_thread = QThread()
        self.moveToThread(self._async_thread)
        self._async_thread.started.connect(self._poll_loop_async)
        self._async_thread.finished.connect(self._async_thread.deleteLater)
        self._async_thread.start()

    def _poll_loop_async(self) -> None:
        """Run async poll loop in background."""
        try:
            asyncio.run(self._async_poll_loop())
        except asyncio.CancelledError:
            logger.info("Async poll loop cancelled")
        except Exception as e:
            logger.error("Async poll loop crashed: %s", e)

    async def _async_poll_loop(self) -> None:
        """Async polling loop with proper cancellation handling."""
        while self._running:
            try:
                stats = await self.async_aria2.get_global_stat()
                if stats is not None:
                    with self._stats_lock:
                        self._cached_stats = stats
                    self.stats_updated.emit(stats)
            except asyncio.CancelledError:
                logger.info("Async poll loop cancelled internally")
                break
            except Exception as e:
                logger.error("Async poll error: %s", e)
                self.error_occurred.emit(f"Async poll error: {e}")
            # Sleep with periodic check for cancellation
            for _ in range(self._poll_interval * 10):  # check every 0.1s
                if not self._running:
                    break
                await asyncio.sleep(0.1)

    def stop(self) -> None:
        """Stop the worker and clean up threads."""
        self._running = False

        # Stop sync thread
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()

        # Stop async thread
        if self._async_thread and self._async_thread.isRunning():
            # Attempt to cancel any ongoing async tasks
            # We cannot directly cancel the running event loop, but we can schedule a cancellation
            # by calling stop on the async_aria2 or by using a future. However, the loop will
            # check _running periodically and exit.
            self._async_thread.quit()
            self._async_thread.wait()

        logger.info("Worker stopped")

    def get_cached_stats(self) -> Dict[str, Any]:
        """Thread-safe getter for cached statistics."""
        with self._stats_lock:
            return self._cached_stats.copy()
