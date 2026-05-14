"""
LookAtMeSession — single-process, single-camera-owner face tracker.

Architecture
============
The previous "look at me" implementation spawned a subprocess (Picamera2 owner
#2) which fought with the main runtime CameraService (Picamera2 owner #1) and
produced "Failed to acquire camera: Device or resource busy". The control
script the subprocess targeted (control_vision_look_at_me_runtime.py) didn't
even exist, so the entire path was broken.

This module replaces both pieces:

    CameraService.latest_observation()  -> returns VisionObservation with the
       │                                    full perception pipeline already
       │                                    run (Haar face detector, Hailo
       │                                    object detector, etc.).
       ▼
    LookAtMeSession (this module)
       │   - subscribes to CameraService.latest_observation() in a worker
       │     thread at ~25fps
       │   - extracts face boxes from observation.metadata.perception.faces
       │   - if face seen      -> TrackingPlanner -> pan/tilt move_delta
       │   - if no face for N  -> ScanPlanner    -> sweep X + Y
       │   - all moves go through pan_tilt_backend.move_delta(...) which
       │     enforces safe_limits, calibration gate, and serial write gate.
       ▼
    PanTiltService (waveshare_serial backend already exists)

There is NO subprocess. There is NO second camera owner. There is no
hand-off-then-reacquire dance. The tracker shares the SAME camera frames the
rest of NEXA already uses, and stops cleanly when told to stop.

Public API
==========
    session = LookAtMeSession.from_settings(
        settings=settings,
        vision_backend=vision,           # CameraService
        pan_tilt_backend=pan_tilt,       # PanTiltService backend
    )
    session.start(language="en")         # non-blocking, returns immediately
    session.is_active()                  # bool
    session.status()                     # diagnostic dict
    session.stop()                       # also returns pan/tilt to center
    session.close()                      # stop + drop hardware references
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from modules.shared.logging.logger import get_logger

from .scan_planner import ScanPlanner
from .tracking_planner import TrackingPlanner

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class LookAtMeStatus:
    """Diagnostic snapshot exposed via `session.status()`."""

    enabled: bool = True
    active: bool = False
    started_at: float = 0.0
    last_face_at: float = 0.0
    face_seen_count: int = 0
    no_face_streak: int = 0
    move_count: int = 0
    scan_count: int = 0
    last_reason: str = ""
    last_error: str = ""
    last_language: str = ""
    pan_angle: float = 0.0
    tilt_angle: float = 0.0
    fps_target: float = 0.0
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "active": self.active,
            "started_at": round(self.started_at, 3),
            "last_face_at": round(self.last_face_at, 3),
            "face_seen_count": self.face_seen_count,
            "no_face_streak": self.no_face_streak,
            "move_count": self.move_count,
            "scan_count": self.scan_count,
            "last_reason": self.last_reason,
            "last_error": self.last_error,
            "last_language": self.last_language,
            "pan_angle": round(self.pan_angle, 3),
            "tilt_angle": round(self.tilt_angle, 3),
            "fps_target": round(self.fps_target, 2),
            "config": dict(self.config),
        }


class LookAtMeSession:
    """In-process face tracker driven by an existing CameraService."""

    def __init__(
        self,
        *,
        vision_backend: Any,
        pan_tilt_backend: Any | None,
        config: dict[str, Any] | None = None,
    ) -> None:
        cfg = dict(config or {})
        self._vision_backend = vision_backend
        self._pan_tilt_backend = pan_tilt_backend
        self._enabled = bool(cfg.get("enabled", True))

        self._target_fps = max(5.0, float(cfg.get("target_fps", 25.0)))
        self._scan_after_no_face_frames = max(2, int(cfg.get("scan_after_no_face_frames", 6)))
        self._scan_interval_seconds = max(0.04, float(cfg.get("scan_interval_seconds", 0.16)))
        self._return_to_center_on_stop = bool(cfg.get("return_to_center_on_stop", True))
        self._max_runtime_seconds = float(cfg.get("max_runtime_seconds", 600.0))

        tracking_cfg = dict(cfg.get("tracking", {}) or {})
        self._tracker = TrackingPlanner(
            pan_gain_degrees=float(cfg.get("pan_gain_degrees", tracking_cfg.get("pan_gain_degrees", 22.0))),
            tilt_gain_degrees=float(cfg.get("tilt_gain_degrees", tracking_cfg.get("tilt_gain_degrees", 24.0))),
            target_x_norm=float(tracking_cfg.get("target_x_norm", 0.5)),
            target_y_norm=float(tracking_cfg.get("target_y_norm", 0.5)),
            hold_zone_x=float(cfg.get("dead_zone_x", tracking_cfg.get("hold_zone_x", 0.020))),
            hold_zone_y=float(cfg.get("dead_zone_y", tracking_cfg.get("hold_zone_y", 0.025))),
            max_step_degrees=float(cfg.get("max_step_degrees", tracking_cfg.get("max_step_degrees", 1.4))),
            fast_offset_threshold=float(tracking_cfg.get("fast_offset_threshold", 0.045)),
            fast_gain_boost=float(tracking_cfg.get("fast_gain_boost", 1.35)),
            invert_tilt=bool(tracking_cfg.get("invert_tilt", False)),
        )

        scan_cfg = dict(cfg.get("scan", {}) or {})
        tilt_levels_raw = scan_cfg.get("tilt_levels_degrees", (0.0, 6.0, 10.0))
        if isinstance(tilt_levels_raw, str):
            tilt_levels_raw = [
                part.strip() for part in tilt_levels_raw.split(",") if part.strip()
            ]
        try:
            tilt_levels = tuple(float(v) for v in tilt_levels_raw)
        except (TypeError, ValueError):
            tilt_levels = (0.0, 6.0, 10.0)

        self._scanner = ScanPlanner(
            pan_limit_degrees=float(cfg.get("search_pan_limit_degrees", scan_cfg.get("pan_limit_degrees", 50.0))),
            pan_step_degrees=float(cfg.get("search_step_degrees", scan_cfg.get("pan_step_degrees", 6.0))),
            tilt_levels_degrees=tilt_levels,
        )

        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._lock = threading.RLock()
        self._status = LookAtMeStatus(enabled=self._enabled, fps_target=self._target_fps)
        self._status.config = {
            "target_fps": self._target_fps,
            "scan_after_no_face_frames": self._scan_after_no_face_frames,
            "return_to_center_on_stop": self._return_to_center_on_stop,
            "scan_pan_limit_degrees": self._scanner.pan_limit,
            "scan_pan_step_degrees": self._scanner.pan_step,
            "scan_tilt_levels_degrees": list(self._scanner.tilt_levels),
        }

        # Continuous follow runtime state.
        # The face detector can update faster than the physical pan-tilt can
        # move. Sending every tiny correction as an independent move_delta makes
        # the head look like: move, stop, move, stop. These fields smooth and
        # rate-limit the physical command stream.
        self._command_interval_seconds = max(
            0.015,
            float(cfg.get("command_interval_seconds", cfg.get("movement_interval_seconds", 0.04))),
        )
        self._min_move_degrees = max(0.0, float(cfg.get("min_move_degrees", 0.04)))
        self._runtime_max_step_degrees = max(
            0.05,
            float(cfg.get("max_runtime_step_degrees", cfg.get("max_step_degrees", tracking_cfg.get("max_step_degrees", 0.6)))),
        )
        self._follow_smoothing_alpha = min(
            1.0,
            max(0.05, float(cfg.get("smoothing_alpha", cfg.get("target_smoothing_alpha", 0.25)))),
        )
        self._last_motion_command_at = 0.0
        self._smoothed_pan_delta_degrees = 0.0
        self._smoothed_tilt_delta_degrees = 0.0

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_settings(
        cls,
        *,
        settings: dict[str, Any],
        vision_backend: Any,
        pan_tilt_backend: Any | None,
    ) -> "LookAtMeSession":
        """Build a session from the global settings dict."""
        return cls(
            vision_backend=vision_backend,
            pan_tilt_backend=pan_tilt_backend,
            config=dict(settings.get("look_at_me", {}) or {}),
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    def is_active(self) -> bool:
        with self._lock:
            return bool(self._status.active)

    def start(self, *, language: str = "en") -> dict[str, Any]:
        """Start the tracker. Non-blocking. Idempotent.

        Returns a small dict describing the start outcome — useful for the
        ActionFlow handler that drives the spoken acknowledgement.
        """
        if not self._enabled:
            LOGGER.info("LookAtMeSession start skipped: disabled by config.")
            return {"started": False, "reason": "disabled_by_config"}

        if self._vision_backend is None:
            LOGGER.warning("LookAtMeSession start skipped: vision backend missing.")
            return {"started": False, "reason": "vision_backend_missing"}

        with self._lock:
            if self._status.active and self._worker is not None and self._worker.is_alive():
                LOGGER.info("LookAtMeSession already active — start() is a no-op.")
                return {"started": False, "reason": "already_active"}

            self._stop_event.clear()
            self._scanner.reset()
            self._status.active = True
            self._status.started_at = time.monotonic()
            self._status.last_face_at = 0.0
            self._status.face_seen_count = 0
            self._status.no_face_streak = 0
            self._status.move_count = 0
            self._status.scan_count = 0
            self._status.last_reason = "starting"
            self._status.last_error = ""
            self._status.last_language = str(language or "")

            worker = threading.Thread(
                target=self._run,
                name="LookAtMeSessionWorker",
                daemon=True,
            )
            self._worker = worker
            worker.start()

        LOGGER.info("LookAtMeSession started: language=%s fps=%.1f", language, self._target_fps)
        return {"started": True, "reason": "started", "language": str(language or "")}

    def stop(self) -> dict[str, Any]:
        """Stop the tracker, optionally return pan/tilt to center."""
        with self._lock:
            was_active = bool(self._status.active)
            self._stop_event.set()
            worker = self._worker

        if worker is not None and worker.is_alive():
            worker.join(timeout=2.5)

        with self._lock:
            self._worker = None
            self._status.active = False
            if was_active:
                self._status.last_reason = "stopped_by_request"

        center_result: dict[str, Any] = {}
        if was_active and self._return_to_center_on_stop and self._pan_tilt_backend is not None:
            center_method = getattr(self._pan_tilt_backend, "center", None)
            if callable(center_method):
                try:
                    center_result = dict(center_method() or {})
                    LOGGER.info(
                        "LookAtMeSession centered pan/tilt on stop. ok=%s",
                        center_result.get("ok"),
                    )
                except Exception as error:  # pragma: no cover - hardware dependent
                    LOGGER.warning("LookAtMeSession center on stop failed safely: %s", error)
                    center_result = {"ok": False, "error": str(error)}

        LOGGER.info("LookAtMeSession stopped. was_active=%s", was_active)
        return {"stopped": was_active, "center_result": center_result}

    def close(self) -> None:
        """Final teardown. Safe to call multiple times."""
        try:
            self.stop()
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.warning("LookAtMeSession close encountered safe error: %s", error)
        self._vision_backend = None
        self._pan_tilt_backend = None

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status.to_dict()

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _run(self) -> None:
        period = 1.0 / self._target_fps
        last_scan_at = 0.0

        try:
            while not self._stop_event.is_set():
                tick_start = time.monotonic()

                # Hard runtime cap protects against runaway sessions if the
                # stop command never arrives (lost network, broken router).
                if (
                    self._max_runtime_seconds > 0.0
                    and (tick_start - self._status.started_at) > self._max_runtime_seconds
                ):
                    LOGGER.info(
                        "LookAtMeSession reached max_runtime_seconds=%.1f. Stopping.",
                        self._max_runtime_seconds,
                    )
                    with self._lock:
                        self._status.last_reason = "max_runtime_exceeded"
                    break

                try:
                    self._tick(now=tick_start, last_scan_at=last_scan_at)
                except Exception as error:  # pragma: no cover - defensive
                    LOGGER.warning(
                        "LookAtMeSession tick failed safely: %s",
                        error,
                    )
                    with self._lock:
                        self._status.last_error = f"{type(error).__name__}: {error}"

                # Refresh the scan-rate cursor from status (the tick may have
                # bumped scan_count and updated scan timing).
                with self._lock:
                    if self._status.scan_count > 0:
                        last_scan_at = tick_start

                spent = time.monotonic() - tick_start
                sleep_for = period - spent
                if sleep_for > 0:
                    # Use stop_event.wait for prompt cancellation.
                    if self._stop_event.wait(sleep_for):
                        break
        finally:
            with self._lock:
                self._status.active = False

    def _tick(self, *, now: float, last_scan_at: float) -> None:
        """One frame of work: read observation, decide, move."""
        observation = self._latest_observation()

        face_box = _extract_face_box(observation)
        if face_box is not None:
            self._handle_face_seen(face_box=face_box, now=now)
            return

        # No face this tick.
        with self._lock:
            self._status.no_face_streak += 1
            should_scan = (
                self._status.no_face_streak >= self._scan_after_no_face_frames
                and (now - last_scan_at) >= self._scan_interval_seconds
            )

        if should_scan:
            self._handle_scan_step(now=now)

    def _handle_face_seen(
        self,
        *,
        face_box: tuple[float, float],
        now: float,
    ) -> None:
        face_x_norm, face_y_norm = face_box
        command = self._tracker.plan(face_x_norm=face_x_norm, face_y_norm=face_y_norm)

        with self._lock:
            self._status.face_seen_count += 1
            self._status.no_face_streak = 0
            self._status.last_face_at = now

        if command.in_hold_zone:
            self._reset_motion_smoothing()
            with self._lock:
                self._status.last_reason = "tracking_hold"
            return

        result = self._move_delta(
            pan_delta_degrees=command.pan_delta_degrees,
            tilt_delta_degrees=command.tilt_delta_degrees,
            reason="tracking",
        )
        with self._lock:
            self._status.last_reason = "tracking"
            self._status.move_count += 1
            self._update_pan_tilt_from_result(result)

    def _handle_scan_step(self, *, now: float) -> None:
        target = self._scanner.next_target()

        with self._lock:
            current_pan = self._status.pan_angle
            current_tilt = self._status.tilt_angle

        pan_delta = target.target_pan_degrees - current_pan
        tilt_delta = target.target_tilt_degrees - current_tilt

        result = self._move_delta(
            pan_delta_degrees=pan_delta,
            tilt_delta_degrees=tilt_delta,
            reason=f"scan:{target.direction}",
        )

        with self._lock:
            self._status.last_reason = f"scan:{target.direction}"
            self._status.scan_count += 1
            self._update_pan_tilt_from_result(result)

    def _reset_motion_smoothing(self) -> None:
        self._smoothed_pan_delta_degrees = 0.0
        self._smoothed_tilt_delta_degrees = 0.0

    def _clamp_runtime_delta(self, value: float) -> float:
        limit = max(0.05, float(self._runtime_max_step_degrees))
        value = float(value)
        if value > limit:
            return limit
        if value < -limit:
            return -limit
        return value

    def _current_pan_tilt_angles(self) -> dict[str, float]:
        with self._lock:
            return {
                "pan_angle": float(self._status.pan_angle),
                "tilt_angle": float(self._status.tilt_angle),
            }

    def _move_delta(
        self,
        *,
        pan_delta_degrees: float,
        tilt_delta_degrees: float,
        reason: str,
    ) -> dict[str, Any]:
        backend = self._pan_tilt_backend
        if backend is None:
            return {"ok": False, "movement_executed": False, "error": "pan_tilt_backend_missing"}

        method = getattr(backend, "move_delta", None)
        if not callable(method):
            return {"ok": False, "movement_executed": False, "error": "move_delta_unavailable"}

        requested_pan = float(pan_delta_degrees)
        requested_tilt = float(tilt_delta_degrees)

        # Scan commands are intentionally discrete. Face-follow commands are
        # smoothed and rate-limited to reduce physical start/stop behaviour.
        if reason == "tracking":
            alpha = float(self._follow_smoothing_alpha)
            self._smoothed_pan_delta_degrees = (
                alpha * requested_pan + (1.0 - alpha) * self._smoothed_pan_delta_degrees
            )
            self._smoothed_tilt_delta_degrees = (
                alpha * requested_tilt + (1.0 - alpha) * self._smoothed_tilt_delta_degrees
            )

            pan_to_send = self._clamp_runtime_delta(self._smoothed_pan_delta_degrees)
            tilt_to_send = self._clamp_runtime_delta(self._smoothed_tilt_delta_degrees)

            min_delta = float(self._min_move_degrees)
            if abs(pan_to_send) < min_delta and abs(tilt_to_send) < min_delta:
                result = self._current_pan_tilt_angles()
                result.update(
                    {
                        "ok": True,
                        "movement_executed": False,
                        "movement_deferred": True,
                        "defer_reason": "below_min_move_degrees",
                        "requested_pan_delta_degrees": round(requested_pan, 4),
                        "requested_tilt_delta_degrees": round(requested_tilt, 4),
                        "smoothed_pan_delta_degrees": round(pan_to_send, 4),
                        "smoothed_tilt_delta_degrees": round(tilt_to_send, 4),
                    }
                )
                return result

            now = time.monotonic()
            elapsed = now - float(self._last_motion_command_at)
            if elapsed < float(self._command_interval_seconds):
                result = self._current_pan_tilt_angles()
                result.update(
                    {
                        "ok": True,
                        "movement_executed": False,
                        "movement_deferred": True,
                        "defer_reason": "command_interval",
                        "command_interval_seconds": round(float(self._command_interval_seconds), 4),
                        "elapsed_since_last_command_seconds": round(elapsed, 4),
                        "requested_pan_delta_degrees": round(requested_pan, 4),
                        "requested_tilt_delta_degrees": round(requested_tilt, 4),
                        "smoothed_pan_delta_degrees": round(pan_to_send, 4),
                        "smoothed_tilt_delta_degrees": round(tilt_to_send, 4),
                    }
                )
                return result

            self._last_motion_command_at = now
        else:
            pan_to_send = self._clamp_runtime_delta(requested_pan)
            tilt_to_send = self._clamp_runtime_delta(requested_tilt)

        try:
            result = dict(
                method(
                    pan_delta_degrees=float(pan_to_send),
                    tilt_delta_degrees=float(tilt_to_send),
                )
                or {}
            )
            result.setdefault("requested_pan_delta_degrees", round(requested_pan, 4))
            result.setdefault("requested_tilt_delta_degrees", round(requested_tilt, 4))
            result["continuous_follow_reason"] = reason
            result["smoothed_pan_delta_degrees"] = round(float(pan_to_send), 4)
            result["smoothed_tilt_delta_degrees"] = round(float(tilt_to_send), 4)
            return result
        except Exception as error:  # pragma: no cover - hardware dependent
            LOGGER.warning(
                "LookAtMeSession move_delta failed safely: reason=%s error=%s",
                reason,
                error,
            )
            return {"ok": False, "movement_executed": False, "error": f"{type(error).__name__}: {error}"}

    def _update_pan_tilt_from_result(self, result: dict[str, Any]) -> None:
        if not isinstance(result, dict):
            return
        pan = result.get("pan_angle")
        tilt = result.get("tilt_angle")
        if isinstance(pan, (int, float)):
            self._status.pan_angle = float(pan)
        if isinstance(tilt, (int, float)):
            self._status.tilt_angle = float(tilt)

    def _latest_observation(self) -> Any:
        method = getattr(self._vision_backend, "latest_observation", None)
        if not callable(method):
            return None
        try:
            # force_refresh=False — we want the LATEST cached frame from the
            # continuous capture worker, never block the tracker on I/O.
            return method(force_refresh=False)
        except TypeError:
            try:
                return method()
            except Exception as error:  # pragma: no cover - defensive
                LOGGER.debug("LookAtMeSession observation read failed: %s", error)
                return None
        except Exception as error:  # pragma: no cover - defensive
            LOGGER.debug("LookAtMeSession observation read failed: %s", error)
            return None


def _extract_face_box(observation: Any) -> tuple[float, float] | None:
    """Pull the highest-confidence face center from a VisionObservation.

    Returns (x_norm, y_norm) where each value is the face center expressed in
    [0, 1] frame coordinates, or None if no face is present in the snapshot.

    The shape we read here matches what `modules/devices/vision/fusion/
    snapshot_builder.py` produces:

        observation.metadata = {
            "diagnostics": {...},
            "frame_width": int,
            "frame_height": int,
            "perception": {
                "faces": [
                    {
                        "bounding_box": {"left": int, "top": int,
                                          "right": int, "bottom": int},
                        "confidence": float,
                        ...
                    },
                    ...
                ],
                ...
            },
        }
    """
    if observation is None:
        return None

    metadata = getattr(observation, "metadata", None)
    if not isinstance(metadata, dict):
        return None

    frame_width = int(metadata.get("frame_width", 0) or 0)
    frame_height = int(metadata.get("frame_height", 0) or 0)
    if frame_width <= 0 or frame_height <= 0:
        return None

    perception = metadata.get("perception")
    if not isinstance(perception, dict):
        return None

    faces = perception.get("faces") or []
    if not faces:
        return None

    # Pick the most confident face.
    best = None
    best_conf = -1.0
    for face in faces:
        if not isinstance(face, dict):
            continue
        try:
            conf = float(face.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf > best_conf:
            best = face
            best_conf = conf

    if best is None:
        return None

    box = best.get("bounding_box") or best.get("box") or {}
    if not isinstance(box, dict):
        return None

    try:
        left = float(box.get("left", 0))
        top = float(box.get("top", 0))
        right = float(box.get("right", 0))
        bottom = float(box.get("bottom", 0))
    except (TypeError, ValueError):
        return None

    if right <= left or bottom <= top:
        return None

    center_x = (left + right) / 2.0
    center_y = (top + bottom) / 2.0
    return (center_x / frame_width, center_y / frame_height)


__all__ = ["LookAtMeSession", "LookAtMeStatus"]
