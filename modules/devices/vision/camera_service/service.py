from __future__ import annotations

import threading
from typing import Any

from modules.devices.vision.behavior import BehaviorPipeline
from modules.devices.vision.capture import VisionCaptureReader
from modules.devices.vision.config import VisionRuntimeConfig
from modules.devices.vision.fusion import build_vision_observation
from modules.devices.vision.perception import PerceptionPipeline
from modules.devices.vision.sessions import VisionSessionTracker
from modules.devices.vision.stabilization import BehaviorStabilizer
from modules.runtime.contracts import VisionObservation
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


class CameraService:
    """
    Stable public entrypoint for the NeXa vision subsystem.

    Stage 1 responsibilities:
    - own the capture reader lifecycle
    - expose a stable latest_observation() API for the runtime
    - return a real camera-backed VisionObservation snapshot
    - keep the perception / behavior layers decoupled for later stages

    Stage 2 foundation:
    - run a clean perception pipeline with separate people/object/scene contracts
    - keep behavior inference out of the camera service itself
    - track activity sessions over time

    Stage 3 detector foundation:
    - load configurable detector backends
    - expose active detector status
    - support real people / face detection paths

    Stage 4 stabilization:
    - smooth short detector drops
    - reduce flicker in activity booleans
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = VisionRuntimeConfig.from_mapping(config)
        if not self._config.enabled:
            raise ValueError("CameraService requires vision.enabled=true in config.")

        self._lock = threading.RLock()
        self._reader = VisionCaptureReader(config=self._config)
        self._perception = PerceptionPipeline.from_config(self._config)
        self._behavior = BehaviorPipeline()
        self._stabilizer = BehaviorStabilizer.from_config(self._config)
        self._sessions = VisionSessionTracker()
        self._last_observation: VisionObservation | None = None
        self._last_error: str | None = None
        self._closed = False

        if not self._config.lazy_start:
            observation = self.latest_observation(force_refresh=True)
            if observation is None and self._last_error is not None:
                raise RuntimeError(f"Vision startup capture failed: {self._last_error}")

    def latest_observation(self, *, force_refresh: bool = True) -> VisionObservation | None:
        with self._lock:
            if self._closed:
                return self._last_observation

            if self._last_observation is None or force_refresh:
                try:
                    return self._capture_once_locked()
                except Exception as error:
                    self._last_error = f"{error.__class__.__name__}: {error}"
                    LOGGER.warning("Vision capture failed. %s", self._last_error)
                    return self._last_observation

            return self._last_observation

    def status(self) -> dict[str, Any]:
        with self._lock:
            last = self._last_observation
            return {
                "ok": self._last_error is None and not self._closed,
                "enabled": self._config.enabled,
                "backend": self._reader.active_backend or self._config.backend,
                "requested_backend": self._config.backend,
                "fallback_backend": self._config.fallback_backend,
                "frame_width": self._config.frame_width,
                "frame_height": self._config.frame_height,
                "lazy_start": self._config.lazy_start,
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
            }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return

            try:
                self._reader.close()
            finally:
                self._closed = True

    def _capture_once_locked(self) -> VisionObservation:
        packet = self._reader.read_frame()
        perception = self._perception.analyze(packet)
        raw_behavior = self._behavior.analyze(perception)
        behavior = self._stabilizer.stabilize(raw_behavior, packet.captured_at)
        sessions = self._sessions.update(behavior, packet.captured_at)

        observation = build_vision_observation(
            packet,
            perception=perception,
            behavior=behavior,
            sessions=sessions,
        )

        self._last_observation = observation
        self._last_error = None

        LOGGER.info(
            "Vision snapshot captured: backend=%s size=%sx%s people=%s faces=%s objects=%s presence=%s desk=%s phone=%s computer=%s study=%s presence_seconds=%s",
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