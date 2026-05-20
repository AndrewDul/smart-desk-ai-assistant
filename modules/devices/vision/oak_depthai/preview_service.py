"""Managed OAK-D Lite RGB/depth preview service.

Starts a depthai Gen3 pipeline in a background thread, captures RGB and depth
frames at low FPS, and exposes the latest frames plus streaming telemetry.

Lifecycle is controlled by the caller (FeedbackLane):
  - start()  — opens device, starts capture thread
  - stop()   — signals thread, joins, releases device

Get the module-level singleton via get_preview_service().
The singleton is never started automatically; the caller must call start().
"""
from __future__ import annotations

import importlib.util
import threading
import time
from typing import Any

from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)

_TARGET_FPS = 10.0
_RGB_WIDTH = 640
_RGB_HEIGHT = 400


def _depthai_available() -> bool:
    """Return True if depthai can be imported (handles test mocks in sys.modules)."""
    import sys as _sys
    if "depthai" in _sys.modules:
        return True
    try:
        return importlib.util.find_spec("depthai") is not None
    except ValueError:
        return True


class OakPreviewFrame:
    """Single captured frame (RGB or depth) from the OAK-D Lite."""

    __slots__ = ("pixels", "width", "height", "channels", "kind", "captured_at_ms")

    def __init__(
        self,
        *,
        pixels: Any,
        width: int,
        height: int,
        channels: int,
        kind: str,
    ) -> None:
        self.pixels = pixels
        self.width = int(width)
        self.height = int(height)
        self.channels = int(channels)
        self.kind = str(kind)
        self.captured_at_ms = time.monotonic() * 1000.0


