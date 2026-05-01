"""Feedback vision streamer — pipes camera frames to the Visual Shell dashboard.

Background daemon thread that pulls the latest frame from the existing
``ContinuousCaptureWorker`` (no extra capture pressure), encodes it as JPEG,
base64-encodes the bytes, and sends ``FEEDBACK_VISION_FRAME`` over the same
TCP transport the rest of the Visual Shell uses.

Designed to be cheap on a Pi:
  - downscale to ~480 px on the long edge before encoding
  - JPEG quality 60
  - default 5 fps (configurable)
  - if the camera worker isn't ready we skip and try again next tick

The streamer is started by the feedback lane when feedback mode turns on
and stopped when it turns off.
"""
from __future__ import annotations

import base64
import io
import threading
import time
from typing import Any

from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


class FeedbackVisionStreamer:
    """Background thread that streams camera frames to the dashboard."""

    def __init__(
        self,
        controller: Any,
        camera_service: Any,
        *,
        target_fps: float = 5.0,
        long_edge_px: int = 480,
        jpeg_quality: int = 60,
    ) -> None:
        self._controller = controller
        self._camera_service = camera_service
        self._target_fps = max(0.5, float(target_fps))
        self._long_edge_px = max(160, int(long_edge_px))
        self._jpeg_quality = int(max(20, min(95, jpeg_quality)))
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="nexa-feedback-vision-streamer",
                daemon=True,
            )
            self._thread.start()
        LOGGER.info("Feedback vision streamer started: fps=%s long_edge=%s",
                    self._target_fps, self._long_edge_px)
        return True

    def stop(self, *, timeout: float = 1.5) -> bool:
        with self._lock:
            thread = self._thread
            if thread is None:
                return False
            self._stop_event.set()
        thread.join(timeout=timeout)
        with self._lock:
            self._thread = None
        LOGGER.info("Feedback vision streamer stopped")
        return True

    def is_running(self) -> bool:
        with self._lock:
            t = self._thread
            return t is not None and t.is_alive()

    # ------------------------------------------------------------------

    def _run(self) -> None:
        period = 1.0 / self._target_fps
        next_tick = time.monotonic()
        consecutive_failures = 0

        while not self._stop_event.is_set():
            tick_start = time.monotonic()
            try:
                sent = self._tick_once()
                if sent:
                    consecutive_failures = 0
                else:
                    consecutive_failures = min(consecutive_failures + 1, 12)
            except Exception as error:  # pragma: no cover — defensive
                consecutive_failures = min(consecutive_failures + 1, 12)
                LOGGER.debug("Feedback vision tick failed safely: %s", error)

            # Back off slightly when failing repeatedly so we don't hammer
            # a missing camera.
            extra_backoff = 0.0
            if consecutive_failures >= 3:
                extra_backoff = min(consecutive_failures * 0.25, 2.0)

            next_tick += period
            sleep_for = max(0.0, next_tick - time.monotonic()) + extra_backoff
            if sleep_for > 0.0:
                if self._stop_event.wait(timeout=sleep_for):
                    break

            # If we fell badly behind (e.g. encoder slow), reset the schedule.
            if time.monotonic() - tick_start > period * 4.0:
                next_tick = time.monotonic()

    def _tick_once(self) -> bool:
        packet = self._latest_packet()
        if packet is None:
            return False

        jpeg_b64, w, h = self._encode_packet(packet)
        if jpeg_b64 == "" or w <= 0 or h <= 0:
            return False

        return bool(
            self._controller.feedback_vision_frame(
                jpeg_b64=jpeg_b64,
                width=w,
                height=h,
                source="nexa-feedback-vision",
            )
        )

    def _latest_packet(self):
        # Prefer the continuous worker so we don't trigger a new capture.
        worker = getattr(self._camera_service, "_worker", None)
        if worker is not None and hasattr(worker, "latest_frame"):
            try:
                return worker.latest_frame()
            except Exception:
                return None
        return None

    def _encode_packet(self, packet) -> tuple[str, int, int]:
        pixels = getattr(packet, "pixels", None)
        if pixels is None:
            return ("", 0, 0)

        try:
            return self._encode_with_cv2(pixels, packet)
        except Exception:
            pass

        try:
            return self._encode_with_pillow(pixels, packet)
        except Exception:
            return ("", 0, 0)

    def _encode_with_cv2(self, pixels, packet) -> tuple[str, int, int]:
        import cv2  # type: ignore
        import numpy as np  # type: ignore

        arr = np.asarray(pixels)
        if arr.ndim != 3:
            return ("", 0, 0)

        h, w = int(arr.shape[0]), int(arr.shape[1])
        if h <= 0 or w <= 0:
            return ("", 0, 0)

        long_edge = max(h, w)
        if long_edge > self._long_edge_px:
            scale = float(self._long_edge_px) / float(long_edge)
            new_w = max(2, int(w * scale))
            new_h = max(2, int(h * scale))
            arr = cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_AREA)
            w, h = new_w, new_h

        # Most NeXa capture backends already produce BGR; if it's RGB the
        # preview will look slightly off but won't crash.
        backend = str(getattr(packet, "backend_label", "")).lower()
        if backend in ("picamera2", "rgb"):
            arr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        ok, buf = cv2.imencode(
            ".jpg",
            arr,
            [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality],
        )
        if not ok:
            return ("", 0, 0)
        return (base64.b64encode(buf.tobytes()).decode("ascii"), w, h)

    def _encode_with_pillow(self, pixels, packet) -> tuple[str, int, int]:
        from PIL import Image  # type: ignore
        import numpy as np  # type: ignore

        arr = np.asarray(pixels)
        if arr.ndim != 3:
            return ("", 0, 0)
        h, w = int(arr.shape[0]), int(arr.shape[1])
        if h <= 0 or w <= 0:
            return ("", 0, 0)

        backend = str(getattr(packet, "backend_label", "")).lower()
        if backend in ("opencv", "bgr"):
            arr = arr[:, :, ::-1]  # BGR → RGB

        img = Image.fromarray(arr.astype("uint8"))
        long_edge = max(h, w)
        if long_edge > self._long_edge_px:
            scale = float(self._long_edge_px) / float(long_edge)
            img = img.resize(
                (max(2, int(w * scale)), max(2, int(h * scale))),
                Image.BILINEAR,
            )
            w, h = img.size

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=self._jpeg_quality, optimize=False)
        return (base64.b64encode(buf.getvalue()).decode("ascii"), int(w), int(h))


__all__ = ["FeedbackVisionStreamer"]
