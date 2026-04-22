# modules/devices/vision/perception/objects/hailo_yolo_detector.py
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from modules.devices.vision.capture import FramePacket
from modules.devices.vision.perception.models import ObjectDetection
from modules.devices.vision.perception.objects.hailo_runtime import (
    HailoDeviceManager,
    HailoRuntimeError,
    HailoUnavailableError,
    HefInferenceRunner,
    get_hailo_device_manager,
)
from modules.devices.vision.perception.objects.postprocess import (
    postprocess_yolo_detections,
)
from modules.devices.vision.preprocessing import preprocess_frame_for_yolo
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


class _PreprocessFn(Protocol):
    def __call__(self, packet: FramePacket, *, target_size: int = 640) -> Any:
        ...


@dataclass(slots=True)
class HailoYoloObjectDetector:
    """
    Hailo-backed YOLOv11m object detector for NeXa.

    Responsibilities:
    - Lazily initialize the Hailo device manager + HEF inference runner on
      first detect_objects() call (or via explicit initialize()).
    - Execute: preprocess frame -> Hailo inference -> postprocess detections.
    - Expose broker-ready cadence controls for Etap D:
        * set_inference_cadence_hz(hz): 0.0 pauses, N runs at N inferences/sec
        * pause() / resume() convenience
        * is_paused(), current_cadence_hz(), last_inference_timing_ms()
    - Gracefully no-op when paused or when cadence window has not elapsed —
      returning the last known detections so downstream pipeline stays stable.
    - Gracefully no-op when Hailo is unavailable, returning () and logging once.

    Thread safety:
    - detect_objects() is safe to call from a single capture thread.
    - Cadence setters are safe to call from any thread.
    - Hailo device access is internally serialized by HailoDeviceManager.
    """

    backend_label: str = "hailo_yolov11"
    hef_path: str = "/usr/share/hailo-models/yolov11m_h10.hef"
    score_threshold: float = 0.35
    max_detections: int = 30
    desk_relevant_only: bool = False
    initial_cadence_hz: float = 2.0

    # Injected for tests — production path resolves these lazily.
    device_manager: HailoDeviceManager | None = None
    inference_runner: HefInferenceRunner | None = None
    preprocess_fn: _PreprocessFn = field(default=preprocess_frame_for_yolo)
    target_input_size: int = 640

    # Internal state (not set by constructor callers).
    _cadence_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _cadence_hz: float = field(default=0.0, init=False, repr=False)
    _last_inference_monotonic: float = field(default=0.0, init=False, repr=False)
    _last_detections: tuple[ObjectDetection, ...] = field(default=(), init=False, repr=False)
    _last_timing_ms: dict[str, float] = field(default_factory=dict, init=False, repr=False)
    _initialized: bool = field(default=False, init=False, repr=False)
    _initialize_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _unavailable_reason: str | None = field(default=None, init=False, repr=False)
    _availability_warning_logged: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        # Seed cadence from config-provided initial value.
        with self._cadence_lock:
            self._cadence_hz = max(0.0, float(self.initial_cadence_hz))

    # ------------------------------------------------------------------
    # ObjectDetector protocol
    # ------------------------------------------------------------------

    def detect_objects(self, packet: FramePacket) -> tuple[ObjectDetection, ...]:
        """
        Protocol entry point called by PerceptionPipeline per frame.

        Returns the most recent detections. An inference call is made only
        when cadence allows (and the detector is not paused and Hailo is
        available). Otherwise the last known result is returned so the
        downstream behavior layer sees continuity.
        """
        if self._is_unavailable():
            return ()

        if not self._should_run_now():
            return self._last_detections

        if not self._ensure_initialized():
            return self._last_detections

        try:
            return self._run_inference_cycle(packet)
        except HailoRuntimeError as error:
            LOGGER.warning("HailoYoloObjectDetector: inference failed. %s", error)
            # Keep last-known detections; do not clear on transient error.
            return self._last_detections

    # ------------------------------------------------------------------
    # Broker-ready cadence API
    # ------------------------------------------------------------------

    def set_inference_cadence_hz(self, hz: float) -> None:
        """
        Set how often inference may run, in Hz.

        - 0.0 pauses the detector (last detections are served on each call).
        - Positive value allows up to N inferences per second.

        Safe to call from any thread.
        """
        new_value = max(0.0, float(hz))
        with self._cadence_lock:
            if new_value != self._cadence_hz:
                LOGGER.info(
                    "HailoYoloObjectDetector: cadence changed %.2f Hz -> %.2f Hz",
                    self._cadence_hz,
                    new_value,
                )
            self._cadence_hz = new_value

    def pause(self) -> None:
        self.set_inference_cadence_hz(0.0)

    def resume(self, hz: float | None = None) -> None:
        """Resume inference at the provided cadence, or initial cadence if None."""
        target = float(hz) if hz is not None else float(self.initial_cadence_hz)
        self.set_inference_cadence_hz(target)

    def is_paused(self) -> bool:
        with self._cadence_lock:
            return self._cadence_hz <= 0.0

    def current_cadence_hz(self) -> float:
        with self._cadence_lock:
            return self._cadence_hz

    def last_inference_timing_ms(self) -> dict[str, float]:
        return dict(self._last_timing_ms)

    def status(self) -> dict[str, Any]:
        """Structured status for diagnostics overlays and health checks."""
        with self._cadence_lock:
            cadence = self._cadence_hz
        return {
            "backend": self.backend_label,
            "hef_path": str(self.hef_path),
            "initialized": self._initialized,
            "unavailable_reason": self._unavailable_reason,
            "cadence_hz": cadence,
            "paused": cadence <= 0.0,
            "last_detection_count": len(self._last_detections),
            "last_timing_ms": dict(self._last_timing_ms),
            "score_threshold": self.score_threshold,
            "max_detections": self.max_detections,
            "desk_relevant_only": self.desk_relevant_only,
        }

    # ------------------------------------------------------------------
    # Explicit lifecycle
    # ------------------------------------------------------------------

    def initialize(self) -> bool:
        """
        Eagerly initialize the device manager + HEF runner.

        Returns True on success, False if Hailo is unavailable. Safe to call
        multiple times — subsequent calls are no-ops if already initialized.
        """
        return self._ensure_initialized()

    def close(self) -> None:
        """Release the HEF runner. Device manager is shared and NOT closed here."""
        with self._initialize_lock:
            if self.inference_runner is not None:
                try:
                    self.inference_runner.unload()
                except Exception as error:
                    LOGGER.warning("HailoYoloObjectDetector: error during unload. %s", error)
            self._initialized = False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _is_unavailable(self) -> bool:
        return self._unavailable_reason is not None

    def _should_run_now(self) -> bool:
        """Gate inference on cadence + paused state."""
        with self._cadence_lock:
            cadence = self._cadence_hz
            last = self._last_inference_monotonic

        if cadence <= 0.0:
            return False

        if last <= 0.0:
            # First call — run immediately.
            return True

        min_interval = 1.0 / cadence
        now = time.monotonic()
        return (now - last) >= min_interval

    def _ensure_initialized(self) -> bool:
        if self._initialized:
            return True
        if self._unavailable_reason is not None:
            return False

        with self._initialize_lock:
            if self._initialized:
                return True
            if self._unavailable_reason is not None:
                return False

            try:
                manager = self.device_manager or get_hailo_device_manager()
                if not manager.is_ready():
                    manager.open()

                if self.inference_runner is None:
                    hef_path = Path(self.hef_path)
                    self.inference_runner = HefInferenceRunner(
                        manager,
                        hef_path=hef_path,
                    )

                if not self.inference_runner.is_loaded():
                    self.inference_runner.load()

                self.device_manager = manager
                self._initialized = True
                LOGGER.info(
                    "HailoYoloObjectDetector: initialized (hef=%s, score>=%.2f, max=%d, cadence=%.2f Hz)",
                    Path(self.hef_path).name,
                    self.score_threshold,
                    self.max_detections,
                    self._cadence_hz,
                )
                return True
            except HailoUnavailableError as error:
                self._unavailable_reason = f"hailo_unavailable: {error}"
                if not self._availability_warning_logged:
                    LOGGER.warning(
                        "HailoYoloObjectDetector: Hailo unavailable. Falling back silently. %s",
                        error,
                    )
                    self._availability_warning_logged = True
                return False
            except HailoRuntimeError as error:
                self._unavailable_reason = f"hailo_runtime_error: {error}"
                LOGGER.warning(
                    "HailoYoloObjectDetector: runtime initialization failed. %s",
                    error,
                )
                return False

    def _run_inference_cycle(self, packet: FramePacket) -> tuple[ObjectDetection, ...]:
        assert self.inference_runner is not None  # narrowing after _ensure_initialized

        preprocess_start = time.perf_counter()
        tensor, transform = self.preprocess_fn(packet, target_size=self.target_input_size)
        preprocess_ms = (time.perf_counter() - preprocess_start) * 1000.0

        inference_result = self.inference_runner.infer(tensor)

        postprocess_start = time.perf_counter()
        detections = postprocess_yolo_detections(
            inference_result.detections,
            transform=transform,
            score_threshold=self.score_threshold,
            max_detections=self.max_detections,
            desk_relevant_only=self.desk_relevant_only,
        )
        postprocess_ms = (time.perf_counter() - postprocess_start) * 1000.0

        now = time.monotonic()
        with self._cadence_lock:
            self._last_inference_monotonic = now
        self._last_detections = detections
        self._last_timing_ms = {
            "preprocess_ms": round(preprocess_ms, 3),
            "inference_ms": round(inference_result.inference_ms, 3),
            "postprocess_ms": round(postprocess_ms, 3),
        }
        return detections