from __future__ import annotations

import threading
from typing import Any

from modules.devices.vision.capture import VisionCaptureReader
from modules.devices.vision.config import VisionRuntimeConfig
from modules.devices.vision.fusion import build_camera_only_observation
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
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = VisionRuntimeConfig.from_mapping(config)
        if not self._config.enabled:
            raise ValueError("CameraService requires vision.enabled=true in config.")

        self._lock = threading.RLock()
        self._reader = VisionCaptureReader(config=self._config)
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
        observation = build_camera_only_observation(packet)
        self._last_observation = observation
        self._last_error = None

        LOGGER.info(
            "Vision snapshot captured: backend=%s size=%sx%s",
            packet.backend_label,
            packet.width,
            packet.height,
        )
        return observation