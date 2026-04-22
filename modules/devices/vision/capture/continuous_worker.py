# modules/devices/vision/capture/continuous_worker.py
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from modules.shared.logging.logger import get_logger

from .frame_packet import FramePacket
from .reader import VisionCaptureReader

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class CaptureWorkerStats:
    frames_captured: int = 0
    frames_dropped: int = 0
    consecutive_errors: int = 0
    last_capture_at: float | None = None
    last_error: str | None = None
    last_error_at: float | None = None


class ContinuousCaptureWorker:
    """
    Background thread that continuously reads frames from a VisionCaptureReader
    and maintains the latest FramePacket in a thread-safe slot.

    Design rules:
    - One thread, one frame slot — no queue, no backpressure.
    - Consumers always get the freshest available frame without blocking.
    - On repeated read errors the worker backs off and logs, never crashes.
    - Caller must call start() and stop() explicitly.
    """

    _MAX_CONSECUTIVE_ERRORS = 10
    _ERROR_BACKOFF_SECONDS = 0.5
    _IDLE_SLEEP_SECONDS = 0.001

    def __init__(
        self,
        reader: VisionCaptureReader,
        *,
        target_fps: float = 10.0,
        error_backoff_seconds: float = _ERROR_BACKOFF_SECONDS,
    ) -> None:
        self._reader = reader
        self._target_fps = max(1.0, float(target_fps))
        self._error_backoff_seconds = max(0.1, float(error_backoff_seconds))

        self._lock = threading.Lock()
        self._latest_frame: FramePacket | None = None
        self._stats = CaptureWorkerStats()

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._started = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background capture thread. Safe to call only once."""
        if self._started:
            LOGGER.warning("ContinuousCaptureWorker.start() called more than once — ignored.")
            return

        self._started = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="nexa-vision-capture",
            daemon=True,
        )
        self._thread.start()
        LOGGER.info(
            "ContinuousCaptureWorker started. target_fps=%.1f",
            self._target_fps,
        )

    def stop(self, *, timeout_seconds: float = 2.0) -> None:
        """Signal the background thread to stop and wait for it to exit."""
        if not self._started:
            return

        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=timeout_seconds)
            if self._thread.is_alive():
                LOGGER.warning(
                    "ContinuousCaptureWorker thread did not stop within %.1fs.",
                    timeout_seconds,
                )
            self._thread = None

        self._started = False
        LOGGER.info("ContinuousCaptureWorker stopped.")

    def latest_frame(self) -> FramePacket | None:
        """
        Return the most recently captured frame, or None if no frame is
        available yet. Never blocks — safe to call from any thread.
        """
        with self._lock:
            return self._latest_frame

    def stats(self) -> dict[str, Any]:
        """Return a snapshot of capture statistics for diagnostics."""
        with self._lock:
            s = self._stats
            return {
                "frames_captured": s.frames_captured,
                "frames_dropped": s.frames_dropped,
                "consecutive_errors": s.consecutive_errors,
                "last_capture_at": s.last_capture_at,
                "last_error": s.last_error,
                "last_error_at": s.last_error_at,
                "target_fps": self._target_fps,
                "running": self._started and not self._stop_event.is_set(),
            }

    @property
    def is_running(self) -> bool:
        return self._started and not self._stop_event.is_set()

    # ------------------------------------------------------------------
    # Internal capture loop
    # ------------------------------------------------------------------

    def _capture_loop(self) -> None:
        frame_interval = 1.0 / self._target_fps
        LOGGER.debug("ContinuousCaptureWorker capture loop starting.")

        while not self._stop_event.is_set():
            loop_start = time.monotonic()

            try:
                frame = self._reader.read_frame()
                self._store_frame(frame)
            except Exception as error:
                self._record_error(error)
                if self._stats.consecutive_errors >= self._MAX_CONSECUTIVE_ERRORS:
                    LOGGER.error(
                        "ContinuousCaptureWorker: %d consecutive errors, backing off %.2fs. Last: %s",
                        self._stats.consecutive_errors,
                        self._error_backoff_seconds,
                        error,
                    )
                    time.sleep(self._error_backoff_seconds)
                continue

            elapsed = time.monotonic() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > self._IDLE_SLEEP_SECONDS:
                time.sleep(sleep_time)

        LOGGER.debug("ContinuousCaptureWorker capture loop exited.")

    def _store_frame(self, frame: FramePacket) -> None:
        with self._lock:
            if self._latest_frame is not None:
                self._stats.frames_dropped += 1
            self._latest_frame = frame
            self._stats.frames_captured += 1
            self._stats.consecutive_errors = 0
            self._stats.last_capture_at = frame.captured_at
            self._stats.last_error = None

    def _record_error(self, error: Exception) -> None:
        with self._lock:
            self._stats.consecutive_errors += 1
            self._stats.last_error = f"{error.__class__.__name__}: {error}"
            self._stats.last_error_at = time.monotonic()