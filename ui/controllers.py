# =============================================================================
# ui/controllers.py
# =============================================================================
import asyncio
import logging
from typing import Optional, List

from PyQt6.QtCore import QObject, pyqtSignal

from core.data_store import DataStore
from core.queue_model import Queue
from core.worker import BackendWorker

logger = logging.getLogger(__name__)


class QueueController(QObject):
    """Controller for managing download queues."""
    queue_added = pyqtSignal(Queue)
    queue_removed = pyqtSignal(str)  # queue id
    queue_updated = pyqtSignal(Queue)

    def __init__(self, store: DataStore, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._store = store

    def add_queue(self, queue: Queue) -> None:
        """Add a new queue and save."""
        self._store.add_queue(queue)
        self.queue_added.emit(queue)

    def remove_queue(self, queue_id: str) -> None:
        """Remove a queue by id."""
        self._store.remove_queue(queue_id)
        self.queue_removed.emit(queue_id)

    def update_queue(self, queue: Queue) -> None:
        """Update an existing queue."""
        self._store.update_queue(queue)
        self.queue_updated.emit(queue)

    def get_all_queues(self) -> List[Queue]:
        """Return all queues from store."""
        return self._store.queues

    def get_queue(self, queue_id: str) -> Optional[Queue]:
        """Get a queue by id."""
        return self._store.get_queue(queue_id)


class DownloadController(QObject):
    """Controller for managing download operations."""
    download_added = pyqtSignal(str)  # gid
    download_removed = pyqtSignal(str)  # gid
    download_paused = pyqtSignal(str)
    download_resumed = pyqtSignal(str)

    def __init__(self, worker: BackendWorker, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._worker = worker

    def add_download(self, uri: str, options: Optional[dict] = None) -> Optional[str]:
        """Add a download via the worker."""
        try:
            if uri.startswith("magnet:"):
                coro = self._worker.async_aria2.add_magnet(uri, options)
            else:
                coro = self._worker.async_aria2.add_uri([uri], options)
            gid = asyncio.run(coro)
            if gid:
                self.download_added.emit(gid)
            return gid
        except Exception as e:
            logger.error("Failed to add download: %s", e)
            return None

    def remove_download(self, gid: str) -> bool:
        """Remove a download."""
        try:
            result = asyncio.run(self._worker.async_aria2.remove(gid))
            if result:
                self.download_removed.emit(gid)
            return bool(result)
        except Exception as e:
            logger.error("Failed to remove download: %s", e)
            return False

    def pause_download(self, gid: str) -> bool:
        """Pause a download."""
        try:
            result = asyncio.run(self._worker.async_aria2.pause(gid))
            if result:
                self.download_paused.emit(gid)
            return bool(result)
        except Exception as e:
            logger.error("Failed to pause download: %s", e)
            return False

    def resume_download(self, gid: str) -> bool:
        """Resume a paused download."""
        try:
            result = asyncio.run(self._worker.async_aria2.unpause(gid))
            if result:
                self.download_resumed.emit(gid)
            return bool(result)
        except Exception as e:
            logger.error("Failed to resume download: %s", e)
            return False
