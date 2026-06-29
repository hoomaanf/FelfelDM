# =============================================================================
# core/worker.py
# =============================================================================
import asyncio
import logging
import threading
from abc import ABC, abstractmethod, ABCMeta
from typing import Optional, Dict, Any

from PyQt6.QtCore import QObject, pyqtSignal, QThread

from core.aria2_rpc import Aria2RPC
from core.aria2_rpc_async import AsyncAria2RPC
from core.data_store import DataStore
from core.constants import RPC_POLL_INTERVAL

logger = logging.getLogger(__name__)

# Define a metaclass that combines QObject's metaclass and ABCMeta
class QABCMeta(type(QObject), ABCMeta):
    pass


class BaseBackendWorker(QObject, ABC, metaclass=QABCMeta):
    """Base class for backend workers providing common signals and cache."""

    stats_updated = pyqtSignal(dict)
    download_added = pyqtSignal(str)
    download_removed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, aria2: Aria2RPC, store: DataStore) -> None:
        super().__init__()
        self.aria2: Aria2RPC = aria2
        self.async_aria2: AsyncAria2RPC = AsyncAria2RPC(
            aria2.host, aria2.port, aria2.secret, aria2.verify_ssl
        )
        self.store: DataStore = store
        self._running: bool = False
        self._cached_stats: Dict[str, Any] = {}
        self._stats_lock = threading.Lock()
        self._poll_interval: int = RPC_POLL_INTERVAL
        self._thread: Optional[QThread] = None

        # Error counter and max allowed errors before auto-stop
        self._error_count: int = 0
        self._max_errors: int = 5

    @abstractmethod
    def start(self) -> None:
        """Start the worker's polling loop."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the worker and clean up."""
        pass

    def get_cached_stats(self) -> Dict[str, Any]:
        """Thread-safe getter for cached statistics."""
        with self._stats_lock:
            return self._cached_stats.copy()


class SyncBackendWorker(BaseBackendWorker):
    """Synchronous polling worker running in a dedicated QThread."""

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._error_count = 0
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._poll_loop)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _poll_loop(self) -> None:
        while self._running:
            self._poll()
            self._thread.msleep(self._poll_interval * 1000)

    def _poll(self) -> None:
        try:
            stats = self.aria2.get_global_stat()
            with self._stats_lock:
                self._cached_stats = stats
            self.stats_updated.emit(stats)
            # Reset error counter on success
            self._error_count = 0
        except Exception as e:
            self._error_count += 1
            logger.error("Poll error (attempt %d/%d): %s", self._error_count, self._max_errors, e)
            if self._error_count >= self._max_errors:
                error_msg = f"Too many polling errors ({self._error_count}), stopping worker"
                logger.critical(error_msg)
                self.error_occurred.emit(error_msg)
                self.stop()
            else:
                self.error_occurred.emit(f"Poll error: {e}")

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
        logger.info("Sync worker stopped")


class AsyncBackendWorker(BaseBackendWorker):
    """Asynchronous polling worker using asyncio."""

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._error_count = 0
        self._thread = QThread()
        self.moveToThread(self._thread)
        self._thread.started.connect(self._poll_loop)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _poll_loop(self) -> None:
        try:
            asyncio.run(self._async_poll_loop())
        except asyncio.CancelledError:
            logger.info("Async poll loop cancelled")
        except Exception as e:
            logger.error("Async poll loop crashed: %s", e)

    async def _async_poll_loop(self) -> None:
        while self._running:
            try:
                stats = await self.async_aria2.get_global_stat()
                if stats is not None:
                    with self._stats_lock:
                        self._cached_stats = stats
                    self.stats_updated.emit(stats)
                    # Reset error counter on success
                    self._error_count = 0
            except asyncio.CancelledError:
                logger.info("Async poll loop cancelled internally")
                break
            except Exception as e:
                self._error_count += 1
                logger.error("Async poll error (attempt %d/%d): %s", self._error_count, self._max_errors, e)
                if self._error_count >= self._max_errors:
                    error_msg = f"Too many async poll errors ({self._error_count}), stopping worker"
                    logger.critical(error_msg)
                    self.error_occurred.emit(error_msg)
                    self.stop()
                    break
                else:
                    self.error_occurred.emit(f"Async poll error: {e}")
            for _ in range(self._poll_interval * 10):
                if not self._running:
                    break
                await asyncio.sleep(0.1)

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
        logger.info("Async worker stopped")


# Alias for backward compatibility
BackendWorker = SyncBackendWorker
