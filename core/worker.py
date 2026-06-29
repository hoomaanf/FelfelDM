# =============================================================================
# core/worker.py
# =============================================================================
import asyncio
import logging
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
        self._poll_interval = RPC_POLL_INTERVAL

        # Thread for sync polling
        self._thread: Optional[QThread] = None

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
        """Perform a single poll (synchronous)."""
        try:
            stats = self.aria2.get_global_stat()
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
        asyncio.run(self._async_poll_loop())

    async def _async_poll_loop(self) -> None:
        """Async polling loop."""
        while self._running:
            try:
                stats = await self.async_aria2.get_global_stat()
                self._cached_stats = stats
                self.stats_updated.emit(stats)
            except Exception as e:
                logger.error("Async poll error: %s", e)
                self.error_occurred.emit(f"Async poll error: {e}")
            await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        """Stop the worker and clean up threads."""
        self._running = False
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
        if hasattr(self, '_async_thread') and self._async_thread.isRunning():
            self._async_thread.quit()
            self._async_thread.wait()

    def get_cached_stats(self) -> Dict[str, Any]:
        """Return cached statistics."""
        return self._cached_stats
