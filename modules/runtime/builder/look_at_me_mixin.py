from __future__ import annotations

import copy
import threading
import time
from dataclasses import asdict, is_dataclass
from typing import Any

from modules.devices.pan_tilt import PanTiltService
from modules.devices.vision.tracking import VisionTrackingService
from modules.runtime.contracts import RuntimeBackendStatus
from modules.shared.logging.logger import get_logger


LOGGER = get_logger(__name__)


def _as_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if is_dataclass(value):
        return asdict(value)
    return {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


class LookAtMeSession:
    """Safe runtime look-at-me tracking loop.

    The default vision_tracking service remains dry-run. When explicitly enabled
    through the look_at_me runtime gates, this session creates a temporary
    hardware-capable pan-tilt backend and tracking service only for the active
    look-at-me command. This keeps global startup settings safe while allowing
    controlled face tracking movement.
    """

    def __init__(
        self,
        *,
        settings: dict[str, Any],
        vision_backend: Any,
        pan_tilt_backend: Any,
        vision_tracking_service: Any | None = None,
    ) -> None:
        self._settings = settings
        self._vision_backend = vision_backend
        self._pan_tilt_backend = pan_tilt_backend
        self._vision_tracking_service = vision_tracking_service
        self._config = dict(settings.get("look_at_me", {}) or {})
        self.enabled = bool(self._config.get("enabled", True))

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None

        self._started_at: float | None = None
        self._last_start_language = "en"
        self._last_error: str | None = None
        self._last_iteration: dict[str, Any] | None = None
        self._move_count = 0
        self._loop_count = 0
        self._paused_object_detection = False

        self._active_tracking_service: Any | None = None
        self._active_pan_tilt_backend: Any | None = None

    def start(self, *, language: str = "en") -> dict[str, Any]:
        with self._lock:
            if not self.enabled:
                return {
                    "started": False,
                    "already_running": False,
                    "enabled": False,
                    "reason": "look_at_me_disabled",
                }

            if self._vision_tracking_service is None:
                return {
                    "started": False,
                    "already_running": False,
                    "enabled": True,
                    "reason": "vision_tracking_service_unavailable",
                }

            if self._worker is not None and self._worker.is_alive():
                return {
                    "started": False,
                    "already_running": True,
                    "enabled": True,
                    "status": self.status(),
                }

            self._stop_event.clear()
            self._last_start_language = str(language or "en")
            self._last_error = None
            self._last_iteration = None
            self._move_count = 0
            self._loop_count = 0
            self._started_at = time.monotonic()

            self._activate_runtime_tracking_service()

            self._worker = threading.Thread(
                target=self._run_loop,
                name="nexa-look-at-me-session",
                daemon=True,
            )
            self._worker.start()

            return {
                "started": True,
                "already_running": False,
                "enabled": True,
                "mode": self._active_mode(),
                "runtime_pan_tilt_execution_enabled": self._runtime_pan_tilt_execution_enabled(),
            }

    def stop(self) -> dict[str, Any]:
        with self._lock:
            worker = self._worker
            was_running = bool(worker is not None and worker.is_alive())
            self._stop_event.set()

        if worker is not None and worker.is_alive():
            worker.join(timeout=self._stop_timeout_seconds())

        center_result: dict[str, Any] | None = None
        if bool(self._config.get("center_on_stop", False)):
            backend = self._active_pan_tilt_backend or self._pan_tilt_backend
            center = getattr(backend, "center", None)
            if callable(center):
                try:
                    center_result = dict(center() or {})
                except Exception as error:
                    center_result = {"ok": False, "error": f"{type(error).__name__}: {error}"}

        self._resume_object_detection_if_needed()
        self._close_active_runtime_backends()

        return {
            "stopped": was_running,
            "was_running": was_running,
            "center_requested": bool(self._config.get("center_on_stop", False)),
            "center_result": center_result,
            "status": self.status(),
        }

    def close(self) -> None:
        self.stop()

    def status(self) -> dict[str, Any]:
        with self._lock:
            worker = self._worker
            running = bool(worker is not None and worker.is_alive())
            active_service = self._tracking_service()
            active_status = {}
            status_method = getattr(active_service, "status", None)
            if callable(status_method):
                try:
                    active_status = dict(status_method() or {})
                except Exception as error:
                    active_status = {"error": f"{type(error).__name__}: {error}"}

            return {
                "enabled": self.enabled,
                "running": running,
                "started_at_monotonic": self._started_at,
                "last_start_language": self._last_start_language,
                "last_error": self._last_error,
                "last_iteration": dict(self._last_iteration or {}),
                "move_count": self._move_count,
                "loop_count": self._loop_count,
                "mode": self._active_mode(),
                "vision_tracking_attached": self._vision_tracking_service is not None,
                "pan_tilt_backend_attached": self._pan_tilt_backend is not None,
                "runtime_pan_tilt_execution_enabled": self._runtime_pan_tilt_execution_enabled(),
                "active_runtime_pan_tilt_backend": self._active_pan_tilt_backend is not None,
                "active_tracking_status": active_status,
            }

    def _run_loop(self) -> None:
        self._pause_object_detection_for_tracking()
        try:
            self._ensure_runtime_camera_started()
            deadline = self._session_deadline()
            interval = self._movement_interval_seconds()
            min_delta = self._min_move_degrees()

            while not self._stop_event.is_set():
                if deadline is not None and time.monotonic() >= deadline:
                    break

                iteration_started = time.monotonic()
                iteration = self._run_once(min_delta=min_delta)
                elapsed = time.monotonic() - iteration_started

                with self._lock:
                    self._loop_count += 1
                    self._last_iteration = iteration

                sleep_for = max(0.0, interval - elapsed)
                if self._stop_event.wait(timeout=sleep_for):
                    break

        except Exception as error:
            LOGGER.exception("Look-at-me tracking loop failed: %s", error)
            with self._lock:
                self._last_error = f"{type(error).__name__}: {error}"
        finally:
            self._resume_object_detection_if_needed()
            self._close_active_runtime_backends()

    def _run_once(self, *, min_delta: float) -> dict[str, Any]:
        service = self._tracking_service()
        if service is None:
            return {"ok": False, "reason": "vision_tracking_service_unavailable"}

        plan = service.plan_once(force_refresh=True)
        plan_payload = _as_mapping(plan)
        has_target = bool(plan_payload.get("has_target", False))

        execution_result = None
        latest_execution = getattr(service, "latest_execution_result", None)
        if callable(latest_execution):
            execution_result = _as_mapping(latest_execution())

        adapter_result = None
        latest_adapter = getattr(service, "latest_pan_tilt_adapter_result", None)
        if callable(latest_adapter):
            adapter_result = _as_mapping(latest_adapter())

        pan_delta = _safe_float(plan_payload.get("pan_delta_degrees", 0.0))
        tilt_delta = _safe_float(plan_payload.get("tilt_delta_degrees", 0.0))

        if not has_target:
            return {
                "ok": True,
                "reason": str(plan_payload.get("reason") or "no_target"),
                "has_target": False,
                "movement_executed": False,
                "plan": plan_payload,
                "execution_result": execution_result or {},
                "pan_tilt_adapter_result": adapter_result or {},
            }

        if abs(pan_delta) < min_delta and abs(tilt_delta) < min_delta:
            return {
                "ok": True,
                "reason": "below_min_move_degrees",
                "has_target": True,
                "movement_executed": False,
                "pan_delta_degrees": round(pan_delta, 4),
                "tilt_delta_degrees": round(tilt_delta, 4),
                "plan": plan_payload,
                "execution_result": execution_result or {},
                "pan_tilt_adapter_result": adapter_result or {},
            }

        backend_executed = bool((adapter_result or {}).get("backend_command_executed", False))
        if backend_executed:
            with self._lock:
                self._move_count += 1

        return {
            "ok": bool((adapter_result or {}).get("accepted", False)),
            "reason": str(
                (adapter_result or {}).get("status")
                or plan_payload.get("reason")
                or "tracking_step"
            ),
            "has_target": True,
            "movement_executed": backend_executed,
            "pan_delta_degrees": round(pan_delta, 4),
            "tilt_delta_degrees": round(tilt_delta, 4),
            "plan": plan_payload,
            "execution_result": execution_result or {},
            "pan_tilt_adapter_result": adapter_result or {},
        }

    def _tracking_service(self) -> Any | None:
        return self._active_tracking_service or self._vision_tracking_service

    def _active_mode(self) -> str:
        if self._active_tracking_service is not None:
            return "runtime_hardware_tracking_session"
        return "runtime_vision_tracking_loop"

    def _activate_runtime_tracking_service(self) -> None:
        self._close_active_runtime_backends()

        if not self._runtime_pan_tilt_execution_enabled():
            self._active_tracking_service = None
            self._active_pan_tilt_backend = None
            return

        pan_tilt_config = self._build_runtime_pan_tilt_config()
        tracking_config = self._build_runtime_tracking_config()

        self._active_pan_tilt_backend = PanTiltService(config=pan_tilt_config)
        self._active_tracking_service = VisionTrackingService(
            vision_backend=self._vision_backend,
            pan_tilt_backend=self._active_pan_tilt_backend,
            config=tracking_config,
        )

    def _close_active_runtime_backends(self) -> None:
        backend = self._active_pan_tilt_backend
        self._active_tracking_service = None
        self._active_pan_tilt_backend = None

        close = getattr(backend, "close", None)
        if callable(close):
            try:
                close()
            except Exception as error:
                LOGGER.debug("Failed to close look-at-me runtime pan-tilt backend: %s", error)

    def _runtime_pan_tilt_execution_enabled(self) -> bool:
        return bool(
            self._config.get("runtime_pan_tilt_execution_enabled", False)
            and self._config.get("runtime_hardware_execution_enabled", False)
            and self._config.get("physical_movement_confirmed", False)
        )

    def _build_runtime_pan_tilt_config(self) -> dict[str, Any]:
        base = copy.deepcopy(dict(self._settings.get("pan_tilt", {}) or {}))
        status = {}
        status_method = getattr(self._pan_tilt_backend, "status", None)
        if callable(status_method):
            try:
                status = dict(status_method() or {})
            except Exception:
                status = {}

        safe_limits = status.get("safe_limits")
        if isinstance(safe_limits, dict):
            base["safe_limits"] = dict(safe_limits)

        base.update(
            {
                "enabled": True,
                "backend": str(status.get("backend") or base.get("backend") or "waveshare_serial"),
                "hardware_enabled": True,
                "motion_enabled": True,
                "dry_run": False,
                "startup_policy": "no_motion",
                "calibration_required": True,
                "allow_uncalibrated_motion": False,
                "device": str(status.get("device") or base.get("device") or "/dev/serial0"),
                "baudrate": _safe_int(status.get("baudrate") or base.get("baudrate"), 115200),
                "timeout_seconds": _safe_float(
                    status.get("timeout_seconds") or base.get("timeout_seconds"),
                    0.2,
                ),
                "protocol": str(status.get("protocol") or base.get("protocol") or "waveshare_json_serial"),
                "calibration_state_path": str(
                    status.get("calibration_state_path")
                    or base.get("calibration_state_path")
                    or "var/data/pan_tilt_limit_calibration.json"
                ),
                "max_step_degrees": self._runtime_max_step_degrees(),
                "command_speed": self._runtime_command_speed(),
                "command_acceleration": self._runtime_command_acceleration(),
                "serial_warmup_seconds": _safe_float(
                    self._config.get("serial_warmup_seconds"),
                    _safe_float(base.get("serial_warmup_seconds"), 0.05),
                ),
                "read_after_write_seconds": _safe_float(
                    self._config.get("read_after_write_seconds"),
                    _safe_float(base.get("read_after_write_seconds"), 0.0),
                ),
                "command_mode": str(
                    self._config.get("command_mode")
                    or base.get("command_mode")
                    or "gimbal_move"
                ),
            }
        )
        return base

    def _build_runtime_tracking_config(self) -> dict[str, Any]:
        base = copy.deepcopy(dict(self._settings.get("vision_tracking", {}) or {}))
        base["enabled"] = True
        base["persist_status"] = True
        base["status_path"] = str(
            self._config.get("runtime_status_path", "var/data/look_at_me_tracking_status.json")
        )

        policy = copy.deepcopy(dict(base.get("policy", {}) or {}))
        policy.update(
            {
                "enabled": True,
                "dead_zone_x": _safe_float(self._config.get("dead_zone_x"), policy.get("dead_zone_x", 0.025)),
                "dead_zone_y": _safe_float(self._config.get("dead_zone_y"), policy.get("dead_zone_y", 0.035)),
                "pan_gain_degrees": _safe_float(
                    self._config.get("pan_gain_degrees"),
                    policy.get("pan_gain_degrees", 9.0),
                ),
                "tilt_gain_degrees": _safe_float(
                    self._config.get("tilt_gain_degrees"),
                    policy.get("tilt_gain_degrees", 7.0),
                ),
                "max_step_degrees": self._runtime_max_step_degrees(),
                "limit_margin_degrees": _safe_float(
                    self._config.get("limit_margin_degrees"),
                    policy.get("limit_margin_degrees", 1.0),
                ),
                "base_yaw_assist_edge_threshold": _safe_float(
                    self._config.get("base_yaw_assist_edge_threshold"),
                    policy.get("base_yaw_assist_edge_threshold", 0.42),
                ),
            }
        )
        base["policy"] = policy

        base["motion_executor"] = {
            "dry_run": True,
            "movement_execution_enabled": False,
            "pan_tilt_movement_execution_enabled": False,
            "base_yaw_assist_execution_enabled": False,
            "base_forward_backward_movement_enabled": False,
        }

        base["pan_tilt_adapter"] = {
            "dry_run": False,
            "backend_command_execution_enabled": True,
            "runtime_hardware_execution_enabled": True,
            "physical_movement_confirmed": True,
            "require_calibrated_limits": True,
            "require_no_motion_startup_policy": True,
            "max_allowed_pan_delta_degrees": self._runtime_max_step_degrees(),
            "max_allowed_tilt_delta_degrees": self._runtime_max_step_degrees(),
        }
        return base

    def _runtime_max_step_degrees(self) -> float:
        return max(
            0.05,
            min(
                0.5,
                _safe_float(
                    self._config.get("max_runtime_step_degrees"),
                    _safe_float(self._config.get("max_step_degrees"), 0.5),
                ),
            ),
        )

    def _runtime_command_speed(self) -> int:
        return max(1, min(60, _safe_int(self._config.get("command_speed"), 50)))

    def _runtime_command_acceleration(self) -> int:
        return max(1, min(60, _safe_int(self._config.get("command_acceleration"), 50)))

    def _ensure_runtime_camera_started(self) -> None:
        start = getattr(self._vision_backend, "start", None)
        if callable(start):
            start()

    def _pause_object_detection_for_tracking(self) -> None:
        if not bool(self._config.get("pause_object_detection_while_tracking", True)):
            return
        pause = getattr(self._vision_backend, "pause_object_detection", None)
        if not callable(pause):
            return
        try:
            self._paused_object_detection = bool(pause())
        except Exception as error:
            LOGGER.debug("Look-at-me object detection pause failed: %s", error)
            self._paused_object_detection = False

    def _resume_object_detection_if_needed(self) -> None:
        if not self._paused_object_detection:
            return
        resume = getattr(self._vision_backend, "resume_object_detection", None)
        if callable(resume):
            try:
                resume(None)
            except Exception as error:
                LOGGER.debug("Look-at-me object detection resume failed: %s", error)
        self._paused_object_detection = False

    def _movement_interval_seconds(self) -> float:
        value = self._config.get(
            "command_interval_seconds",
            self._config.get("movement_interval_seconds", 0.06),
        )
        return max(0.04, min(0.5, _safe_float(value, 0.06)))

    def _min_move_degrees(self) -> float:
        return max(0.0, min(1.0, _safe_float(self._config.get("min_move_degrees", 0.04), 0.04)))

    def _stop_timeout_seconds(self) -> float:
        return max(0.2, min(5.0, _safe_float(self._config.get("stop_timeout_seconds", 1.5), 1.5)))

    def _session_deadline(self) -> float | None:
        max_seconds = _safe_float(self._config.get("max_session_seconds", 0.0), 0.0)
        if max_seconds <= 0.0:
            return None
        return time.monotonic() + max(1.0, max_seconds)


class RuntimeBuilderLookAtMeMixin:
    def _build_look_at_me_session(
        self,
        *,
        vision_backend: Any,
        pan_tilt_backend: Any,
        vision_tracking_service: Any | None = None,
    ) -> tuple[LookAtMeSession | None, RuntimeBackendStatus]:
        config = dict(self.settings.get("look_at_me", {}) or {})

        if not bool(config.get("enabled", False)):
            return None, RuntimeBackendStatus(
                component="look_at_me",
                ok=True,
                selected_backend="disabled",
                detail="Look-at-me tracking session is disabled in settings.",
                metadata={"enabled": False},
            )

        if vision_tracking_service is None:
            return None, RuntimeBackendStatus(
                component="look_at_me",
                ok=False,
                selected_backend="unavailable",
                detail="Look-at-me requires the runtime VisionTrackingService.",
                fallback_used=True,
                metadata={"vision_tracking_attached": False},
            )

        session = LookAtMeSession(
            settings=self.settings,
            vision_backend=vision_backend,
            pan_tilt_backend=pan_tilt_backend,
            vision_tracking_service=vision_tracking_service,
        )

        return session, RuntimeBackendStatus(
            component="look_at_me",
            ok=True,
            selected_backend="runtime_vision_tracking_loop",
            detail="Look-at-me tracking session is ready and reuses the runtime camera owner.",
            capabilities=(
                "start",
                "stop",
                "smooth_face_tracking",
                "single_camera_owner",
                "temporary_runtime_pan_tilt_execution",
            ),
            metadata=session.status(),
        )


__all__ = ["LookAtMeSession", "RuntimeBuilderLookAtMeMixin"]
