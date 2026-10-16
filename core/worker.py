# core/worker.py

from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal, pyqtSlot, Qt
from typing import Dict, Optional, List, Set
from concurrent.futures import ThreadPoolExecutor
import threading
import uuid
from datetime import datetime
import os
import re
import glob
import time

from core.youtube_worker import YouTubeWorker
from core.data_store import DataStore


def _redact_proxy_url(url: str) -> str:
    """Strip credentials from a proxy URL before it reaches the log.

    A proxy URL can embed user:password@, and the log is both written to
    disk and displayed in the log viewer.
    """
    if not url or "@" not in url:
        return url
    try:
        scheme, rest = url.split("://", 1) if "://" in url else ("", url)
        _creds, host = rest.rsplit("@", 1)
        prefix = f"{scheme}://" if scheme else ""
        return f"{prefix}***:***@{host}"
    except Exception:
        return "***"


class BackendWorker(QThread):

    stats_updated = pyqtSignal(dict)
    aria2_error = pyqtSignal(str)
    size_fetched = pyqtSignal(str, object, str)
    remove_multi_requested = pyqtSignal(list)

    resume_requested = pyqtSignal(str)
    pause_requested = pyqtSignal(str)
    pause_multi_requested = pyqtSignal(list)
    resume_multi_requested = pyqtSignal(list)
    remove_requested = pyqtSignal(str)
    add_url_requested = pyqtSignal(str, dict)
    re_add_requested = pyqtSignal(str)
    set_speed_limit_requested = pyqtSignal(str, int)
    set_speed_limit_multi_requested = pyqtSignal(list, int)
    save_session_requested = pyqtSignal()
    shutdown_requested = pyqtSignal()

    operation_result = pyqtSignal(str, object)

    youtube_progress = pyqtSignal(str, int)
    youtube_status = pyqtSignal(str, str)
    youtube_speed = pyqtSignal(str, str, str)
    youtube_finished = pyqtSignal(str, bool, str)
    youtube_size_fetched = pyqtSignal(str, int)

    def __init__(self, aria2, store: DataStore, proxy_manager=None):
        super().__init__()
        self.aria2 = aria2
        self.store = store
        self.proxy_manager = proxy_manager
        self.running = True

        self._fetching_sizes: Set[str] = set()
        self._fetched_sizes: Set[str] = set()
        self._failed_sizes: Dict[str, float] = {}

        self._size_executor = ThreadPoolExecutor(
            max_workers=5, thread_name_prefix="SizeFetch"
        )

        self.remove_multi_requested.connect(
            self._on_remove_multi_requested, Qt.ConnectionType.QueuedConnection
        )
        self.youtube_workers: Dict[str, YouTubeWorker] = {}
        self.youtube_downloads: Dict[str, dict] = {}
        self.youtube_lock = threading.Lock()
        self.youtube_gids: Set[str] = set()
        self._size_workers: Dict[str, YouTubeWorker] = {}

        self.resume_requested.connect(
            self._on_resume_requested, Qt.ConnectionType.QueuedConnection
        )
        self.pause_requested.connect(
            self._on_pause_requested, Qt.ConnectionType.QueuedConnection
        )
        self.pause_multi_requested.connect(
            self._on_pause_multi_requested, Qt.ConnectionType.QueuedConnection
        )
        self.resume_multi_requested.connect(
            self._on_resume_multi_requested, Qt.ConnectionType.QueuedConnection
        )
        self.remove_requested.connect(
            self._on_remove_requested, Qt.ConnectionType.QueuedConnection
        )
        self.add_url_requested.connect(
            self._on_add_url_requested, Qt.ConnectionType.QueuedConnection
        )
        self.re_add_requested.connect(
            self._on_re_add_requested, Qt.ConnectionType.QueuedConnection
        )
        self.set_speed_limit_requested.connect(
            self._on_set_speed_limit, Qt.ConnectionType.QueuedConnection
        )
        self.set_speed_limit_multi_requested.connect(
            self._on_set_speed_limit_multi, Qt.ConnectionType.QueuedConnection
        )
        self.save_session_requested.connect(
            self._on_save_session, Qt.ConnectionType.QueuedConnection
        )
        self.shutdown_requested.connect(
            self._on_shutdown, Qt.ConnectionType.QueuedConnection
        )

        self._load_youtube_downloads()

    def _yt_verify_ssl(self) -> bool:
        """Certificate verification for yt-dlp, following the user setting.

        Defaults to verifying; only the explicit "disable SSL verify"
        setting turns it off.
        """
        try:
            return not self.store.settings.get("disable_ssl_verify", False)
        except Exception:
            return True

    def _load_youtube_downloads(self):
        """Load YouTube downloads from datastore"""
        try:
            youtube_items = self.store.get_all_youtube_downloads()
            for item in youtube_items:
                download_id = item.get("id")
                if download_id:
                    self.youtube_downloads[download_id] = item
                    self.youtube_gids.add(download_id)

                    status = item.get("status", "")
                    print(
                        f"📁 Loading YouTube download: {download_id} - status: {status}"
                    )

                    if status in ["completed", "cancelled"]:
                        self.store.delete_youtube_download(download_id)
                        if download_id in self.youtube_downloads:
                            del self.youtube_downloads[download_id]
                        self.youtube_gids.discard(download_id)
                        print(f"🗑️ Removed completed/cancelled download: {download_id}")
                        continue

                    if status in ["downloading", "paused"]:
                        self.youtube_downloads[download_id]["status"] = "paused"
                        self.store.update_youtube_status(download_id, "paused")
                        print(f"⏸️ Set download to paused: {download_id}")

            self._cleanup_completed_downloads()
            print(f"📁 Loaded {len(self.youtube_downloads)} active YouTube downloads")

        except Exception as e:
            print(f"Error loading YouTube downloads: {e}")
            import traceback

            traceback.print_exc()

    def _cleanup_completed_downloads(self):
        """Clean up completed and cancelled downloads from datastore"""
        try:
            all_downloads = self.store.get_all_youtube_downloads()
            for item in all_downloads:
                download_id = item.get("id")
                status = item.get("status", "")
                if status in ["completed", "cancelled"]:
                    self.store.delete_youtube_download(download_id)
                    print(f"🗑️ Cleaned up completed/cancelled: {download_id}")
        except Exception as e:
            print(f"Error cleaning up downloads: {e}")

    def run(self):
        """Main polling loop - builds complete runtime snapshot of all downloads"""
        while self.running:
            try:
                if not self.aria2.is_connected():
                    if not self.aria2.start_aria2():
                        self.stats_updated.emit({"connected": False})
                        self.msleep(300)
                        continue

                snapshot = self._build_runtime_snapshot()
                self.stats_updated.emit(snapshot)

            except Exception as e:
                self.aria2_error.emit(str(e))
                self.stats_updated.emit({"connected": False})

            self.msleep(300)

    def stop(self):
        """Stop the worker loop and all child threads.

        This is called from the UI thread during quit_app, so it must
        return in a bounded amount of time — otherwise the shutdown
        splash freezes on screen.
        """
        self.running = False

        # Cancel YouTube workers (bounded: each has a 3s wait timeout).
        try:
            self._stop_all_youtube_downloads()
        except Exception as e:
            print(f"⚠️ Error stopping YouTube workers: {e}")

        # Stop size-fetcher workers (bounded: 1s per worker).
        try:
            self._stop_all_size_workers()
        except Exception as e:
            print(f"⚠️ Error stopping size workers: {e}")

        # Shut down the size-fetch thread pool. cancel_futures drops
        # queued tasks immediately; running tasks finish within their
        # own timeout (FileSizeFetcher uses a 30s timeout, so this is
        # the worst case — but in practice most fetches complete or
        # fail fast).
        try:
            self._size_executor.shutdown(wait=True, cancel_futures=True)
        except TypeError:
            # Python < 3.9 fallback (no cancel_futures).
            self._size_executor.shutdown(wait=True)
        except Exception as e:
            print(f"⚠️ Error shutting down size executor: {e}")

        # Wait for the run() loop to notice running=False and exit.
        if not self.wait(3000):
            print("⚠️ [BackendWorker] stop: thread didn't exit in 3s, " "terminating")
            self.terminate()
            self.wait(1000)

    def _build_gid_to_download_id_map(self) -> Dict[str, str]:

        mapping: Dict[str, str] = {}
        for q in self.store.queues:
            for download_id, info in q.downloads_info.items():
                aria2_gid = info.get("aria2_gid")
                if aria2_gid:
                    mapping[aria2_gid] = download_id
        return mapping

    def _build_runtime_snapshot(self) -> dict:
        active = self.aria2.tell_active() or []
        waiting = self.aria2.tell_waiting() or []
        stopped = self.aria2.tell_stopped(0, 300) or []

        all_downloads = active + waiting + stopped

        # ⭐ ساخت set از GIDهای waiting
        waiting_gids = {dl.get("gid") for dl in waiting if dl.get("gid")}

        downloads_snapshot = []
        seen_gids = set()

        gid_to_download_id = self._build_gid_to_download_id_map()
        valid_gids = set(gid_to_download_id.keys())

        for q in self.store.queues:
            for item in q.downloads:
                valid_gids.add(item)
                if item in q.downloads_info:
                    info = q.downloads_info[item]
                    aria2_gid = info.get("aria2_gid")
                    if aria2_gid:
                        valid_gids.add(aria2_gid)

        for download in all_downloads:
            gid = download.get("gid")
            if not gid or gid in seen_gids:
                continue
            seen_gids.add(gid)

            if gid not in valid_gids:
                if gid in self._fetching_sizes or gid in self._fetched_sizes:
                    continue

                try:
                    self.aria2.remove(gid)
                    try:
                        self.aria2._call("aria2.removeDownloadResult", [gid])
                    except Exception:
                        pass
                except Exception:
                    pass
                continue

            complete_info = self._get_complete_download_info(gid, download)
            if complete_info:
                if gid in waiting_gids:
                    complete_info["status"] = "waiting"
                    complete_info["downloadSpeed"] = "0"

                complete_info["download_id"] = gid_to_download_id.get(gid)
                downloads_snapshot.append(complete_info)

        try:
            youtube_status = self._get_youtube_status()
            if not isinstance(youtube_status, list):
                youtube_status = []
        except Exception as e:
            print(f"⚠️ [Worker] Error getting youtube status: {e}")
            youtube_status = []

        snapshot = {
            "connected": True,
            "stat": self.aria2.get_global_stat() or {},
            "downloads": downloads_snapshot,
            "active": active,
            "waiting": waiting,
            "stopped": stopped,
            "youtube_downloads": youtube_status,
        }

        return snapshot

    def _get_complete_download_info(
        self, gid: str, partial_info: dict
    ) -> Optional[dict]:

        try:
            full_info = partial_info
            complete_info = {
                "gid": gid,
                "status": full_info.get("status", "unknown"),
                "totalLength": full_info.get("totalLength", "0"),
                "completedLength": full_info.get("completedLength", "0"),
                "downloadSpeed": full_info.get("downloadSpeed", "0"),
                "files": full_info.get("files", []),
                "connections": full_info.get("connections", "0"),
                "errorMessage": full_info.get("errorMessage", ""),
            }
            optional_fields = [
                "uploadLength",
                "uploadSpeed",
                "bitfield",
                "bittorrent",
                "verifiedLength",
                "verifyIntegrityPending",
                "seeder",
                "numSeeders",
                "pieceLength",
                "totalPieces",
                "dir",
                "infoHash",
                "numPieces",
            ]
            for field in optional_fields:
                if field in full_info:
                    complete_info[field] = full_info[field]

            if complete_info.get("totalLength") == "0" and complete_info.get(
                "status"
            ) in ("active", "waiting", "paused"):
                if (
                    gid not in self.youtube_gids
                    and gid not in self._fetching_sizes
                    and gid not in self._fetched_sizes
                ):
                    files = complete_info.get("files", [])
                    url = None
                    if files and files[0].get("uris"):
                        uris = files[0].get("uris", [])
                        if uris and uris[0].get("uri"):
                            url = uris[0].get("uri")
                    if url:
                        # _fetch_size_for_gid handles adding to
                        # _fetching_sizes and cleaning up on every exit
                        # path. Adding here would leak the gid if that
                        # function returns early for any reason.
                        self._fetch_size_for_gid(gid, url)

            return complete_info

        except Exception as e:
            print(f"⚠️ Error getting complete info for {gid}: {e}")
            return {
                "gid": gid,
                "status": partial_info.get("status", "unknown"),
                "totalLength": partial_info.get("totalLength", "0"),
                "completedLength": partial_info.get("completedLength", "0"),
                "downloadSpeed": partial_info.get("downloadSpeed", "0"),
                "files": partial_info.get("files", []),
                "connections": partial_info.get("connections", "0"),
                "errorMessage": partial_info.get("errorMessage", ""),
            }

    def _get_youtube_status(self) -> List[dict]:
        status_list = []
        try:
            with self.youtube_lock:
                for download_id, info in self.youtube_downloads.items():
                    status_list.append(
                        {
                            "id": download_id,
                            "url": info.get("url", ""),
                            "title": info.get("yt_options", {}).get("title", ""),
                            "status": info.get("status", "pending"),
                            "progress": info.get("progress", 0),
                            "speed": info.get("speed", ""),
                            "eta": info.get("eta", ""),
                            "total_size": info.get("total_size", 0),
                        }
                    )
        except Exception as e:
            print(f"⚠️ [Worker] Error getting youtube status: {e}")
            return []
        return status_list

    def _fetch_size_for_gid(self, gid: str, url: str):
        """
        Queue a size-fetch task to the parallel executor.
        The actual work is done in _fetch_size_worker (runs in a thread pool).

        Resolves the owning download_id + queue_name so the worker can pick
        the correct proxy (download > queue > global) when fetching the size.

        C24 fix:
        - The gid is claimed in _fetching_sizes BEFORE any early-return
          check, so a poll that races with a previous fetch cannot
          re-submit the same gid.
        - A try/finally releases the claim on every exit path EXCEPT the
          successful submit. When submit succeeds, _fetch_size_worker's
          own finally is responsible for the release, so the claim stays
          held for the full lifetime of the fetch.
        """
        # Atomically claim the gid. If someone else already claimed it
        # (or already fetched it), do nothing.
        if gid in self._fetching_sizes or gid in self._fetched_sizes:
            return
        self._fetching_sizes.add(gid)

        submitted = False
        try:
            # Skip recently-failed gids (5-minute cooldown).
            failed_at = self._failed_sizes.get(gid)
            if failed_at is not None:
                if time.time() - failed_at < 300.0:
                    return
                # Cooldown expired: forget the previous failure and retry.
                del self._failed_sizes[gid]

            if gid in self.youtube_gids:
                return

            # Resolve the download_id and queue_name that own this gid.
            download_id = None
            queue_name = None
            for q in self.store.queues:
                for dl_id, info in q.downloads_info.items():
                    if dl_id == gid or info.get("aria2_gid") == gid:
                        download_id = dl_id
                        queue_name = q.name
                        break
                if download_id:
                    break

            # If we already know the size in storage, emit it and skip.
            if download_id and queue_name:
                for q in self.store.queues:
                    if q.name != queue_name:
                        continue
                    existing_size = q.downloads_info.get(download_id, {}).get(
                        "totalLength", 0
                    )
                    if existing_size > 0:
                        self._fetched_sizes.add(gid)
                        print(
                            f"⏭️ [Worker] Size exists in storage for {gid}: "
                            f"{existing_size}, skipping fetch"
                        )
                        from utils.helpers import get_category_from_filename

                        filename = q.downloads_info[download_id].get("name", "")
                        if not filename:
                            filename = url.split("/")[-1].split("?")[0]
                        category = get_category_from_filename(filename)
                        self.size_fetched.emit(gid, existing_size, category)
                        return
                    break

            # Submit to executor. On success, _fetch_size_worker will
            # release the claim in its own finally.
            self._size_executor.submit(
                self._fetch_size_worker,
                gid,
                url,
                download_id,
                queue_name,
            )
            submitted = True

        except RuntimeError as e:
            print(f"⚠️ [Worker] Size executor is shut down: {e}")
        except Exception as e:
            print(f"⚠️ [Worker] _fetch_size_for_gid failed for {gid}: {e}")
        finally:
            if not submitted:
                # Early return or submit failure: release the claim so a
                # future call (after the cooldown) can retry.
                self._fetching_sizes.discard(gid)
    def _fetch_size_worker(
        self,
        gid: str,
        url: str,
        download_id: str = None,
        queue_name: str = None,
    ):
        """
        Runs in a thread pool. Fetches the size for one URL using
        FileSizeFetcher (HEAD -> RANGE -> STREAM -> yt-dlp).

        Uses the effective proxy for this download (download > queue > global)
        so that size fetching works on servers only reachable via proxy.
        """
        try:
            from core.file_size_fetcher import FileSizeFetcher
            from utils.helpers import get_category_from_filename

            # Resolve proxy for this fetch.
            proxy_dict = None
            if self.proxy_manager is not None:
                try:
                    proxy_dict = self.proxy_manager.get_effective_proxy_dict(
                        download_id=download_id,
                        queue_name=queue_name,
                    )
                except Exception as e:
                    print(f"⚠️ [Worker] Could not resolve proxy for {gid}: {e}")
                    proxy_dict = None

            print(
                f"📏 [Worker] Fetching size for {gid}: {url} "
                f"(proxy={'yes' if proxy_dict else 'no'})"
            )

            fetcher = FileSizeFetcher(timeout=30, proxy=proxy_dict)
            try:
                size = fetcher.get_size(url)
            finally:
                fetcher.close()

            if size is not None and size < 0:
                size = size & 0xFFFFFFFF
                print(f"🔄 [Size] Converted negative to unsigned: {size}")

            if size and size > 0:
                self._fetched_sizes.add(gid)
                self._failed_sizes.pop(gid, None)

                filename = None
                for q in self.store.queues:
                    if download_id and download_id in q.downloads_info:
                        filename = q.downloads_info[download_id].get("name", "")
                        break
                    if gid in q.downloads_info:
                        filename = q.downloads_info[gid].get("name", "")
                        break
                if not filename:
                    filename = url.split("/")[-1].split("?")[0]
                category = get_category_from_filename(filename)

                self.size_fetched.emit(gid, size, category)
                print(
                    f"✅ [BackendWorker] Size fetched for {gid}: "
                    f"{size} bytes ({size/1024/1024/1024:.2f} GB)"
                )
            else:
                print(f"⚠️ [Worker] Could not fetch size for {gid}")
                self._failed_sizes[gid] = time.time()

        except Exception as e:
            import traceback

            traceback.print_exc()
            self._failed_sizes[gid] = time.time()
        finally:
            self._fetching_sizes.discard(gid)

    @pyqtSlot(str)
    def _on_resume_requested(self, gid: str):
        try:
            self.aria2.resume(gid)
            print(f"▶️ [Worker] Resumed {gid}")
        except Exception as e:
            print(f"⚠️ [Worker] Resume failed for {gid}: {e}")

    @pyqtSlot(str)
    def _on_pause_requested(self, gid: str):
        try:
            self.aria2.pause(gid)
            print(f"⏸️ [Worker] Paused {gid}")
        except Exception as e:
            print(f"⚠️ [Worker] Pause failed for {gid}: {e}")

    @pyqtSlot(list)
    def _on_remove_multi_requested(self, gids: list):
        """Remove multiple downloads in one batch (best-effort)."""
        try:
            if hasattr(self.aria2, "remove_multi"):
                self.aria2.remove_multi(gids)
                print(f"🗑️ [Worker] Removed {len(gids)} download(s) in one round trip")
            else:
                for gid in gids:
                    try:
                        self.aria2.remove(gid)
                    except Exception:
                        pass
                print(f"🗑️ [Worker] Removed {len(gids)} download(s) individually")

            try:
                if hasattr(self.aria2, "purge_download_result"):
                    self.aria2.purge_download_result()
                else:
                    for gid in gids:
                        try:
                            self.aria2._call("aria2.removeDownloadResult", [gid])
                        except Exception:
                            pass
            except Exception:
                pass

        except Exception as e:
            print(f"⚠️ [Worker] Bulk remove failed: {e}")

    @pyqtSlot(list)
    def _on_pause_multi_requested(self, gids: list):
        try:
            self.aria2.pause_multi(gids)
            print(f"⏸️ [Worker] Paused {len(gids)} download(s) in one round trip")
        except Exception as e:
            print(f"⚠️ [Worker] Bulk pause failed: {e}")

    @pyqtSlot(list)
    def _on_resume_multi_requested(self, gids: list):
        try:
            self.aria2.resume_multi(gids)
            print(f"▶️ [Worker] Resumed {len(gids)} download(s) in one round trip")
        except Exception as e:
            print(f"⚠️ [Worker] Bulk resume failed: {e}")

    @pyqtSlot(str)
    def _on_remove_requested(self, gid: str):
        try:
            self.aria2.remove(gid)
            print(f"🗑️ [Worker] Removed {gid}")
        except Exception as e:
            print(f"⚠️ [Worker] Remove failed for {gid}: {e}")

    @pyqtSlot(str, dict)
    def _on_add_url_requested(self, url: str, options: dict):
        try:
            new_gid = self.aria2.add_url(url, options)
            self.operation_result.emit("add_url", new_gid)
            print(f"➕ [Worker] Added URL: {url} -> {new_gid}")
        except Exception as e:
            print(f"⚠️ [Worker] Add URL failed: {e}")
            self.operation_result.emit("add_url", None)

    @pyqtSlot(str)
    def _on_re_add_requested(self, download_id_or_gid: str):
        """Re-add a download to aria2 after a failure.

        C5 fix: read every option the user originally configured from
        downloads_info, instead of hardcoding split=8 / conn=8 and
        losing the header, connections, speed limit, matched rule,
        proxy, etc. The goal is for the re-added download to look
        identical to the original add.
        """
        try:
            url = None
            save_path = None
            matched_id = None
            info = None
            owning_queue = None

            def _report(new_gid=None, error=None):
                # Always tell the UI WHICH download this result is for, so
                # concurrent retries can't be attributed to the wrong one.
                self.operation_result.emit(
                    "re_add",
                    {
                        "id": matched_id or download_id_or_gid,
                        "new": new_gid,
                        "success": new_gid is not None,
                        "error": error,
                    },
                )

            # ── 1. Locate the download in any queue ──
            # First try as a download_id, then fall back to matching
            # aria2_gid. This covers both modern and legacy ids.
            for q in self.store.queues:
                if download_id_or_gid in q.downloads_info:
                    info = q.downloads_info[download_id_or_gid]
                    matched_id = download_id_or_gid
                    owning_queue = q
                    break

            if info is None:
                for q in self.store.queues:
                    for dl_id, d_info in q.downloads_info.items():
                        if d_info.get("aria2_gid") == download_id_or_gid:
                            info = d_info
                            matched_id = dl_id
                            owning_queue = q
                            break
                    if info is not None:
                        break

            if info is None:
                print(
                    f"❌ [Worker] Cannot re-add: no info for "
                    f"{download_id_or_gid}"
                )
                _report(error="missing download info")
                return

            url = info.get("url")
            save_path = info.get("save_path") or (
                owning_queue.save_path if owning_queue else None
            )

            if not url or not save_path:
                print(
                    f"❌ [Worker] Cannot re-add: missing url or save_path "
                    f"for {download_id_or_gid}"
                )
                _report(error="missing url or save_path")
                return

            # ── 2. Rebuild options from the persisted settings ──
            # Every field below was stored by _process_add_download_common
            # at add time. Defaults are chosen to match the add path so
            # old entries without these fields behave the same.
            connections = int(info.get("connections") or 8)
            min_split_size = info.get("min_split_size") or "1M"
            stream_piece_selector = info.get("stream_piece_selector") or "geom"
            header = info.get("header") or []

            options = {
                "dir": save_path,
                "split": str(connections),
                "max-connection-per-server": str(connections),
                "min-split-size": min_split_size,
                "stream-piece-selector": stream_piece_selector,
                "continue": "true",
                "always-resume": "true",
                "pause": "false",
            }

            # Re-apply the original header (User-Agent, cookies, referer…)
            if header:
                options["header"] = list(header)

            # Per-download speed limit (overrides queue speed limit).
            # If absent, fall back to the queue's speed limit.
            per_download_speed = int(info.get("speed_limit") or 0)
            queue_speed = getattr(owning_queue, "speed_limit", 0) if owning_queue else 0
            effective_speed = per_download_speed or queue_speed
            if effective_speed > 0:
                options["max-download-limit"] = f"{effective_speed}K"

            # ── 3. Re-apply the proxy (download > queue > global) ──
            if self.proxy_manager is not None and matched_id:
                queue_name_for_proxy = owning_queue.name if owning_queue else None
                proxy_dict = None
                try:
                    proxy_dict = self.proxy_manager.get_effective_proxy_dict(
                        download_id=matched_id,
                        queue_name=queue_name_for_proxy,
                    )
                except Exception as e:
                    print(
                        f"⚠️ [Worker] Could not resolve proxy for re-add "
                        f"{matched_id[:12]}: {e}"
                    )
                    proxy_dict = None

                if proxy_dict:
                    proxy_url = proxy_dict.get("https") or proxy_dict.get("http")
                    if proxy_url:
                        options["all-proxy"] = proxy_url
                        # Never log verbatim: may embed user:password@.
                        print(
                            "🌐 [Worker] Re-add with proxy: "
                            f"{_redact_proxy_url(proxy_url)}"
                        )
                else:
                    print(
                        f"🌐 [Worker] Re-add without proxy for "
                        f"{matched_id[:12]}"
                    )

            # ── 4. Submit ──
            new_gid = self.aria2.add_url(url, options)
            if new_gid:
                id_short = (
                    matched_id[:12] if matched_id else download_id_or_gid[:12]
                )
                print(
                    f"🔄 [Worker] Re-added id={id_short} -> gid={new_gid} "
                    f"(conn={connections}, speed={effective_speed}K, "
                    f"proxy={'yes' if 'all-proxy' in options else 'no'}, "
                    f"header={'yes' if header else 'no'})"
                )
                _report(new_gid=new_gid)
            else:
                _report(error="aria2 rejected add_url")
        except Exception as e:
            print(f"⚠️ [Worker] Re-add failed: {e}")
            _report(error=str(e))
    @pyqtSlot(str, int)
    def _on_set_speed_limit(self, gid: str, speed_kb: int):
        try:
            limit = "0" if speed_kb <= 0 else f"{speed_kb}K"
            self.aria2.change_option(gid, {"max-download-limit": limit})
            print(f"⚡ [Worker] Speed limit set for {gid}: {limit}")
        except Exception as e:
            print(f"⚠️ [Worker] Set speed limit failed: {e}")

    @pyqtSlot(list, int)
    def _on_set_speed_limit_multi(self, gids: list, speed_kb: int):
        try:
            self.aria2.set_speed_limit_multi(gids, speed_kb)
            print(f"⚡ [Worker] Speed limit set for {len(gids)} download(s)")
        except Exception as e:
            print(f"⚠️ [Worker] Bulk set speed limit failed: {e}")

    @pyqtSlot()
    def _on_save_session(self):
        try:
            self.aria2.save_session()
            print(f"💾 [Worker] Session saved")
        except Exception as e:
            print(f"⚠️ [Worker] Save session failed: {e}")

    @pyqtSlot()
    def _on_shutdown(self):
        try:
            self.aria2.shutdown()
            print(f"🛑 [Worker] aria2 shutdown")
        except Exception as e:
            print(f"⚠️ [Worker] Shutdown failed: {e}")

    def add_youtube_download(self, download_data: dict) -> str:
        download_id = download_data.get("id") or str(uuid.uuid4())
        existing = self.store.get_youtube_download(download_id)
        if existing:
            requested_status = download_data.get("status")

            print(f"📦 [ADD] Download already exists: {download_id}")
            with self.youtube_lock:
                # Merge the persisted record into memory, but never let a
                # stale persisted status override an explicit one from the
                # caller. A queue Start re-adds an item that the store still
                # has marked "paused" (it was only flipped in the UI), so
                # copying that status verbatim made _start_youtube_download
                # bail out and the download never actually began.
                merged = dict(existing)
                if requested_status:
                    merged["status"] = requested_status
                self.youtube_downloads[download_id] = merged
                self.youtube_gids.add(download_id)
                total_size = merged.get("total_size", 0)
                status = merged.get("status", "paused")

            # An explicit start request always means "run this now".
            if status == "downloading":
                if total_size > 0:
                    self._start_youtube_download(download_id)
                else:
                    self._fetch_youtube_size(download_id)
            return download_id

        download_item = {
            "id": download_id,
            "url": download_data["url"],
            "save_path": download_data["save_path"],
            "download_type": "youtube",
            "status": "paused",
            "progress": 0,
            "speed": "",
            "eta": "",
            "total_size": 0,
            "yt_options": download_data.get("yt_options", {}),
            "proxy": download_data.get("proxy"),
            "queue_id": download_data.get("queue_id"),
            "created_at": datetime.now().isoformat(),
            "completed_at": None,
            "error_message": "",
        }
        self.store.add_youtube_download(download_item)
        with self.youtube_lock:
            self.youtube_downloads[download_id] = download_item
            self.youtube_gids.add(download_id)
        self._fetch_youtube_size(download_id)
        return download_id

    def _fetch_youtube_size(self, download_id: str):
        with self.youtube_lock:
            if download_id not in self.youtube_downloads:
                return
            item = self.youtube_downloads[download_id]
            if item.get("total_size", 0) > 0:
                return
            url = item["url"]
            save_path = item["save_path"]
            format_type = item.get("yt_options", {}).get("format", "mp4")
            cookie_file = item.get("yt_options", {}).get("cookies_path")
            proxy_url = item.get("proxy")

        format_id = item.get("yt_options", {}).get("format_id")
        quality = item.get("yt_options", {}).get("quality", "best")
        yt_opts = item.get("yt_options", {})
        size_worker = YouTubeWorker(
            url=url,
            output_path=save_path,
            format_type=format_type,
            cookie_file=cookie_file,
            proxy_url=proxy_url,
            format_id=format_id,
            quality=quality,
            format_spec=yt_opts.get("format_spec"),
            title=yt_opts.get("title"),
            download_id=download_id,
            verify_ssl=self._yt_verify_ssl(),
        )

        size_worker.size_fetched.connect(
            lambda size: self._on_youtube_size_fetched(download_id, size)
        )
        size_worker.is_fetching_size = True
        size_worker.start()
        self._size_workers[download_id] = size_worker
        print(f"📏 [SIZE] Worker started for: {download_id}")

    def _on_youtube_size_fetched(self, download_id: str, size: int):
        print(f"📏 [SIZE] Received size for {download_id}: {size} bytes")

        should_auto_start = False
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                item = self.youtube_downloads[download_id]
                self.youtube_downloads[download_id]["total_size"] = size

                current_status = item.get("status", "paused")
                worker_exists = download_id in self.youtube_workers

                if current_status == "downloading" and not worker_exists:
                    should_auto_start = True
                    self.store.update_youtube_download(
                        download_id,
                        {"total_size": size},
                    )
                else:
                    self.youtube_downloads[download_id]["status"] = "paused"
                    self.store.update_youtube_download(
                        download_id,
                        {"total_size": size, "status": "paused"},
                    )

        self.youtube_size_fetched.emit(download_id, size)

        if should_auto_start:
            print(f"🎬 [SIZE] Auto-starting download after size fetch: {download_id}")
            self._start_youtube_download(download_id)

        if download_id in self._size_workers:
            try:
                worker = self._size_workers[download_id]
                if worker.isRunning():
                    # quit() is a no-op on YouTubeWorker (custom run());
                    # use its cooperative stop instead.
                    worker.stop_for_removal()
            except Exception as e:
                print(f"⚠️ [Worker] Could not stop size worker: {e}")
            self._size_workers.pop(download_id, None)

    def _start_youtube_download(self, download_id: str):
        with self.youtube_lock:
            if download_id not in self.youtube_downloads:
                print(f"❌ [START] download_id not in youtube_downloads")
                return
            item = self.youtube_downloads[download_id]
            total_size = item.get("total_size", 0)
            status = item.get("status", "paused")

            print(f"🔍 [START] total_size={total_size}, status={status}")
            print(f"🔍 [START] worker exists: {download_id in self.youtube_workers}")

            if download_id in self.youtube_workers:
                print(f"⏭️ [START] Worker already exists for {download_id}")
                return

            if total_size == 0:
                print(f"⚠️ [START] total_size is 0, will fetch size")
                pass
            else:
                if status == "completed":
                    print(f"⏭️ [START] Status is completed, skipping")
                    return
                url = item["url"]
                save_path = item["save_path"]
                format_type = item.get("yt_options", {}).get("format", "mp4")
                cookie_file = item.get("yt_options", {}).get("cookies_path")
                proxy_url = item.get("proxy")

        if total_size == 0:
            self._fetch_youtube_size(download_id)
            return

        print(f"🔨 [START] Creating YouTubeWorker for {download_id}")
        format_id = item.get("yt_options", {}).get("format_id")
        quality = item.get("yt_options", {}).get("quality", "best")
        yt_opts = item.get("yt_options", {})
        worker = YouTubeWorker(
            url=url,
            output_path=save_path,
            format_type=format_type,
            cookie_file=cookie_file,
            proxy_url=proxy_url,
            format_id=format_id,
            quality=quality,
            format_spec=yt_opts.get("format_spec"),
            title=yt_opts.get("title"),
            download_id=download_id,
            verify_ssl=self._yt_verify_ssl(),
        )
        worker.progress.connect(lambda p: self._on_youtube_progress(download_id, p))
        worker.status.connect(lambda s: self._on_youtube_status(download_id, s))
        worker.speed_eta.connect(lambda s, e: self._on_youtube_speed(download_id, s, e))
        worker.finished.connect(
            lambda success, msg: self._on_youtube_finished(download_id, success, msg)
        )
        with self.youtube_lock:
            self.youtube_workers[download_id] = worker
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]["status"] = "downloading"
                self.store.update_youtube_status(download_id, "downloading")
        self.youtube_status.emit(download_id, "downloading")
        print(f"▶️ [START] Calling worker.start() for {download_id}")
        worker.start()
        print(f"🎬 YouTube download started: {download_id}")

    def _resume_youtube_download(self, item: dict):
        download_id = item["id"]
        yt_options = item.get("yt_options", {})
        worker = YouTubeWorker(
            url=item["url"],
            output_path=item["save_path"],
            format_type=yt_options.get("format", "mp4"),
            cookie_file=yt_options.get("cookies_path"),
            proxy_url=item.get("proxy"),
            format_id=yt_options.get("format_id"),
            quality=yt_options.get("quality", "best"),
            format_spec=yt_options.get("format_spec"),
            title=yt_options.get("title"),
            download_id=download_id,
            verify_ssl=self._yt_verify_ssl(),
        )
        worker.progress.connect(lambda p: self._on_youtube_progress(download_id, p))
        worker.status.connect(lambda s: self._on_youtube_status(download_id, s))
        worker.speed_eta.connect(lambda s, e: self._on_youtube_speed(download_id, s, e))
        worker.finished.connect(
            lambda success, msg: self._on_youtube_finished(download_id, success, msg)
        )
        self.youtube_workers[download_id] = worker
        item["status"] = "downloading"
        self.store.update_youtube_status(download_id, "downloading")
        worker.start()
        print(f"🎬 YouTube download resumed: {download_id}")

    def pause_youtube_download(self, download_id: str):
        print(f"⏸️ [Worker] Pausing: {download_id}")
        worker = None
        with self.youtube_lock:
            if download_id in self.youtube_workers:
                worker = self.youtube_workers[download_id]
        if worker and worker.is_running():
            worker.pause()
            with self.youtube_lock:
                if download_id in self.youtube_downloads:
                    self.youtube_downloads[download_id]["status"] = "paused"
                    self.store.update_youtube_status(download_id, "paused")
            self.youtube_status.emit(download_id, "paused")

    def resume_youtube_download(self, download_id: str):
        print(f"▶️ [Worker] Resuming: {download_id}")
        worker = None
        with self.youtube_lock:
            if download_id in self.youtube_workers:
                worker = self.youtube_workers[download_id]
        if worker and worker.is_running():
            worker.resume()
            with self.youtube_lock:
                if download_id in self.youtube_downloads:
                    self.youtube_downloads[download_id]["status"] = "downloading"
                    self.store.update_youtube_status(download_id, "downloading")
            self.youtube_status.emit(download_id, "downloading")

    def cancel_youtube_download(self, download_id: str):
        """Cancel a YouTube download and safely remove only its own files.

        C29 fix: the previous implementation unconditionally called
        os.remove(file_path) where file_path was derived from the stored
        title. If a completed download with the same title existed on disk
        (e.g. the user re-added the same video), that file was deleted.
        It also built glob patterns from the title, which are unsafe if the
        title contains glob metacharacters.

        Now: we only ask the YouTubeWorker to clean up (it knows exactly
        which files it produced), and we only remove the final target file
        if we can prove it was created by THIS run — i.e. its mtime is not
        older than the moment this download was started, and it lives
        directly inside save_path.
        """
        print(f"🗑️ [Worker] Cancelling YouTube download: {download_id}")
        worker = None
        save_path = None
        expected_final_path = None
        download_started_at = None

        with self.youtube_lock:
            if download_id in self.youtube_workers:
                worker = self.youtube_workers[download_id]
                del self.youtube_workers[download_id]
            if download_id in self.youtube_downloads:
                item = self.youtube_downloads[download_id]
                yt_options = item.get("yt_options", {})
                title = yt_options.get("title", "Unknown")
                format_type = yt_options.get("format", "video")
                ext = "mp4" if format_type == "video" else "mp3"
                # Sanitize the same way yt-dlp does when it builds filenames.
                safe_title = re.sub(r'[<>:"/\\|?*]', "_", title)
                filename = f"{safe_title}.{ext}"
                save_path = item.get("save_path", "")
                if save_path:
                    expected_final_path = os.path.join(save_path, filename)
                # If we have a creation timestamp, use it to prove the file
                # is from this run.
                created_at = item.get("created_at")
                if created_at:
                    try:
                        from datetime import datetime as _dt

                        download_started_at = _dt.fromisoformat(created_at).timestamp()
                    except Exception:
                        download_started_at = None

        # 1. Let the worker clean up files it produced. This is the
        #    authoritative cleanup — it uses _produced_paths plus a safe
        #    fallback scan anchored to the exact title.
        if worker and worker.is_running():
            worker.cancel()
            worker.wait(1000)

        # 2. If the worker wasn't running (e.g. it had already exited but
        #    the download wasn't marked finished yet), clean up via the
        #    worker's safe routines directly. But we need a reference to
        #    the worker object; if it's gone, fall back to a minimal,
        #    provably-safe check on the expected final path.
        if worker is None and expected_final_path and save_path:
            self._safe_delete_final_file(
                expected_final_path, save_path, download_started_at
            )

        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                del self.youtube_downloads[download_id]
            self.youtube_gids.discard(download_id)
            if download_id in self._size_workers:
                try:
                    size_worker = self._size_workers.pop(download_id, None)
                    if size_worker is not None and size_worker.isRunning():
                        size_worker.stop_for_removal()
                except Exception as e:
                    print(f"⚠️ [Worker] Could not stop size worker: {e}")

        print(
            f"🗑️ [Worker] YouTube download cancelled and its files deleted: "
            f"{download_id}"
        )

    def _safe_delete_final_file(
        self,
        file_path: str,
        save_path: str,
        download_started_at: Optional[float],
    ):
        """Delete a single final-output file, but only if it's safe.

        Safety rules (C29):
        - Must be a regular file directly inside save_path.
        - If we know when the download started, the file's mtime must not
        predate that by more than a small grace window (5s) — this
        prevents deleting a pre-existing file with the same name.
        """
        try:
            real_save = Path(save_path).resolve()
            real_file = Path(file_path).resolve()
        except (OSError, RuntimeError) as e:
            print(f"⚠️ [Worker] Cannot resolve paths for delete: {e}")
            return

        if real_file.parent != real_save:
            print(f"⚠️ [Worker] Refusing to delete outside save_path: {real_file}")
            return
        if not real_file.exists():
            return
        if real_file.is_dir():
            print(f"⚠️ [Worker] Refusing to rmtree directory: {real_file}")
            return

        if download_started_at is not None:
            try:
                mtime = real_file.stat().st_mtime
            except OSError:
                return
            # Grace window: yt-dlp may write the final file a few seconds
            # before we recorded 'created_at' (clock skew, save).
            if mtime < download_started_at - 5.0:
                print(
                    f"⚠️ [Worker] Refusing to delete older file "
                    f"(mtime={mtime:.0f} < start={download_started_at:.0f}): "
                    f"{real_file.name}"
                )
                return

        try:
            real_file.unlink()
            print(f"🗑️ [Worker] Deleted: {real_file.name}")
        except OSError as e:
            print(f"⚠️ [Worker] Could not delete {real_file}: {e}")

    def cancel_youtube_download_without_delete(self, download_id: str):
        print(f"🗑️ [Worker] Cancelling YouTube download without delete: {download_id}")
        worker = None
        with self.youtube_lock:
            if download_id in self.youtube_workers:
                worker = self.youtube_workers[download_id]
                del self.youtube_workers[download_id]

        if worker and worker.is_running():
            worker.cancel()
            worker.wait(1000)

        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                del self.youtube_downloads[download_id]
            self.youtube_gids.discard(download_id)
            if download_id in self._size_workers:
                try:
                    size_worker = self._size_workers.pop(download_id, None)
                    if size_worker is not None and size_worker.isRunning():
                        size_worker.stop_for_removal()
                except Exception as e:
                    print(f"⚠️ [Worker] Could not stop size worker: {e}")

        print(f"🗑️ [Worker] YouTube download cancelled (files kept): {download_id}")

    def _on_youtube_progress(self, download_id: str, progress: int):
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]["progress"] = progress
                self.store.update_youtube_progress(download_id, progress)
        self.youtube_progress.emit(download_id, progress)

    def _on_youtube_status(self, download_id: str, status: str):
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]["status_text"] = status
        self.youtube_status.emit(download_id, status)

    def _on_youtube_speed(self, download_id: str, speed: str, eta: str):
        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                self.youtube_downloads[download_id]["speed"] = speed
                self.youtube_downloads[download_id]["eta"] = eta
        self.youtube_speed.emit(download_id, speed, eta)

    def _on_youtube_finished(self, download_id: str, success: bool, message: str):
        print(
            f"🎬 [Worker] YouTube download finished: {download_id} - Success: {success} - Message: {message}"
        )
        if "cancelled" in message.lower() or "cancel" in message.lower():
            with self.youtube_lock:
                if download_id in self.youtube_downloads:
                    del self.youtube_downloads[download_id]
                if download_id in self.youtube_workers:
                    del self.youtube_workers[download_id]
                self.youtube_gids.discard(download_id)
            return

        with self.youtube_lock:
            if download_id in self.youtube_downloads:
                if success:
                    self.youtube_downloads[download_id]["status"] = "completed"
                    self.youtube_downloads[download_id]["progress"] = 100
                    self.store.update_youtube_status(download_id, "completed")
                else:
                    self.youtube_downloads[download_id]["status"] = "error"
                    self.youtube_downloads[download_id]["error_message"] = message
                    self.store.update_youtube_status(download_id, "error")
            if download_id in self.youtube_workers:
                del self.youtube_workers[download_id]
            self.youtube_gids.discard(download_id)

        self.youtube_finished.emit(download_id, success, message)

    def _stop_all_youtube_downloads(self):
        # Take a snapshot of the workers under the lock, then cancel them
        # OUTSIDE the lock. cancel() calls self.wait() internally, so
        # holding youtube_lock across it would block any other thread that
        # needs the lock (and, since this is called from the UI thread via
        # quit_app -> worker.stop(), it would freeze the whole UI).
        with self.youtube_lock:
            workers_snapshot = list(self.youtube_workers.items())
            self.youtube_workers.clear()

        for download_id, worker in workers_snapshot:
            try:
                if worker.is_running():
                    worker.cancel()
            except Exception as e:
                print(f"⚠️ Error cancelling YouTube worker {download_id[:8]}: {e}")
            with self.youtube_lock:
                if download_id in self.youtube_downloads:
                    self.youtube_downloads[download_id]["status"] = "paused"
                    self.store.update_youtube_status(download_id, "paused")

    def _stop_all_size_workers(self):
        for download_id, worker in list(self._size_workers.items()):
            try:
                if worker.isRunning():
                    worker.stop_for_removal()
            except Exception as e:
                print(f"⚠️ [Worker] Could not stop size worker {download_id[:8]}: {e}")
        self._size_workers.clear()
