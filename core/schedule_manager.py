# core/schedule_manager.py

from __future__ import annotations

import time
from datetime import datetime, time as dt_time
from typing import Dict, List, Set, Optional, Callable

from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker


class ScheduleConfig:
    def __init__(self, queue_name, start, end, days, enabled=True):
        self.queue_name = queue_name
        self.start = start
        self.end = end
        self.days = days
        self.enabled = enabled


def is_within_window(start, end, days, now, enabled=True) -> bool:
    """Canonical "is this schedule active right now?" test.

    Single source of truth shared by the scheduler thread and the queue
    model. They previously each had their own version that disagreed for
    windows crossing midnight, so the sidebar could claim a queue was
    "active" while the scheduler considered it inactive (or vice versa).

    `days` holds the weekday numbers the window *starts* on. For an
    overnight window (start > end) the tail that runs past midnight
    belongs to the previous day, e.g. a Sunday 22:00-06:00 window is still
    running at Monday 03:00.

    The interval is half-open: [start, end). A download scheduled to end
    at 06:00 is not active at exactly 06:00.
    """
    if not enabled:
        return False
    if start == end:
        return False

    weekday = now.weekday()
    t = now.time()

    try:
        days = set(days)
    except TypeError:
        return False
    if not days:
        return False

    if start < end:
        return weekday in days and start <= t < end

    # Window crosses midnight.
    if t >= start:
        # Before midnight: today must be a start day.
        return weekday in days
    if t < end:
        # After midnight: the window was started by the previous day.
        return ((weekday - 1) % 7) in days
    return False


