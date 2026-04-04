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
        self._lock = threading.Lock()

        self._running = False
        self._mode: str | None = None
        self._remaining_seconds = 0
        self._started_at = 0.0
        self._ends_at = 0.0

    def start(self, minutes: float, mode: str) -> tuple[bool, str]:
        with self._lock:
            if self._running:
                return False, "A timer is already running."

            if minutes <= 0:
                return False, "Timer duration must be greater than zero."

            total_seconds = max(1, int(round(minutes * 60)))

            self._running = True
            self._mode = mode
            self._remaining_seconds = total_seconds
            self._started_at = time.time()
            self._ends_at = self._started_at + total_seconds
            self._stop_event = threading.Event()

            self._thread = threading.Thread(
                target=self._run,
                args=(mode, self._stop_event),
                daemon=True,
            )

        if self.on_started:
            self.on_started(mode, minutes)

        self._thread.start()
        return True, f"{mode.capitalize()} timer started for {minutes:g} minute(s)."

    def _run(self, mode: str, stop_event: threading.Event) -> None:
        while not stop_event.is_set():
            with self._lock:
                if not self._running or self._mode != mode:
                    return

                remaining = max(0, int(round(self._ends_at - time.time())))
                self._remaining_seconds = remaining

                if remaining <= 0:
                    self._running = False
                    self._mode = None
                    self._remaining_seconds = 0
                    self._started_at = 0.0
                    self._ends_at = 0.0
                    finished = True
                else:
                    finished = False

            if finished:
                if self.on_finished:
                    self.on_finished(mode)
                return

            time.sleep(0.2)

    def stop(self) -> tuple[bool, str]:
        with self._lock:
            if not self._running:
                return False, "No timer is currently running."

            stopped_mode = self._mode or "unknown"
            stop_event = self._stop_event

            self._running = False
            self._mode = None
            self._remaining_seconds = 0
            self._started_at = 0.0
            self._ends_at = 0.0

        if stop_event:
            stop_event.set()

        if self.on_stopped:
            self.on_stopped(stopped_mode)

        return True, f"{stopped_mode.capitalize()} timer stopped."

    def status(self) -> dict:
        with self._lock:
            running = self._running
            mode = self._mode
            remaining_seconds = self._remaining_seconds
            started_at = self._started_at
            ends_at = self._ends_at

        return {
            "running": running,
            "mode": mode,
            "remaining_seconds": remaining_seconds,
            "started_at": started_at,
            "ends_at": ends_at,
        }