"""Turning aria2's poll results into UI state."""

import os
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QMetaObject, Qt
from PyQt6.QtWidgets import QSystemTrayIcon


class StatsSyncMixin:
    """Turning aria2's poll results into UI state."""

    def _on_stats_received(self, result: Dict[str, Any]) -> None:
        if not isinstance(result, dict):
            return

        if not result.get("connected"):
            self.status_lbl.setText("● Disconnected")
            self.status_lbl.setStyleSheet("color: #e74c3c; font-weight: bold;")
            if hasattr(self, "speed_status_label"):
                self.speed_status_label.setText("0 B/s")
            if hasattr(self, "tray") and hasattr(self, "tray_icon_normal"):
                self.tray.setIcon(self.tray_icon_normal)
            return

        self.status_lbl.setText("● Connected")
        self.status_lbl.setStyleSheet("color: #27ae60; font-weight: bold;")

        downloads_list = result.get("downloads", [])

        new_errors = []
        for dl in downloads_list:
            if not isinstance(dl, dict):
                continue
            gid = dl.get("gid")
            if not gid:
                continue
            new_status = dl.get("status", "")

            if new_status == "error":
                download_id = None
                for did, ddata in self._all_downloads.items():
                    if ddata.get("aria2_gid") == gid:
                        download_id = did
                        break
                if download_id:
                    # Skip if this download is already being retried.
                    # Otherwise every poll tick re-detects the same error
                    # and calls _on_download_error again in a loop.
                    if (
                        download_id in self._retry_state
                        or download_id in self._retrying_gids
                    ):
                        continue
                    if self._all_downloads[download_id].get("status") == "retrying":
                        continue

                    old_status = self._all_downloads[download_id].get("status", "")

                    if old_status not in ("error", "stopped", "paused"):
                        new_errors.append((download_id, dl.get("errorMessage", "")))

        self._update_downloads_from_stats(downloads_list)

        for download_id, error_msg in new_errors:
            self._on_download_error(download_id, error_msg)

        youtube_downloads = result.get("youtube_downloads", [])
        self._update_youtube_dialogs(youtube_downloads)

        self._refresh_table()
        self._update_queue_status()

        if self._queue_list_dirty:
            self._refresh_queue_list()

        self._update_queue_buttons()
        self._update_shutdown_button_state()
        self._update_toggle_button()
        self._update_progress_bar()
        q = self._current_queue()
        if q and q.speed_limit > 0 and not q.paused:
            active_count = sum(
                1
                for did in q.downloads
                if self._all_downloads.get(did, {}).get("status", "")
                in ("active", "downloading")
            )
            last = getattr(self, "_last_speed_limit_active_count", None)
            if active_count != last:
                self._last_speed_limit_active_count = active_count
                self._apply_queue_speed_limit(q)

        if (
            self._details_visible
            and hasattr(self, "details_panel")
            and self.details_panel is not None
        ):
            self._update_details_panel()

        for gid, dialog in list(self._progress_dialogs.items()):
            try:
                if dialog.isVisible() and gid in self._all_downloads:
                    dialog.update_data(self._all_downloads[gid])
            except (RuntimeError, AttributeError):
                self._progress_dialogs.pop(gid, None)

        if self.shutdown_cb.isChecked():
            self._check_already_complete()

    def _update_downloads_from_stats(self, downloads_list: List[Dict]) -> None:

        gid_to_download_id: Dict[str, str] = {}
        for download_id, data in self._all_downloads.items():
            aria2_gid = data.get("aria2_gid")
            if aria2_gid:
                gid_to_download_id[aria2_gid] = download_id
        saved_data = {}
        for download_id, data in self._all_downloads.items():
            try:
                total = (
                    int(data.get("totalLength", 0)) if data.get("totalLength", 0) else 0
                )
                completed = (
                    int(data.get("completedLength", 0))
                    if data.get("completedLength", 0)
                    else 0
                )
            except (ValueError, TypeError):
                total = 0
                completed = 0
            if total > 0 or completed > 0:
                saved_data[download_id] = {
                    "totalLength": total,
                    "completedLength": completed,
                }

        newly_completed = []

        for dl in downloads_list:
            if not isinstance(dl, dict):
                continue
            gid = dl.get("gid")
            if not gid:
                continue

            download_id = gid_to_download_id.get(gid)

            if download_id and download_id in self._all_downloads:
                pass
            elif gid in self._all_downloads:

                download_id = gid
            else:

                continue

            if download_id in self._all_downloads:
                new_total = 0
                try:
                    new_total = (
                        int(dl.get("totalLength", 0)) if dl.get("totalLength", 0) else 0
                    )
                except (ValueError, TypeError):
                    new_total = 0

                if (
                    new_total == 0
                    and download_id in saved_data
                    and saved_data[download_id]["totalLength"] > 0
                ):

                    # aria2 reported no size this tick: keep the sizes we
                    # have, but status and speed are still aria2's, as-is.
                    if (
                        download_id not in self._retry_state
                        and download_id not in self._retrying_gids
                    ):
                        for key in ["status", "downloadSpeed"]:
                            if key in dl:
                                self._all_downloads[download_id][key] = dl[key]
                    if "files" in dl:
                        self._all_downloads[download_id]["files"] = dl["files"]

                    self._all_downloads[download_id]["totalLength"] = saved_data[
                        download_id
                    ]["totalLength"]
                    self._all_downloads[download_id]["completedLength"] = saved_data[
                        download_id
                    ]["completedLength"]
                    continue

                old_status = self._all_downloads[download_id].get("status", "")
                new_status = dl.get("status", "")

                # aria2 is the single source of truth for a download's status
                # and speed: they are copied from its report unchanged. The one
                # exception is the app's own retry countdown ("retrying"),
                # which shows until the retry finishes.
                if download_id in self._retry_state:
                    dl = dict(dl)
                    dl.pop("status", None)
                    dl.pop("downloadSpeed", None)
                    new_status = old_status

                if new_status in ["complete", "completed"] and old_status not in [
                    "complete",
                    "completed",
                ]:
                    if download_id not in self._completed_gids:
                        self._completed_gids.add(download_id)
                        newly_completed.append(download_id)

                self._all_downloads[download_id].update(dl)
            else:
                self._all_downloads[download_id] = dl

        for download_id in newly_completed:
            self._play_completion_sound()

        current_gids = {dl.get("gid") for dl in downloads_list if dl.get("gid")}
        for download_id in list(self._all_downloads.keys()):
            if self._all_downloads[download_id].get("download_type") == "youtube":
                continue
            in_queue = any(download_id in q.downloads for q in self.store.queues)
            aria2_gid = self._all_downloads[download_id].get("aria2_gid")
            if not in_queue and aria2_gid not in current_gids:
                del self._all_downloads[download_id]

        self._maybe_reset_error_counts()

        for q in self.store.queues:
            for download_id in q.downloads:
                if download_id in self._all_downloads:
                    dl = self._all_downloads[download_id]
                    if download_id not in q.downloads_info:
                        q.downloads_info[download_id] = {}

                    q.downloads_info[download_id].update(
                        {
                            "id": download_id,
                            "aria2_gid": dl.get("aria2_gid"),
                            "totalLength": self._to_int(dl.get("totalLength", 0)),
                            "completedLength": self._to_int(
                                dl.get("completedLength", 0)
                            ),
                            "status": dl.get("status", "unknown"),
                            "name": dl.get("name", "Unknown"),
                            "files": dl.get("files", []),
                            "category": dl.get("category", "📁 Other"),
                            "error_count": self._to_int(dl.get("error_count", 0)),
                            "errorMessage": dl.get("errorMessage", ""),
                            "connections": self._to_int(dl.get("connections", 0)),
                        }
                    )

        self.store.mark_dirty()

    def _on_aria2_error(self, message: str) -> None:
        if any(
            x in message
            for x in [
                "disconnected",
                "cannot be paused now",
                "cannot be unpaused now",
                "is not found",
                "HTTP Error 400",
                "Bad Request",
                "Connection error",
                "Connection reset by peer",
            ]
        ):
            return
        self.tray.showMessage(
            "FelfelDM", message, QSystemTrayIcon.MessageIcon.Warning, 3000
        )
        self.status_label.setText(f"⚠ {message}")

    def _on_size_fetched(self, gid: str, size: int, category: str = "📁 Other") -> None:

        if size < 0:
            size = size & 0xFFFFFFFF

        if size <= 0:
            return

        download_id = None
        if gid in self._all_downloads:
            download_id = gid
        else:
            for did, ddata in self._all_downloads.items():
                if ddata.get("aria2_gid") == gid:
                    download_id = did
                    break

        if not download_id:

            print(f"⚠️ [MainWindow] GID {gid[:12]} not found in _all_downloads")
            return

        try:
            current_size = int(self._all_downloads[download_id].get("totalLength", 0))
        except (ValueError, TypeError):
            current_size = 0

        if current_size > 0 and current_size == size:
            return

        self._size_unknown.discard(download_id)
        self._all_downloads[download_id]["totalLength"] = size
        self._all_downloads[download_id]["category"] = category

        for q in self.store.queues:
            if download_id in q.downloads_info:
                q.downloads_info[download_id]["totalLength"] = size
                q.downloads_info[download_id]["category"] = category
                break

        self.store.save()
        self._refresh_table()
        self._update_progress_bar()

    def _on_size_failed(self, gid: str) -> None:
        """A size fetch ended without a size: show "Unknown", stop waiting."""
        download_id = None
        if gid in self._all_downloads:
            download_id = gid
        else:
            for did, ddata in self._all_downloads.items():
                if ddata.get("aria2_gid") == gid:
                    download_id = did
                    break
        if not download_id:
            return
        if self._to_int(self._all_downloads[download_id].get("totalLength", 0)) > 0:
            return
        self._size_unknown.add(download_id)
        self._refresh_table()

    def _on_download_status_changed(self, gid: str, status: str) -> None:
        # Only YouTube downloads (managed by yt-dlp workers, not aria2)
        # announce their status. For everything else aria2 is the single
        # source of truth and the stats poll sets the status.
        data = self._all_downloads.get(gid)
        if data is not None and data.get("download_type") == "youtube":
            data["status"] = status
            if status == "paused":
                data["downloadSpeed"] = 0

            for q in self.store.queues:
                if gid in q.downloads_info:
                    q.downloads_info[gid]["status"] = status
                    break

        QMetaObject.invokeMethod(
            self, "_delayed_ui_update", Qt.ConnectionType.QueuedConnection
        )

    def _get_aria2_status(self, gid: str) -> Optional[Dict]:
        try:
            if hasattr(self, "aria2") and self.aria2:
                return self.aria2.tell_status(gid)
        except Exception as e:
            print(f"⚠️ Could not get aria2 status for {gid}: {e}")
        return None

    def _to_int(self, value: Any) -> int:
        try:
            if value is None:
                return 0
            if isinstance(value, str):
                return int(value) if value.strip() else 0
            return int(value) if value else 0
        except (ValueError, TypeError):
            return 0

    def _play_completion_sound(self) -> None:
        """Play sound when download completes"""
        if not self.store.settings.get("sound_enabled", True):
            return

        sound_path = self.store.settings.get("sound_path", "")

        if not sound_path or not os.path.exists(sound_path):

            default_sounds = [
                "/usr/share/sounds/freedesktop/stereo/complete.oga",
                "/usr/share/sounds/freedesktop/stereo/complete.wav",
                "/usr/share/sounds/alsa/Noise.wav",
                "/usr/share/sounds/gnome/default/alerts/glass.ogg",
            ]
            for s in default_sounds:
                if os.path.exists(s):
                    sound_path = s
                    break
            else:
                return

        try:
            from PyQt6.QtMultimedia import QSound

            QSound.play(sound_path)
            print(f"🔊 Playing sound: {sound_path}")
            return
        except ImportError:
            pass

        try:
            import subprocess

            players = [
                ["paplay", sound_path],
                ["aplay", sound_path],
                ["ffplay", "-nodisp", "-autoexit", sound_path],
                ["mpv", "--no-video", sound_path],
            ]
            for player in players:
                try:
                    subprocess.Popen(
                        player, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    print(f"🔊 Playing via {' '.join(player)}")
                    return
                except FileNotFoundError:
                    continue
        except:
            pass

        print(f"⚠️ Could not play sound: {sound_path}")