class ScheduleManagerThread(QThread):
    """Background scheduler.

    IMPORTANT (Wayland / lock-screen fix):
    This thread does the actual queue start/pause work itself, using
    the store and aria2 references passed in at construction. It does
    NOT rely on signals crossing to the UI thread, because on Wayland
    the Qt main event loop is frozen while the screen is locked — so
    any queued signal would sit unprocessed until the user unlocks.

    The signals below are kept as a lightweight "please refresh the
    UI" notification. They are allowed to be delayed; the actual
    download state change already happened here in the worker thread.
    """

    # Lightweight UI notifications only. The real work is done here.
    start_queue = pyqtSignal(str)
    pause_queue = pyqtSignal(str)

    def __init__(
        self,
        store,
        aria2,
        check_interval=5.0,
        parent=None,
    ):
        super().__init__(parent)
        self._check_interval = check_interval
        self._mutex = QMutex()
        self._schedules: Dict[str, ScheduleConfig] = {}
        self._running_queues: Set[str] = set()
        self._stop_requested = False

        # References to shared state. Used directly from this thread.
        self._store = store
        self._aria2 = aria2

    def set_schedules(self, schedules: List[ScheduleConfig]):
        with QMutexLocker(self._mutex):
            new_schedules = {s.queue_name: s for s in schedules}

            # Preserve the "running" state for queues whose schedule
            # hasn't changed — otherwise a benign settings save would
            # reset _running_queues and fire start/pause signals again.
            if new_schedules.keys() == self._schedules.keys():
                for name in new_schedules:
                    old = self._schedules[name]
                    new = new_schedules[name]
                    if (
                        old.start == new.start
                        and old.end == new.end
                        and old.days == new.days
                        and old.enabled == new.enabled
                    ):
                        continue
                    # This queue's schedule changed — drop it from running
                    # so the next tick re-evaluates it cleanly.
                    self._running_queues.discard(name)

            self._schedules = new_schedules

    def stop(self):
        self._stop_requested = True
        self.wait(3000)

    def _is_within_window(self, cfg: ScheduleConfig, now: datetime) -> bool:
        # Delegates to the shared helper so the scheduler and the queue
        # model can never disagree about what "active now" means.
        return is_within_window(
            cfg.start, cfg.end, cfg.days, now, enabled=cfg.enabled
        )

    # ─────────────────────────────────────────────────────────────
    #  Direct queue control (runs in this worker thread)
    # ─────────────────────────────────────────────────────────────

    def _find_queue(self, queue_name: str):
        """Find a queue object by name. Reads from the shared store."""
        try:
            for q in self._store.queues:
                if q.name == queue_name:
                    return q
        except Exception as e:
            print(f"⚠️ [Scheduler] Could not read queues: {e}")
        return None

    def _start_queue_direct(self, queue_name: str) -> None:
        """Start a queue and all its downloads directly, without
        involving the UI thread.

        This is what makes the schedule work while the screen is
        locked on Wayland: we never emit a signal that the UI has to
        process — we change state and talk to aria2 ourselves.
        """
        q = self._find_queue(queue_name)
        if q is None:
            print(f"⚠️ [Scheduler] Queue '{queue_name}' not found")
            return

        if q.manually_paused:
            print(
                f"⏸️ [Scheduler] Queue '{queue_name}' is manually paused "
                f"— skipping auto-start"
            )
            return

        if not q.paused:
            return

        print(f"▶️ [Scheduler] Starting queue '{queue_name}' (direct)")

        q.paused = False
        q.manually_paused = False

        # Collect gids that need to be unpaused in aria2.
        gids_to_resume = []
        resumed_infos = []
        for gid in q.downloads:
            info = q.downloads_info.get(gid)
            if not info:
                continue

            dtype = info.get("download_type", "normal")
            if dtype == "youtube":
                # YouTube downloads are handled by the worker's
                # add_youtube_download path when the UI processes the
                # start signal. Skip them here — a locked screen can't
                # safely interact with the yt-dlp workers, and resuming
                # a paused yt-dlp mid-process is what the UI does.
                continue

            aria2_gid = info.get("aria2_gid")
            if not aria2_gid:
                continue

            # Only resume downloads that are paused/waiting/stopped.
            try:
                st = self._aria2.get_status(aria2_gid)
            except Exception:
                st = None
            if not st:
                continue
            real_status = st.get("status", "")
            # "stopped" (finished/errored/removed) cannot be unpaused in
            # aria2; the UI's start logic retries those. Only paused and
            # waiting downloads can be resumed here.
            if real_status in ("paused", "waiting"):
                gids_to_resume.append(aria2_gid)
                resumed_infos.append(info)

        if gids_to_resume:
            try:
                # Use the bulk API to keep it to one round trip.
                ok = self._aria2.resume_multi(gids_to_resume)
                if ok:
                    # Only now are they really running; the status used to
                    # be set to "active" before the call, even when it failed.
                    for info in resumed_infos:
                        info["status"] = "active"
                    print(
                        f"▶️ [Scheduler] Resumed {len(gids_to_resume)} "
                        f"download(s) in queue '{queue_name}'"
                    )
                else:
                    print(
                        f"⚠️ [Scheduler] resume_multi returned False for "
                        f"queue '{queue_name}'"
                    )
            except Exception as e:
                print(f"⚠️ [Scheduler] resume_multi failed: {e}")

        # Persist the new state so a restart preserves it.
        try:
            self._store.save()
        except Exception as e:
            print(f"⚠️ [Scheduler] Could not save store: {e}")

    def _pause_queue_direct(self, queue_name: str) -> None:
        """Pause a queue and all its downloads directly, without
        involving the UI thread.
        """
        q = self._find_queue(queue_name)
        if q is None:
            return

        if q.paused:
            return

        print(f"⏸️ [Scheduler] Pausing queue '{queue_name}' (direct)")

        q.paused = True
        q.manually_paused = False  # Schedule-driven pause, not user

        gids_to_pause = []
        for gid in q.downloads:
            info = q.downloads_info.get(gid)
            if not info:
                continue

            dtype = info.get("download_type", "normal")
            if dtype == "youtube":
                continue  # handled by UI when unlocked

            aria2_gid = info.get("aria2_gid")
            if not aria2_gid:
                continue

            try:
                st = self._aria2.get_status(aria2_gid)
            except Exception:
                st = None
            if not st:
                continue
            real_status = st.get("status", "")
            if real_status in ("active", "waiting"):
                gids_to_pause.append(aria2_gid)
                info["status"] = "paused"
                info["downloadSpeed"] = 0

        if gids_to_pause:
            try:
                ok = self._aria2.pause_multi(gids_to_pause)
                if ok:
                    print(
                        f"⏸️ [Scheduler] Paused {len(gids_to_pause)} "
                        f"download(s) in queue '{queue_name}'"
                    )
            except Exception as e:
                print(f"⚠️ [Scheduler] pause_multi failed: {e}")

        try:
            self._store.save()
        except Exception as e:
            print(f"⚠️ [Scheduler] Could not save store: {e}")

    # ─────────────────────────────────────────────────────────────
    #  Main loop
    # ─────────────────────────────────────────────────────────────

    def run(self):
        while not self._stop_requested:
            now = datetime.now()

            # Decide under the lock, but perform the work outside it.
            # _start_queue_direct/_pause_queue_direct do network RPC and
            # fsync a store save; holding the mutex across them blocked
            # set_schedules() (called from the UI thread) for the whole
            # duration, freezing the interface.
            with QMutexLocker(self._mutex):
                schedules = list(self._schedules.values())
                currently_should_run = set()

                for cfg in schedules:
                    if self._is_within_window(cfg, now):
                        currently_should_run.add(cfg.queue_name)

                to_start = sorted(currently_should_run - self._running_queues)
                to_pause = sorted(self._running_queues - currently_should_run)

                self._running_queues |= set(to_start)
                self._running_queues -= set(to_pause)

            for queue_name in to_start:
                # Do the real work here, in this thread.
                self._start_queue_direct(queue_name)
                # Then notify the UI (may be delayed on Wayland lock).
                self.start_queue.emit(queue_name)

            for queue_name in to_pause:
                self._pause_queue_direct(queue_name)
                self.pause_queue.emit(queue_name)

            slept = 0.0
            while slept < self._check_interval and not self._stop_requested:
                time.sleep(min(1.0, self._check_interval - slept))
                slept += 1.0