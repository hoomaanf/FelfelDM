# core/size_fetcher_worker.py

"""
Background worker for fetching file sizes from multiple URLs in parallel.

Uses the exact same FileSizeFetcher logic as the rest of the application:
    HEAD -> RANGE -> STREAM -> yt-dlp

Each URL gets its own FileSizeFetcher instance/session.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt6.QtCore import QThread, pyqtSignal

from core.file_size_fetcher import FileSizeFetcher


class SizeFetcherWorker(QThread):
    """
    Fetch file sizes for multiple URLs in parallel.

    Signals:
        size_fetched(url, size):
            Emitted when the file size is successfully detected.
            NOTE: `size` is emitted as qint64 to avoid 32-bit overflow
            for files larger than 2 GiB.

        fetch_failed(url, error):
            Emitted when the file size cannot be detected.

        progress(done, total):
            Emitted after each completed URL.

        all_done():
            Emitted when all URLs have finished processing.
    """

    # ⚠️ IMPORTANT: use qint64 instead of int, because Qt's `int` is 32-bit
    # and any file larger than 2 GiB would overflow into a negative number.
    size_fetched = pyqtSignal(str, "qint64")
    fetch_failed = pyqtSignal(str, str)
    progress = pyqtSignal(int, int)
    all_done = pyqtSignal()

    DEFAULT_MAX_WORKERS = 5
    DEFAULT_TIMEOUT = FileSizeFetcher.DEFAULT_TIMEOUT

    def __init__(
        self,
        urls,
        timeout: int = DEFAULT_TIMEOUT,
        proxy: dict = None,
        max_workers: int = DEFAULT_MAX_WORKERS,
        parent=None,
    ):
        super().__init__(parent)

        self.urls = list(urls)
        self.timeout = timeout
        self.proxy = proxy
        self.max_workers = max_workers

        self._cancelled = False

    def cancel(self):
        """Request cancellation."""
        self._cancelled = True
        self.requestInterruption()

    def _fetch_one(self, url: str):
        """
        Fetch one URL using the exact FileSizeFetcher implementation.

        A separate fetcher/session is used for every URL because this method
        runs concurrently in different threads.
        """
        fetcher = FileSizeFetcher(
            timeout=self.timeout,
            proxy=self.proxy,
        )

        try:
            size = fetcher.get_size(url)

            if size is not None and size > 0:
                # Python int has arbitrary precision, so values > 2 GiB
                # are preserved without 32-bit overflow.
                return int(size)

            return None

        finally:
            fetcher.close()

    def run(self):
        total = len(self.urls)

        if total == 0:
            self.all_done.emit()
            return

        completed = 0

        try:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:

                future_to_url = {
                    executor.submit(self._fetch_one, url): url for url in self.urls
                }

                for future in as_completed(future_to_url):

                    url = future_to_url[future]

                    # Don't emit new results after cancellation.
                    if self._cancelled or self.isInterruptionRequested():
                        break

                    try:
                        size = future.result()

                        if size is not None and size > 0:
                            self.size_fetched.emit(url, int(size))
                        else:
                            self.fetch_failed.emit(
                                url,
                                "Unknown size",
                            )

                    except Exception as e:
                        self.fetch_failed.emit(
                            url,
                            str(e),
                        )

                    completed += 1
                    self.progress.emit(
                        completed,
                        total,
                    )

        finally:
            self.all_done.emit()
