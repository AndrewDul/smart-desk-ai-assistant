from __future__ import annotations

import threading
import time
from typing import Callable


class SessionTimer:
    def __init__(
        self,
        on_started: Callable[[str, float], None] | None = None,
        on_finished: Callable[[str], None] | None = None,
        on_stopped: Callable[[str], None] | None = None,
    ) -> None:
        self.on_started = on_started
        self.on_finished = on_finished
        self.on_stopped = on_stopped

        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._running = False
        self._mode: str | None = None
        self._remaining_seconds = 0

    def start(self, minutes: float, mode: str) -> tuple[bool, str]:
        if self._running:
            return False, "A timer is already running."

        if minutes <= 0:
            return False, "Timer duration must be greater than zero."

        self._running = True
        self._mode = mode
        self._remaining_seconds = int(minutes * 60)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

        if self.on_started:
            self.on_started(mode, minutes)

        self._thread.start()
        return True, f"{mode.capitalize()} timer started for {minutes:g} minute(s)."

    def _run(self) -> None:
        end_time = time.time() + self._remaining_seconds

        while self._stop_event and not self._stop_event.is_set():
            self._remaining_seconds = max(0, int(round(end_time - time.time())))
            if self._remaining_seconds <= 0:
                break
            time.sleep(0.5)

        if self._stop_event and self._stop_event.is_set():
            return

        finished_mode = self._mode
        self._running = False
        self._mode = None
        self._remaining_seconds = 0

        if finished_mode and self.on_finished:
            self.on_finished(finished_mode)

    def stop(self) -> tuple[bool, str]:
        if not self._running:
            return False, "No timer is currently running."

        stopped_mode = self._mode or "unknown"

        if self._stop_event:
            self._stop_event.set()

        self._running = False
        self._mode = None
        self._remaining_seconds = 0

        if self.on_stopped:
            self.on_stopped(stopped_mode)

        return True, f"{stopped_mode.capitalize()} timer stopped."

    def status(self) -> dict:
        return {
            "running": self._running,
            "mode": self._mode,
            "remaining_seconds": self._remaining_seconds,
        }
