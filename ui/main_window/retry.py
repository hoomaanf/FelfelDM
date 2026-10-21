"""Automatic retry of failed downloads."""

import time

from PyQt6.QtCore import QTimer

from core.error_classifier import classify, make_entry


class RetryMixin:
    """Automatic retry of failed downloads."""

    def _is_retriable_error(self, error_msg: str, error_code=None) -> bool:
        return classify(error_msg or "", error_code).retriable

    def _on_download_error(self, download_id: str, error_msg: str) -> None:
        data = self._all_downloads.get(download_id)
        if not data:
            return

        if data.get("download_type") == "video":
            return

        if download_id in self._retrying_gids:
            return

        if download_id in self._retry_state:
            return

        if data.get("status") == "retrying":
            return

        print(
            f"🔴 [Error] _on_download_error for {download_id[:12]}, "
            f"msg={error_msg[:100]!r}"
        )

        if not error_msg or not error_msg.strip():
            print(
                f"⏭️ [Retry] Empty error for {download_id[:12]} — "
                f"letting aria2 retry"
            )
            return

            # ── Record this error in the history (bounded to 10) ──
        try:
            entry = make_entry(
                error_msg,
                error_code=data.get("errorCode"),
            )
            hist = data.setdefault("error_history", [])
            hist.append(entry)
            if len(hist) > 10:
                del hist[:-10]
            # Mirror into the persistent store so it survives restarts.
            # We save explicitly here (not via mark_dirty) because errors
            # are rare, and we want the history on disk immediately.
            for _q in self.store.queues:
                if download_id in _q.downloads_info:
                    _q.downloads_info[download_id]["error_history"] = list(hist)
                    break
            self.store.save()
        except Exception as e:
            print(f"⚠️ [Error] Could not record error history: {e}")

        ce = classify(error_msg, data.get("errorCode"))

        # ── Permanent error path ──
        if not ce.retriable:
            print(
                f"🔴 [Retry] Permanent error for {download_id[:12]} "
                f"({ce.category.value}): {error_msg[:60]}"
            )
            self._retrying_gids.add(download_id)
            if error_msg:
                data["errorMessage"] = error_msg
            error_count = self._to_int(data.get("error_count", 0))
            self._schedule_retry(download_id, error_count)
            return

        # ── Transient error path ──
        print(
            f"⏭️ [Retry] Transient error for {download_id[:12]} "
            f"({ce.category.value}) — will retry: {error_msg[:60]}"
        )

        aria2_gid = data.get("aria2_gid")

        if not aria2_gid or not self.aria2:
            print(
                f"⚠️ [Retry] No aria2_gid for {download_id[:12]} — " f"scheduling retry"
            )
            self._retrying_gids.add(download_id)
            if error_msg:
                data["errorMessage"] = error_msg
            error_count = self._to_int(data.get("error_count", 0))
            self._schedule_retry(download_id, error_count)
            return

        status_data = None
        try:
            status_data = self.aria2.get_status(aria2_gid)
        except Exception as e:
            print(f"⚠️ [Retry] Could not check status for {aria2_gid[:12]}: {e}")

        if not status_data:
            print(
                f"⚠️ [Retry] aria2 status unavailable for "
                f"{aria2_gid[:12]} — scheduling retry"
            )
            self._retrying_gids.add(download_id)
            if error_msg:
                data["errorMessage"] = error_msg
            error_count = self._to_int(data.get("error_count", 0))
            self._schedule_retry(download_id, error_count)
            return

        real_status = status_data.get("status", "")
        print(f"🔍 [Retry] aria2 status for {aria2_gid[:12]}: {real_status}")

        if real_status == "error":
            print(
                f"🔄 [Retry] aria2 gave up — scheduling re-add for "
                f"{download_id[:12]}"
            )
            self._retrying_gids.add(download_id)
            error_count = self._to_int(data.get("error_count", 0))
            self._schedule_retry(download_id, error_count)
            return

        if real_status in ("paused", "stopped", "waiting"):
            try:
                self.aria2.resume(aria2_gid)
                print(f"▶️ [Retry] Unpaused {aria2_gid[:12]}")
            except Exception as e:
                print(f"⚠️ [Retry] Resume failed for {aria2_gid[:12]}: {e}")
                # Resume failed: schedule a retry.
                self._retrying_gids.add(download_id)
                if error_msg:
                    data["errorMessage"] = error_msg
                error_count = self._to_int(data.get("error_count", 0))
                self._schedule_retry(download_id, error_count)
            return

        if real_status == "active":
            print(f"⏳ [Retry] aria2 is still active for {aria2_gid[:12]}")
            return

        # Unknown status: schedule a retry.
        print(
            f"⚠️ [Retry] Unknown aria2 status '{real_status}' for "
            f"{aria2_gid[:12]} — scheduling retry"
        )
        self._retrying_gids.add(download_id)
        if error_msg:
            data["errorMessage"] = error_msg
        error_count = self._to_int(data.get("error_count", 0))
        self._schedule_retry(download_id, error_count)

    def _schedule_retry(self, download_id: str, attempt: int) -> None:
        data = self._all_downloads.get(download_id)
        if not data:
            return

        error_msg = data.get("errorMessage", "")

        if not self._is_retriable_error(error_msg, data.get("errorCode")):
            print(
                f"⛔ [Retry] Permanent error for {download_id[:12]}: {error_msg[:60]}"
            )
            data["status"] = "error"
            self._retrying_gids.discard(download_id)
            return

        max_tries = self.store.settings.get("max_retry_attempts", 5)
        next_attempt = attempt + 1

        if next_attempt > max_tries:
            print(f"⛔ [Retry] Max tries reached for {download_id[:12]}")
            data["status"] = "error"
            self._retrying_gids.discard(download_id)
            return

        retry_delay = max(1, int(self.store.settings.get("retry_delay", 5)))

        old_timer = self._retry_timers.pop(download_id, None)
        if old_timer:
            old_timer.stop()

        self._retry_state[download_id] = {
            "deadline": time.time() + retry_delay,
            "attempt": next_attempt,
            "max_tries": max_tries,
        }

        data["status"] = "retrying"
        data["downloadSpeed"] = 0
        data["status_detail"] = (
            f"🔄 Retrying in {retry_delay}s... ({next_attempt}/{max_tries})"
        )

        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda d=download_id: self._do_delayed_retry(d))
        timer.start(retry_delay * 1000)
        self._retry_timers[download_id] = timer

        if self._countdown_timer and not self._countdown_timer.isActive():
            self._countdown_timer.start()

        self._refresh_table()
        print(
            f"⏱️ [Retry] Scheduled {download_id[:12]} in {retry_delay}s "
            f"(attempt {next_attempt}/{max_tries})"
        )

    def _do_delayed_retry(self, download_id: str) -> None:
        timer = self._retry_timers.pop(download_id, None)
        if timer:
            timer.stop()

        self._retry_state.pop(download_id, None)

        self._retrying_gids.discard(download_id)

        if download_id not in self._all_downloads:
            return

        self._all_downloads[download_id].pop("status_detail", None)

        print(f"🔄 [Retry] Executing delayed retry for {download_id[:12]}")
        self._retry_single_download(download_id)

    def _maybe_reset_error_counts(self) -> None:
        """Reset a download's failed-attempt counter once it has been
        downloading healthily for `retry_reset_after` seconds.

        "Healthy" means: status is active, no retry is pending, and
        completedLength actually advanced during the window (so a stalled
        or still-connecting download never earns a reset).
        """
        reset_after = self._to_int(self.store.settings.get("retry_reset_after", 60))
        if reset_after <= 0:
            self._healthy_since.clear()
            return

        now = time.time()

        for download_id in list(self._healthy_since):
            if download_id not in self._all_downloads:
                self._healthy_since.pop(download_id, None)

        for download_id, data in self._all_downloads.items():
            if data.get("download_type") == "video":
                continue

            if self._to_int(data.get("error_count", 0)) <= 0:
                self._healthy_since.pop(download_id, None)
                continue

            healthy = (
                data.get("status") in ("active", "downloading")
                and download_id not in self._retry_state
                and download_id not in self._retrying_gids
            )
            if not healthy:
                self._healthy_since.pop(download_id, None)
                continue

            completed = self._to_int(data.get("completedLength", 0))
            entry = self._healthy_since.get(download_id)

            if entry is None or completed < entry[1]:
                self._healthy_since[download_id] = (now, completed)
                continue

            since, base_completed = entry
            if now - since < reset_after:
                continue

            if completed > base_completed:
                old_count = self._to_int(data.get("error_count", 0))
                data["error_count"] = 0
                for q in self.store.queues:
                    if download_id in q.downloads_info:
                        q.downloads_info[download_id]["error_count"] = 0
                        break
                self._healthy_since.pop(download_id, None)
                self.store.mark_dirty()
                print(
                    f"[Retry] {download_id[:12]} healthy for {reset_after}s — "
                    f"error_count reset {old_count} -> 0"
                )
            else:
                # Active but no data moved during the whole window: not healthy.
                self._healthy_since[download_id] = (now, completed)

    def _tick_retry_countdown(self) -> None:
        if not self._retry_state:
            if self._countdown_timer:
                self._countdown_timer.stop()
            return

        now = time.time()
        finished = []
        any_change = False

        for download_id, info in list(self._retry_state.items()):
            remaining = int(info["deadline"] - now)
            if remaining <= 0:
                finished.append(download_id)
                continue

            data = self._all_downloads.get(download_id)
            if data:
                new_detail = (
                    f"🔄 Retrying in {remaining}s... "
                    f"({info['attempt']}/{info['max_tries']})"
                )
                if data.get("status_detail") != new_detail:
                    data["status_detail"] = new_detail
                    data["status"] = "retrying"
                    any_change = True

        for download_id in finished:
            self._retry_state.pop(download_id, None)

        if any_change:
            self._refresh_table()
