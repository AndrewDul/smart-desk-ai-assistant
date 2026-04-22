# modules/devices/vision/camera_service/service.py
from __future__ import annotations

import threading
import time
from typing import Any

from modules.devices.vision.behavior import BehaviorPipeline
from modules.devices.vision.capture import ContinuousCaptureWorker, VisionCaptureReader
from modules.devices.vision.capture.frame_packet import FramePacket
from modules.devices.vision.config import VisionRuntimeConfig
from modules.devices.vision.diagnostics import build_diagnostics_snapshot
from modules.devices.vision.fusion import build_vision_observation
from modules.devices.vision.perception import PerceptionPipeline
from modules.devices.vision.sessions import VisionSessionTracker
from modules.devices.vision.stabilization import BehaviorStabilizer
from modules.runtime.contracts import VisionObservation
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)

# How long latest_observation() will wait for the first frame in
# continuous mode before giving up and returning None.
_FIRST_FRAME_WAIT_SECONDS = 3.0
_FIRST_FRAME_POLL_INTERVAL = 0.05


class CameraService:
    """
    Stable public entrypoint for the NeXa vision subsystem.

    Two operating modes:
    - Continuous mode (continuous_capture_enabled=True):
        A background thread reads frames at target_fps.
        latest_observation() runs perception/behavior on the latest buffered
        frame without ever blocking on camera I/O.
    - On-demand mode (continuous_capture_enabled=False):
        Legacy synchronous capture — one blocking read per call.

    Lifecycle: __init__ → start() → latest_observation() [repeatedly] → close()
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = VisionRuntimeConfig.from_mapping(config)
        if not self._config.enabled:
            raise ValueError("CameraService requires vision.enabled=true in config.")

        self._pipeline_lock = threading.RLock()
        self._reader = VisionCaptureReader(config=self._config)
        self._perception = PerceptionPipeline.from_config(self._config)
        self._behavior = BehaviorPipeline()
        self._stabilizer = BehaviorStabilizer.from_config(self._config)
        self._sessions = VisionSessionTracker()
        self._last_observation: VisionObservation | None = None
        self._last_error: str | None = None
        self._closed = False

        # Continuous capture worker — only created when mode is enabled.
        self._worker: ContinuousCaptureWorker | None = None
        if self._config.continuous_capture_enabled:
            self._worker = ContinuousCaptureWorker(
                self._reader,
                target_fps=self._config.continuous_capture_target_fps,
                error_backoff_seconds=self._config.continuous_capture_error_backoff_seconds,
            )

        if not self._config.lazy_start:
            self._eager_start()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """
        Start the continuous capture worker (if enabled).
        Safe to call multiple times — subsequent calls are no-ops.
        """
        if self._worker is not None and not self._worker.is_running:
            self._worker.start()
            LOGGER.info("CameraService: continuous capture started.")

    def close(self) -> None:
        with self._pipeline_lock:
            if self._closed:
                return

            if self._worker is not None:
                self._worker.stop(
                    timeout_seconds=self._config.continuous_capture_stop_timeout_seconds
                )

            try:
                self._reader.close()
            finally:
                self._closed = True
                LOGGER.info("CameraService closed.")

    # ------------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------------

    def latest_observation(self, *, force_refresh: bool = True) -> VisionObservation | None:
        """
        Return the most recent VisionObservation.

        In continuous mode:
            Runs perception + behavior on the latest buffered frame.
            Never blocks on camera I/O. If no frame is available yet
            (first call before first frame arrives), waits up to
            _FIRST_FRAME_WAIT_SECONDS before returning None.

        In on-demand mode:
            Synchronous capture — same as before this change.
        """
        with self._pipeline_lock:
            if self._closed:
                return self._last_observation

            if self._worker is not None:
                return self._observation_from_worker()

            # On-demand path (legacy).
            if self._last_observation is None or force_refresh:
                try:
                    return self._capture_once_locked()
                except Exception as error:
                    self._last_error = f"{error.__class__.__name__}: {error}"
                    LOGGER.warning("Vision on-demand capture failed. %s", self._last_error)
                    return self._last_observation

            return self._last_observation

    def status(self) -> dict[str, Any]:
        with self._pipeline_lock:
            last = self._last_observation
            worker_stats = self._worker.stats() if self._worker is not None else None
            return {
                "ok": self._last_error is None and not self._closed,
                "enabled": self._config.enabled,
                "backend": self._reader.active_backend or self._config.backend,
                "requested_backend": self._config.backend,
                "fallback_backend": self._config.fallback_backend,
                "frame_width": self._config.frame_width,
                "frame_height": self._config.frame_height,
                "lazy_start": self._config.lazy_start,
                "continuous_capture_enabled": self._config.continuous_capture_enabled,
                "continuous_capture_target_fps": self._config.continuous_capture_target_fps,
                "closed": self._closed,
                "last_capture_available": last is not None,
                "last_captured_at": None if last is None else last.captured_at,
                "last_error": self._last_error,
                "capabilities": self._config.capability_flags(),
                "detectors": self._perception.detector_status(),
                "perception_pipeline_ready": True,
                "behavior_pipeline_ready": True,
                "stabilization_pipeline_ready": True,
                "session_tracker_ready": True,
                "worker": worker_stats,
            }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _eager_start(self) -> None:
        """Called from __init__ when lazy_start=False."""
        if self._worker is not None:
            self._worker.start()
            # Wait briefly for the first frame to arrive before returning.
            deadline = time.monotonic() + _FIRST_FRAME_WAIT_SECONDS
            while time.monotonic() < deadline:
                if self._worker.latest_frame() is not None:
                    break
                time.sleep(_FIRST_FRAME_POLL_INTERVAL)

        observation = self.latest_observation(force_refresh=True)
        if observation is None and self._last_error is not None:
            raise RuntimeError(f"Vision startup capture failed: {self._last_error}")

    def _observation_from_worker(self) -> VisionObservation | None:
        """
        Grab the latest frame from the worker and run the full pipeline.
        If the worker has no frame yet, poll briefly for the first one.
        """
        packet = self._worker.latest_frame()

        if packet is None:
            # Worker just started — wait for first frame.
            deadline = time.monotonic() + _FIRST_FRAME_WAIT_SECONDS
            while time.monotonic() < deadline:
                time.sleep(_FIRST_FRAME_POLL_INTERVAL)
                packet = self._worker.latest_frame()
                if packet is not None:
                    break

        if packet is None:
            self._last_error = "No frame available from continuous capture worker."
            LOGGER.warning("CameraService: %s", self._last_error)
            return self._last_observation

        try:
            return self._run_pipeline(packet)
        except Exception as error:
            self._last_error = f"{error.__class__.__name__}: {error}"
            LOGGER.warning("Vision pipeline failed on buffered frame. %s", self._last_error)
            return self._last_observation

    def _capture_once_locked(self) -> VisionObservation:
        """On-demand synchronous capture path."""
        packet = self._reader.read_frame()
        return self._run_pipeline(packet)

    def _run_pipeline(self, packet: FramePacket) -> VisionObservation:
        """Run perception → behavior → stabilize → sessions → build observation."""
        perception = self._perception.analyze(packet)
        raw_behavior = self._behavior.analyze(perception)
        behavior = self._stabilizer.stabilize(raw_behavior, packet.captured_at)
        sessions = self._sessions.update(behavior, packet.captured_at)
        diagnostics = build_diagnostics_snapshot(
            packet,
            perception=perception,
            raw_behavior=raw_behavior,
            behavior=behavior,
            sessions=sessions,
        )
        observation = build_vision_observation(
            packet,
            perception=perception,
            behavior=behavior,
            sessions=sessions,
        )
        observation.metadata["diagnostics"] = diagnostics.to_dict()
        self._last_observation = observation
        self._last_error = None

        LOGGER.info(
            "Vision snapshot: backend=%s size=%sx%s people=%s faces=%s objects=%s "
            "presence=%s desk=%s phone=%s computer=%s study=%s presence_sec=%s",
            packet.backend_label,
            packet.width,
            packet.height,
            len(perception.people),
            len(perception.faces),
            len(perception.objects),
            behavior.presence.active,
            behavior.desk_activity.active,
            behavior.phone_usage.active,
            behavior.computer_work.active,
            behavior.study_activity.active,
            sessions.presence.current_active_seconds,
        )
        return observation