# core/schedule_manager.py

from __future__ import annotations

import time
from datetime import datetime, time as dt_time
from typing import Dict, List, Set

from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QMutexLocker


class ScheduleConfig:

    def __init__(self, queue_name, start, end, days, enabled=True):
        self.queue_name = queue_name
        self.start = start
        self.end = end
        self.days = days
        self.enabled = enabled


class ScheduleManagerThread(QThread):

    start_queue = pyqtSignal(str)
    pause_queue = pyqtSignal(str)

    def __init__(self, check_interval=5.0, parent=None):
        super().__init__(parent)
        self._check_interval = check_interval
        self._mutex = QMutex()
        self._schedules: Dict[str, ScheduleConfig] = {}
        self._running_queues: Set[str] = set()
        self._stop_requested = False

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
        if not cfg.enabled:
            return False
        if now.weekday() not in cfg.days:
            return False

        current = now.time()
        start, end = cfg.start, cfg.end

        if start <= end:
            return start <= current < end
        else:
            return current >= start or current < end

    def run(self):

        while not self._stop_requested:
            now = datetime.now()

            with QMutexLocker(self._mutex):
                schedules = list(self._schedules.values())
                currently_should_run = set()

                for cfg in schedules:
                    if self._is_within_window(cfg, now):
                        currently_should_run.add(cfg.queue_name)

                to_start = currently_should_run - self._running_queues

                to_pause = self._running_queues - currently_should_run

                for queue_name in to_start:
                    self._running_queues.add(queue_name)
                    self.start_queue.emit(queue_name)

                for queue_name in to_pause:
                    self._running_queues.discard(queue_name)
                    self.pause_queue.emit(queue_name)

            slept = 0.0
            while slept < self._check_interval and not self._stop_requested:
                time.sleep(min(1.0, self._check_interval - slept))
                slept += 1.0
