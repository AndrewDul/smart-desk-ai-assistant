from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(slots=True)
class TimerSnapshot:
    running: bool
    mode: str | None
    remaining_seconds: int
    started_at: float
    ends_at: float

    @property
    def remaining_minutes(self) -> float:
        return self.remaining_seconds / 60.0 if self.remaining_seconds > 0 else 0.0


class TimerService:
    """
    Lightweight session timer for NeXa.

    Supported modes:
    - timer
    - focus
    - break

    Public API:
    - start(minutes, mode)
    - stop()
    - status()
    """

    def __init__(
        self,
        on_started: Callable[..., None] | None = None,
        on_finished: Callable[..., None] | None = None,
        on_stopped: Callable[..., None] | None = None,
    ) -> None:
        self.on_started = on_started
        self.on_finished = on_finished
        self.on_stopped = on_stopped

        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None

        self._running = False
        self._mode: str | None = None
        self._remaining_seconds = 0
        self._started_at = 0.0
        self._ends_at = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, minutes: float, mode: str) -> tuple[bool, str]:
        safe_mode = self._normalize_mode(mode)

        try:
            requested_minutes = float(minutes)
        except (TypeError, ValueError):
            return False, "Timer duration must be a number."

        if requested_minutes <= 0:
            return False, "Timer duration must be greater than zero."

        with self._lock:
            if self._running:
                return False, "A timer is already running."

            total_seconds = max(1, int(round(requested_minutes * 60)))

            self._running = True
            self._mode = safe_mode
            self._remaining_seconds = total_seconds
            self._started_at = time.time()
            self._ends_at = self._started_at + total_seconds
            self._stop_event = threading.Event()

            stop_event = self._stop_event
            self._thread = threading.Thread(
                target=self._run,
                args=(safe_mode, requested_minutes, stop_event),
                daemon=True,
                name=f"nexa-timer-{safe_mode}",
            )

        self._emit_started(mode=safe_mode, minutes=requested_minutes)
        self._thread.start()

        return True, f"{safe_mode.capitalize()} timer started for {requested_minutes:g} minute(s)."

    def stop(self) -> tuple[bool, str]:
        with self._lock:
            if not self._running:
                return False, "No timer is currently running."

            stopped_mode = self._mode or "timer"
            stop_event = self._stop_event

            self._running = False
            self._mode = None
            self._remaining_seconds = 0
            self._started_at = 0.0
            self._ends_at = 0.0
            self._stop_event = None

        if stop_event is not None:
            stop_event.set()

        self._emit_stopped(mode=stopped_mode)

        return True, f"{stopped_mode.capitalize()} timer stopped."

    def status(self) -> dict[str, Any]:
        snapshot = self.snapshot()
        return {
            "running": snapshot.running,
            "mode": snapshot.mode,
            "remaining_seconds": snapshot.remaining_seconds,
            "started_at": snapshot.started_at,
            "ends_at": snapshot.ends_at,
        }

    def snapshot(self) -> TimerSnapshot:
        with self._lock:
            return TimerSnapshot(
                running=self._running,
                mode=self._mode,
                remaining_seconds=self._remaining_seconds,
                started_at=self._started_at,
                ends_at=self._ends_at,
            )

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _run(
        self,
        mode: str,
        minutes: float,
        stop_event: threading.Event,
    ) -> None:
        del minutes

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
                    self._stop_event = None
                    finished = True
                else:
                    finished = False

            if finished:
                self._emit_finished(mode=mode)
                return

            time.sleep(0.2)

    # ------------------------------------------------------------------
    # Callback emission
    # ------------------------------------------------------------------

    def _emit_started(self, *, mode: str, minutes: float) -> None:
        if not callable(self.on_started):
            return

        payload = {
            "timer_type": mode,
            "mode": mode,
            "minutes": minutes,
        }

        try:
            self.on_started(**payload)
            return
        except TypeError:
            pass

        try:
            self.on_started(mode, minutes)
            return
        except TypeError:
            pass

        try:
            self.on_started(mode=mode, minutes=minutes)
        except TypeError:
            self.on_started()

    def _emit_finished(self, *, mode: str) -> None:
        if not callable(self.on_finished):
            return

        payload = {
            "timer_type": mode,
            "mode": mode,
        }

        try:
            self.on_finished(**payload)
            return
        except TypeError:
            pass

        try:
            self.on_finished(mode)
            return
        except TypeError:
            pass

        try:
            self.on_finished(mode=mode)
        except TypeError:
            self.on_finished()

    def _emit_stopped(self, *, mode: str) -> None:
        if not callable(self.on_stopped):
            return

        payload = {
            "timer_type": mode,
            "mode": mode,
        }

        try:
            self.on_stopped(**payload)
            return
        except TypeError:
            pass

        try:
            self.on_stopped(mode)
            return
        except TypeError:
            pass

        try:
            self.on_stopped(mode=mode)
        except TypeError:
            self.on_stopped()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_mode(mode: str | None) -> str:
        normalized = str(mode or "timer").strip().lower()
        if normalized in {"focus", "break", "timer"}:
            return normalized
        return "timer"


__all__ = [
    "TimerService",
    "TimerSnapshot",
]