class OakPreviewService:
    """Managed OAK-D Lite RGB+depth preview service.

    Runs a depthai Gen3 pipeline in a single background daemon thread.
    All public properties are thread-safe.
    """

    def __init__(
        self,
        *,
        target_fps: float = _TARGET_FPS,
        rgb_width: int = _RGB_WIDTH,
        rgb_height: int = _RGB_HEIGHT,
    ) -> None:
        self._target_fps = float(target_fps)
        self._rgb_width = int(rgb_width)
        self._rgb_height = int(rgb_height)

        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._latest_rgb: OakPreviewFrame | None = None
        self._latest_depth: OakPreviewFrame | None = None
        self._rgb_frame_count: int = 0
        self._depth_frame_count: int = 0
        self._fps_estimate: float = 0.0
        self._last_frame_at: float | None = None
        self._last_error: str = ""
        self._device_mxid: str = ""

    def start(self) -> bool:
        """Open the OAK device and start the capture thread.

        Returns False without starting if depthai is not installed
        or if the service is already running.
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            if not _depthai_available():
                self._last_error = "depthai not installed"
                return False
            self._stop_event.clear()
            self._latest_rgb = None
            self._latest_depth = None
            self._rgb_frame_count = 0
            self._depth_frame_count = 0
            self._fps_estimate = 0.0
            self._last_frame_at = None
            self._last_error = ""
            self._device_mxid = ""
            self._thread = threading.Thread(
                target=self._run,
                name="nexa-oak-preview",
                daemon=True,
            )
            self._thread.start()
        LOGGER.info(
            "OAK preview service started: fps=%.0f rgb=%dx%d",
            self._target_fps, self._rgb_width, self._rgb_height,
        )
        return True

    def stop(self, *, timeout: float = 3.0) -> bool:
        """Stop the capture thread and release the OAK device."""
        with self._lock:
            thread = self._thread
            if thread is None:
                return False
            self._stop_event.set()
        thread.join(timeout=timeout)
        with self._lock:
            self._thread = None
        LOGGER.info("OAK preview service stopped")
        return True

    @property
    def is_running(self) -> bool:
        with self._lock:
            t = self._thread
            return t is not None and t.is_alive()

    @property
    def rgb_frame_count(self) -> int:
        with self._lock:
            return self._rgb_frame_count

    @property
    def depth_frame_count(self) -> int:
        with self._lock:
            return self._depth_frame_count

    @property
    def fps(self) -> float:
        with self._lock:
            return self._fps_estimate

    @property
    def last_frame_age_ms(self) -> float | None:
        with self._lock:
            if self._last_frame_at is None:
                return None
            return round((time.monotonic() - self._last_frame_at) * 1000.0, 1)

    @property
    def last_error(self) -> str:
        with self._lock:
            return self._last_error

    @property
    def device_mxid(self) -> str:
        with self._lock:
            return self._device_mxid

    def latest_rgb_frame(self) -> OakPreviewFrame | None:
        with self._lock:
            return self._latest_rgb

    def latest_depth_frame(self) -> OakPreviewFrame | None:
        with self._lock:
            return self._latest_depth

    def latest_preview_payload(self) -> dict[str, Any] | None:
        """Return base64-encoded JPEG payload for Visual Shell transport, or None."""
        frame = self.latest_rgb_frame()
        if frame is None:
            return None
        try:
            import base64
            import cv2  # type: ignore
            import numpy as np  # type: ignore
            arr = np.asarray(frame.pixels)
            ok, buf = cv2.imencode(".jpg", arr, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if not ok:
                return None
            return {
                "jpeg_b64": base64.b64encode(buf.tobytes()).decode("ascii"),
                "width": frame.width,
                "height": frame.height,
            }
        except Exception:
            return None

    def status(self) -> dict[str, Any]:
        """Return a snapshot of current preview state (no side effects, lock-safe)."""
        with self._lock:
            age_ms = None
            if self._last_frame_at is not None:
                age_ms = round((time.monotonic() - self._last_frame_at) * 1000.0, 1)
            running = self._thread is not None and self._thread.is_alive()
            return {
                "active_streaming": running,
                "rgb_frame_count": self._rgb_frame_count,
                "depth_frame_count": self._depth_frame_count,
                "fps": round(self._fps_estimate, 1),
                "last_frame_age_ms": age_ms,
                "last_error": self._last_error,
                "device_mxid": self._device_mxid,
            }

    # ------------------------------------------------------------------
    # Internal pipeline (depthai Gen3 API)

    def _run(self) -> None:
        try:
            self._run_pipeline()
        except Exception as exc:
            LOGGER.warning("OAK preview pipeline failed: %s", exc)
            with self._lock:
                self._last_error = str(exc)

    def _run_pipeline(self) -> None:
        try:
            import depthai as dai  # type: ignore
        except ImportError:
            with self._lock:
                self._last_error = "depthai import failed at runtime"
            return

        pipeline = dai.Pipeline()

        # RGB camera (Gen3: Camera node + requestOutput)
        try:
            cam = pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_A)
            rgb_out = cam.requestOutput(
                (self._rgb_width, self._rgb_height),
                type=dai.ImgFrame.Type.BGR888p,
                fps=self._target_fps,
            )
            rgb_q = rgb_out.createOutputQueue(maxSize=4, blocking=False)
        except Exception as exc:
            err = str(exc)
            LOGGER.warning("OAK RGB camera setup failed: %s", err)
            with self._lock:
                self._last_error = err
            return

        # Depth pipeline (Gen3: StereoDepth.build with autoCreateCameras)
        depth_q: Any = None
        try:
            stereo = pipeline.create(dai.node.StereoDepth).build(
                autoCreateCameras=True,
                presetMode=dai.node.StereoDepth.PresetMode.DEFAULT,
                size=(self._rgb_width, self._rgb_height),
                fps=self._target_fps,
            )
            depth_q = stereo.depth.createOutputQueue(maxSize=4, blocking=False)
        except Exception as exc:
            LOGGER.info("OAK depth pipeline skipped (RGB-only mode): %s", exc)

        # Build pipeline to connect to device and read MXID
        try:
            pipeline.build()
            dev = pipeline.getDefaultDevice()
            if dev is not None:
                with self._lock:
                    try:
                        self._device_mxid = str(dev.getDeviceId())
                    except Exception:
                        self._device_mxid = str(dev.getMxId())
        except Exception as exc:
            err = str(exc)
            LOGGER.warning("OAK pipeline build failed: %s", err)
            with self._lock:
                self._last_error = err
            return

        # Run pipeline in a nested thread (p.run() blocks until stopped)
        pipeline_thread_done = threading.Event()

        def _pipeline_run() -> None:
            try:
                pipeline.run()
            except Exception as exc:
                LOGGER.debug("OAK pipeline run ended: %s", exc)
            finally:
                pipeline_thread_done.set()

        run_thread = threading.Thread(
            target=_pipeline_run,
            name="nexa-oak-pipeline-run",
            daemon=True,
        )
        run_thread.start()

        try:
            self._capture_loop(rgb_q, depth_q)
        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
        finally:
            try:
                pipeline.__exit__(None, None, None)
            except Exception:
                pass
            pipeline_thread_done.wait(timeout=3.0)

    def _capture_loop(self, rgb_q: Any, depth_q: Any | None) -> None:
        fps_window: list[float] = []

        while not self._stop_event.is_set():
            captured = False

            if rgb_q.has():
                packet = rgb_q.get()
                arr = packet.getCvFrame()
                if arr is not None and arr.ndim >= 2:
                    h, w = int(arr.shape[0]), int(arr.shape[1])
                    frame = OakPreviewFrame(
                        pixels=arr,
                        width=w,
                        height=h,
                        channels=3 if arr.ndim == 3 else 1,
                        kind="rgb",
                    )
                    now = time.monotonic()
                    fps_window.append(now)
                    fps_window = [t for t in fps_window if now - t < 2.0]
                    fps_est = len(fps_window) / 2.0 if fps_window else 0.0
                    with self._lock:
                        self._latest_rgb = frame
                        self._rgb_frame_count += 1
                        self._last_frame_at = now
                        self._fps_estimate = fps_est
                    captured = True

            if depth_q is not None and depth_q.has():
                packet = depth_q.get()
                arr = packet.getCvFrame()
                if arr is not None and arr.ndim >= 2:
                    arr_vis = self._normalize_depth(arr)
                    h, w = int(arr_vis.shape[0]), int(arr_vis.shape[1])
                    frame = OakPreviewFrame(
                        pixels=arr_vis,
                        width=w,
                        height=h,
                        channels=3,
                        kind="depth",
                    )
                    with self._lock:
                        self._latest_depth = frame
                        self._depth_frame_count += 1
                    captured = True

            if not captured:
                self._stop_event.wait(timeout=0.010)

    def _normalize_depth(self, arr: Any) -> Any:
        try:
            import cv2  # type: ignore
            arr8 = cv2.normalize(arr, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            return cv2.cvtColor(arr8, cv2.COLOR_GRAY2BGR)
        except Exception:
            return arr


# Module-level singleton — created on first access, never started automatically.
_singleton_lock = threading.Lock()
_singleton: OakPreviewService | None = None


def get_preview_service() -> OakPreviewService:
    """Return the shared OAK preview service instance (never auto-starts it)."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                _singleton = OakPreviewService()
    return _singleton


__all__ = [
    "OakPreviewFrame",
    "OakPreviewService",
    "get_preview_service",
]
