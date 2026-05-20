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
        mobility_backend: Any | None = None,
    ) -> None:
        self._settings = settings
        self._vision_backend = vision_backend
        self._pan_tilt_backend = pan_tilt_backend
        self._vision_tracking_service = vision_tracking_service
        self._mobility_backend = mobility_backend
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

        self._last_target_seen_at: float | None = None
        self._last_search_step_at = 0.0
        self._search_direction = -1.0
        self._search_tilt_index = 0
        self._search_tilt_phase = "up"
        self._tracking_state = "idle"
        self._yaw_assist_active = False
        self._yaw_assist_direction: str | None = None
        self._last_yaw_assist_command_at = 0.0
        self._last_yaw_assist_error: str | None = None
        self._mobile_base_backend_started = False
        self._mobile_base_contact_ok = False
        self._last_mobile_base_command: dict[str, Any] | None = None
        self._last_mobile_base_error: str | None = None

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
            self._last_target_seen_at = None
            self._last_search_step_at = 0.0
            self._search_direction = -1.0
            self._search_tilt_index = 0
            self._search_tilt_phase = "up"
            self._search_virtual_pan_degrees = None
            self._search_virtual_tilt_degrees = None
            self._suspect_false_lock_started_at = None
            self._tracking_state = "scanning_for_face"
            self._yaw_assist_active = False
            self._yaw_assist_direction = None
            self._last_yaw_assist_command_at = 0.0
            self._last_yaw_assist_error = None
            self._mobile_base_backend_started = False
            self._mobile_base_contact_ok = False
            self._last_mobile_base_command = None
            self._last_mobile_base_error = None

            self._activate_runtime_tracking_service()
            self._ensure_mobile_base_backend_started()

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

        self._stop_yaw_assist(reason="stop")

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
        self._close_mobile_base_backend_if_started()

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
            search_status = self._search_status_snapshot()
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
                "search_status": search_status,
                "tracking_state": self._tracking_state,
                "mobile_base_yaw_assist_enabled": self._mobile_base_yaw_assist_enabled(),
                "mobile_base_yaw_assist_active": self._yaw_assist_active,
                "mobile_base_yaw_assist_direction": self._yaw_assist_direction,
                "mobile_base_backend_started": self._mobile_base_backend_started,
                "mobile_base_contact_ok": self._mobile_base_contact_ok,
                "mobile_base_yaw_assist_available": self._mobile_base_yaw_assist_available(),
                "last_mobile_base_command": dict(self._last_mobile_base_command or {}),
                "last_mobile_base_error": self._last_mobile_base_error,
                "last_yaw_assist_error": self._last_yaw_assist_error,
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

                self._write_runtime_iteration_status(
                    iteration=iteration,
                    elapsed_seconds=elapsed,
                )

                sleep_for = max(0.0, interval - elapsed)
                if self._stop_event.wait(timeout=sleep_for):
                    break

        except Exception as error:
            LOGGER.exception("Look-at-me tracking loop failed: %s", error)
            with self._lock:
                self._last_error = f"{type(error).__name__}: {error}"
        finally:
            self._stop_yaw_assist(reason="look_at_me_loop_exit")
            self._resume_object_detection_if_needed()
            self._close_active_runtime_backends()
            self._close_mobile_base_backend_if_started()

    def _run_once(self, *, min_delta: float) -> dict[str, Any]:
        service = self._tracking_service()
        if service is None:
            return {"ok": False, "reason": "vision_tracking_service_unavailable"}

        plan = service.plan_once(force_refresh=self._force_refresh_during_tracking())
        plan_payload = _as_mapping(plan)
        has_target = bool(plan_payload.get("has_target", False))

        if has_target and self._should_ignore_suspect_target(plan_payload):
            plan_payload = dict(plan_payload)
            diagnostics = dict(plan_payload.get("diagnostics") or {})
            diagnostics["target_lock_override"] = "ignored_suspect_upper_tilt_false_lock"
            plan_payload["diagnostics"] = diagnostics
            plan_payload["has_target"] = False
            plan_payload["reason"] = "suspect_upper_tilt_false_face_lock"
            has_target = False

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
            last_seen = self._last_target_seen_at
            if last_seen is not None:
                age = time.monotonic() - last_seen
                grace = _safe_float(self._config.get("target_lost_grace_seconds", 0.8), 0.8)
                if age < grace:
                    self._mark_tracking_state("target_grace_period")
                    return {
                        "ok": True,
                        "reason": "target_grace_period",
                        "has_target": False,
                        "movement_executed": False,
                        "short_dropout_grace_active": True,
                        "last_face_seen_age_ms": round(age * 1000, 1),
                        "search_active": False,
                        "plan": plan_payload,
                    }

            self._mark_tracking_state("lost_face_reacquire")
            self._stop_yaw_assist(reason="face_lost")
            search_result = self._maybe_run_search_step(
                reason=str(plan_payload.get("reason") or "no_target"),
                plan_payload=plan_payload,
                execution_result=execution_result or {},
                adapter_result=adapter_result or {},
            )
            if search_result is not None:
                return search_result
            return {
                "ok": True,
                "reason": str(plan_payload.get("reason") or "no_target"),
                "has_target": False,
                "movement_executed": False,
                "short_dropout_grace_active": False,
                "plan": plan_payload,
                "execution_result": execution_result or {},
                "pan_tilt_adapter_result": adapter_result or {},
            }

        self._remember_target_seen()
        self._mark_tracking_state("tracking_face")

        if abs(pan_delta) < min_delta and abs(tilt_delta) < min_delta:
            # Pan/tilt is already close enough — no servo step needed.
            # Still apply yaw assist from the plan: at high pan angles the policy
            # will request yaw even when the face is centered (pan_delta ~ 0),
            # so stopping yaw here would immediately cancel a required base rotation.
            yaw_assist = self._apply_yaw_assist_from_plan(plan_payload)
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
                "yaw_assist": yaw_assist,
            }

        backend_executed = bool((adapter_result or {}).get("backend_command_executed", False))
        if backend_executed:
            with self._lock:
                self._move_count += 1

        yaw_assist = self._apply_yaw_assist_from_plan(plan_payload)
        diagnostics = plan_payload.get("diagnostics") if isinstance(plan_payload.get("diagnostics"), dict) else {}

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
            "yaw_assist": yaw_assist,
            "smoothed_error_x": diagnostics.get("offset_x"),
            "smoothed_error_y": diagnostics.get("offset_y"),
            "pan_command_degrees": round(pan_delta, 4),
            "tilt_command_degrees": round(tilt_delta, 4),
            "tilt_clamped_to_center": bool(diagnostics.get("tilt_clamped_to_center", False)),
            "tilt_blocked_by_no_down_rule": bool(diagnostics.get("tilt_blocked_by_no_down_rule", False)),
            "stop_start_pattern_detected": False,
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
                "max_step_degrees": max(self._runtime_max_step_degrees(), self._runtime_search_step_degrees()),
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
            self._config.get(
                "runtime_tracking_plan_status_path",
                "var/data/look_at_me_tracking_plan_status.json",
            )
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
                "yaw_assist_pan_usage_start": _safe_float(
                    self._config.get("yaw_assist_pan_usage_start"),
                    policy.get("yaw_assist_pan_usage_start", 0.50),
                ),
                "yaw_assist_pan_usage_stop": _safe_float(
                    self._config.get("yaw_assist_pan_usage_stop"),
                    policy.get("yaw_assist_pan_usage_stop", 0.35),
                ),
                "no_tilt_below_center": bool(
                    self._config.get(
                        "no_tilt_below_center",
                        policy.get("no_tilt_below_center", True),
                    )
                ),
                "min_target_confidence": _safe_float(
                    self._config.get("min_target_confidence"),
                    policy.get("min_target_confidence", 0.66),
                ),
                "min_face_area_norm": _safe_float(
                    self._config.get("min_face_area_norm"),
                    policy.get("min_face_area_norm", 0.003),
                ),
                "min_person_area_norm": _safe_float(
                    self._config.get("min_person_area_norm"),
                    policy.get("min_person_area_norm", 0.025),
                ),
                "target_activation_hits": _safe_int(
                    self._config.get("target_activation_hits"),
                    _safe_int(policy.get("target_activation_hits"), 2),
                ),
                "target_smoothing_alpha": _safe_float(
                    self._config.get("smoothing_alpha"),
                    policy.get("target_smoothing_alpha", 0.72),
                ),
                "max_target_jump_norm": _safe_float(
                    self._config.get("max_target_jump_norm"),
                    policy.get("max_target_jump_norm", 0.32),
                ),
            }
        )
        base["policy"] = policy
        base["prefer_face_only_observation"] = bool(
            self._config.get("prefer_face_only_observation", True)
        )

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
            "smooth_follow_enabled": bool(self._config.get("smooth_tracking_enabled", True)),
            "smooth_follow_alpha": _safe_float(
                self._config.get("tracking_smoothing_alpha"),
                _safe_float(self._config.get("smoothing_alpha"), 0.62),
            ),
            "smooth_follow_lead_gain": _safe_float(
                self._config.get("smooth_follow_lead_gain"),
                2.0,
            ),
            "smooth_follow_min_live_step_degrees": _safe_float(
                self._config.get("smooth_follow_min_live_step_degrees"),
                0.28,
            ),
            "smooth_follow_command_interval_seconds": _safe_float(
                self._config.get("smooth_follow_command_interval_seconds"),
                0.016,
            ),
        }
        return base

    def _runtime_max_step_degrees(self) -> float:
        return max(
            0.05,
            min(
                3.0,
                _safe_float(
                    self._config.get("max_runtime_step_degrees"),
                    _safe_float(self._config.get("max_step_degrees"), 2.8),
                ),
            ),
        )

    def _runtime_command_speed(self) -> int:
        return max(1, min(260, _safe_int(self._config.get("command_speed"), 230)))

    def _runtime_command_acceleration(self) -> int:
        return max(1, min(260, _safe_int(self._config.get("command_acceleration"), 220)))

    def _runtime_search_step_degrees(self) -> float:
        configured = _safe_float(self._config.get("search_step_degrees"), 30.0)
        return max(0.25, min(30.0, configured))

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

    def _remember_target_seen(self) -> None:
        with self._lock:
            self._last_target_seen_at = time.monotonic()
            self._last_search_step_at = 0.0
            self._search_direction = -1.0
            self._search_tilt_index = 0

    def _mark_tracking_state(self, state: str) -> None:
        with self._lock:
            self._tracking_state = state

    def _maybe_run_search_step(
        self,
        *,
        reason: str,
        plan_payload: dict[str, Any],
        execution_result: dict[str, Any],
        adapter_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not bool(self._config.get("search_when_no_face", True)):
            return None

        self._stop_yaw_assist(reason="searching_for_face")
        self._mark_tracking_state("scanning_for_face")

        now = time.monotonic()
        with self._lock:
            started_at = self._started_at or now
            last_seen_at = self._last_target_seen_at or started_at
            last_search_at = self._last_search_step_at

        lost_seconds = now - last_seen_at
        if lost_seconds < self._search_after_no_face_seconds():
            return None
        if (now - last_search_at) < self._search_interval_seconds():
            return None

        backend = self._active_pan_tilt_backend or self._pan_tilt_backend
        move_delta = getattr(backend, "move_delta", None)
        if not callable(move_delta):
            return {
                "ok": False,
                "reason": "search_backend_move_delta_unavailable",
                "has_target": False,
                "movement_executed": False,
                "search_active": True,
                "lost_seconds": round(lost_seconds, 3),
                "plan": plan_payload,
                "execution_result": execution_result,
                "pan_tilt_adapter_result": adapter_result,
            }

        search = self._next_search_delta(backend=backend)
        if not bool(search.get("would_move", False)):
            with self._lock:
                self._last_search_step_at = now
            return {
                "ok": True,
                "reason": search.get("reason", reason),
                "has_target": False,
                "movement_executed": False,
                "search_active": True,
                "lost_seconds": round(lost_seconds, 3),
                "search": search,
                "plan": plan_payload,
                "execution_result": execution_result,
                "pan_tilt_adapter_result": adapter_result,
            }

        try:
            response = dict(
                move_delta(
                    pan_delta_degrees=float(search["pan_delta_degrees"]),
                    tilt_delta_degrees=float(search["tilt_delta_degrees"]),
                )
                or {}
            )
        except Exception as error:
            response = {"ok": False, "error": f"{type(error).__name__}: {error}"}

        executed = bool(response.get("movement_executed", response.get("ok", False)))
        if executed:
            self._update_search_virtual_state(search=search, backend_response=response)

        with self._lock:
            self._last_search_step_at = now
            if executed:
                self._move_count += 1

        return {
            "ok": bool(response.get("ok", False)),
            "reason": "search_face_upper_tilt_pan_sweep",
            "has_target": False,
            "movement_executed": executed,
            "search_active": True,
            "lost_seconds": round(lost_seconds, 3),
            "search": search,
            "backend_response": response,
            "plan": plan_payload,
            "execution_result": execution_result,
            "pan_tilt_adapter_result": adapter_result,
        }

    def _should_ignore_suspect_target(self, plan_payload: dict[str, Any]) -> bool:
        """Ignore likely false Haar locks at the upper tilt limit so search can continue."""
        if not bool(self._config.get("ignore_suspect_upper_tilt_false_lock_enabled", True)):
            with self._lock:
                self._suspect_false_lock_started_at = None
            return False

        target = plan_payload.get("target") if isinstance(plan_payload.get("target"), dict) else {}
        metadata = target.get("metadata") if isinstance(target.get("metadata"), dict) else {}
        diagnostics = plan_payload.get("diagnostics") if isinstance(plan_payload.get("diagnostics"), dict) else {}

        detector = str(metadata.get("detector") or "")
        reason = str(plan_payload.get("reason") or "")
        target_lock = str(diagnostics.get("target_lock") or "")
        tilt_at_limit = bool(plan_payload.get("tilt_at_limit", False))

        pan_delta = abs(_safe_float(plan_payload.get("pan_delta_degrees"), 0.0))
        tilt_delta = abs(_safe_float(plan_payload.get("tilt_delta_degrees"), 0.0))
        clamped_tilt = _safe_float(plan_payload.get("clamped_tilt_degrees"), 0.0)
        desired_tilt = _safe_float(plan_payload.get("desired_tilt_degrees"), clamped_tilt)

        upper_limit_degrees = _safe_float(
            self._config.get("suspect_false_lock_upper_tilt_degrees"),
            70.0,
        )
        grace_seconds = max(
            0.0,
            _safe_float(
                self._config.get("suspect_false_lock_grace_seconds"),
                0.35,
            ),
        )

        suspect = (
            detector == "opencv_haar"
            and tilt_at_limit
            and max(clamped_tilt, desired_tilt) >= upper_limit_degrees
            and reason in {"target_centered", "recenter_target"}
            and target_lock in {"locked", "activated", ""}
            and pan_delta <= 0.05
            and tilt_delta <= 0.05
        )

        now = time.monotonic()
        with self._lock:
            if not suspect:
                self._suspect_false_lock_started_at = None
                return False

            if self._suspect_false_lock_started_at is None:
                self._suspect_false_lock_started_at = now
                return False

            return (now - self._suspect_false_lock_started_at) >= grace_seconds

    def _write_runtime_iteration_status(
        self,
        *,
        iteration: dict[str, Any],
        elapsed_seconds: float,
    ) -> None:
        """Persist the real LookAtMeSession iteration status safely."""
        try:
            import json as _json
            from pathlib import Path as _Path

            status_path = _Path(
                str(
                    self._config.get(
                        "runtime_status_path",
                        "var/data/look_at_me_tracking_status.json",
                    )
                )
            )

            payload = self.status()
            payload.update(
                {
                    "event": "look_at_me_runtime_iteration",
                    "runtime_status_source": "LookAtMeSession",
                    "last_iteration": iteration,
                    "iteration_elapsed_ms": round(float(elapsed_seconds) * 1000.0, 4),
                    "tracking_plan_status_path": str(
                        self._config.get(
                            "runtime_tracking_plan_status_path",
                            "var/data/look_at_me_tracking_plan_status.json",
                        )
                    ),
                }
            )

            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(
                _json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as error:
            LOGGER.warning("Failed to persist look-at-me runtime status: %s", error)

    def _update_search_virtual_state(
        self,
        *,
        search: dict[str, Any],
        backend_response: dict[str, Any],
    ) -> None:
        """Advance search state even when hardware telemetry is unavailable."""
        target_pan = _safe_float(
            backend_response.get("pan_angle"),
            _safe_float(search.get("target_pan_degrees"), 0.0),
        )
        target_tilt = _safe_float(
            backend_response.get("tilt_angle"),
            _safe_float(search.get("target_tilt_degrees"), 0.0),
        )

        with self._lock:
            self._search_virtual_pan_degrees = target_pan
            self._search_virtual_tilt_degrees = target_tilt

    def _safe_backend_status(self, backend: Any) -> dict[str, Any]:
        """Read pan-tilt backend status without breaking the tracking loop."""
        status_method = getattr(backend, "status", None)
        if not callable(status_method):
            return {}

        try:
            status = status_method()
        except Exception as error:
            return {
                "status_error": f"{error.__class__.__name__}: {error}",
            }

        if isinstance(status, dict):
            return status
        return {}

    def _next_search_delta(self, *, backend: Any) -> dict[str, Any]:
        """Return the next full-edge wave-sweep search movement.

        Search behavior:
        - move pan/X until the calibrated left/right edge is reached,
        - only then change tilt/Y by one row,
        - then sweep the full pan/X range in the opposite direction,
        - climb upward until the top row,
        - then descend row-by-row back to center,
        - never search below tilt center.
        """
        status = self._safe_backend_status(backend)
        safe_limits = status.get("safe_limits") if isinstance(status.get("safe_limits"), dict) else {}

        pan_min = _safe_float(safe_limits.get("pan_min_degrees"), -89.0)
        pan_max = _safe_float(safe_limits.get("pan_max_degrees"), 89.0)
        pan_center = _safe_float(safe_limits.get("pan_center_degrees"), 0.0)
        tilt_center = _safe_float(safe_limits.get("tilt_center_degrees"), 0.0)
        tilt_max = _safe_float(safe_limits.get("tilt_max_degrees"), 79.0)

        status_pan = max(pan_min, min(pan_max, _safe_float(status.get("pan_angle"), pan_center)))
        status_tilt = _safe_float(status.get("tilt_angle"), tilt_center)

        with self._lock:
            if getattr(self, "_search_virtual_pan_degrees", None) is None:
                self._search_virtual_pan_degrees = status_pan
            if getattr(self, "_search_virtual_tilt_degrees", None) is None:
                self._search_virtual_tilt_degrees = max(tilt_center, status_tilt)

            current_pan = max(pan_min, min(pan_max, float(self._search_virtual_pan_degrees)))
            current_tilt = max(tilt_center, min(tilt_max, float(self._search_virtual_tilt_degrees)))

        step = self._search_step_degrees()
        edge_epsilon = max(1.0, step * 0.20)

        with self._lock:
            direction = self._search_direction
            tilt_index_before = self._search_tilt_index
            tilt_phase_before = self._search_tilt_phase

        target_edge = pan_min if direction < 0.0 else pan_max
        distance_to_edge = target_edge - current_pan
        reached_edge = abs(distance_to_edge) <= edge_epsilon

        row_changed = False

        if reached_edge:
            # At the edge: change row first, then reverse direction.
            self._advance_search_tilt_level()

            with self._lock:
                self._search_direction = 1.0 if direction < 0.0 else -1.0
                direction = self._search_direction
                tilt_index_after = self._search_tilt_index
                tilt_phase_after = self._search_tilt_phase

            target_tilt = self._current_upper_search_tilt(
                tilt_center=tilt_center,
                tilt_max=tilt_max,
            )

            tilt_error = target_tilt - current_tilt
            if abs(tilt_error) <= 0.35:
                tilt_delta = 0.0
            else:
                tilt_delta = min(step, abs(tilt_error))
                if tilt_error < 0.0:
                    tilt_delta = -tilt_delta

            # Hard rule: never search below center.
            if current_tilt + tilt_delta < tilt_center:
                tilt_delta = max(0.0, tilt_center - current_tilt)

            return {
                "would_move": abs(tilt_delta) > 1e-6,
                "pan_delta_degrees": 0.0,
                "tilt_delta_degrees": round(tilt_delta, 4),
                "direction": "right" if direction > 0.0 else "left",
                "row_changed": True,
                "search_pattern": "full_edge_wave_sweep_x_first_upper_only",
                "search_tilt_index": tilt_index_after,
                "search_tilt_phase": tilt_phase_after,
                "previous_search_tilt_index": tilt_index_before,
                "previous_search_tilt_phase": tilt_phase_before,
                "current_pan_degrees": round(current_pan, 4),
                "current_tilt_degrees": round(current_tilt, 4),
                "target_pan_degrees": round(current_pan, 4),
                "target_tilt_degrees": round(target_tilt, 4),
                "pan_lower_degrees": round(pan_min, 4),
                "pan_upper_degrees": round(pan_max, 4),
                "tilt_center_degrees": round(tilt_center, 4),
                "tilt_upper_degrees": round(tilt_max, 4),
                "tilt_upper_only": True,
            }

        # Not at edge yet: move only in X toward the active edge.
        pan_delta_abs = min(step, abs(distance_to_edge))
        pan_delta = pan_delta_abs if distance_to_edge > 0.0 else -pan_delta_abs

        target_pan = current_pan + pan_delta

        with self._lock:
            tilt_index = self._search_tilt_index
            tilt_phase = self._search_tilt_phase

        return {
            "would_move": abs(pan_delta) > 1e-6,
            "pan_delta_degrees": round(pan_delta, 4),
            "tilt_delta_degrees": 0.0,
            "direction": "right" if direction > 0.0 else "left",
            "row_changed": row_changed,
            "search_pattern": "full_edge_wave_sweep_x_first_upper_only",
            "search_tilt_index": tilt_index,
            "search_tilt_phase": tilt_phase,
            "current_pan_degrees": round(current_pan, 4),
            "current_tilt_degrees": round(current_tilt, 4),
            "target_pan_degrees": round(target_pan, 4),
            "target_tilt_degrees": round(
                self._current_upper_search_tilt(tilt_center=tilt_center, tilt_max=tilt_max),
                4,
            ),
            "pan_lower_degrees": round(pan_min, 4),
            "pan_upper_degrees": round(pan_max, 4),
            "tilt_center_degrees": round(tilt_center, 4),
            "tilt_upper_degrees": round(tilt_max, 4),
            "tilt_upper_only": True,
        }

    def _advance_search_tilt_level(self) -> None:
        levels = self._search_tilt_levels()
        if len(levels) <= 1:
            return

        with self._lock:
            if self._search_tilt_phase == "up":
                if self._search_tilt_index < len(levels) - 1:
                    self._search_tilt_index += 1
                else:
                    self._search_tilt_phase = "down"
                    self._search_tilt_index = max(0, self._search_tilt_index - 1)
            else:
                if self._search_tilt_index > 0:
                    self._search_tilt_index -= 1
                else:
                    self._search_tilt_phase = "up"
                    self._search_tilt_index = min(1, len(levels) - 1)

    def _current_upper_search_tilt(self, *, tilt_center: float, tilt_max: float) -> float:
        levels = self._search_tilt_levels()
        if not levels:
            return max(tilt_center, min(tilt_max, tilt_center))
        with self._lock:
            index = min(self._search_tilt_index, len(levels) - 1)
        target = tilt_center + levels[index]
        return max(tilt_center, min(tilt_max - self._tilt_soft_limit_zone_degrees(), target))

    def _search_tilt_levels(self) -> list[float]:
        raw = self._config.get(
            "search_tilt_levels_degrees",
            [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 79.0],
        )
        if isinstance(raw, str):
            raw_values = [part.strip() for part in raw.split(",") if part.strip()]
        elif isinstance(raw, (list, tuple)):
            raw_values = list(raw)
        else:
            raw_values = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 79.0]

        values: list[float] = []
        for item in raw_values:
            value = max(0.0, _safe_float(item, 0.0))
            if value not in values:
                values.append(value)

        values = sorted(values)
        if not values or values[0] != 0.0:
            values.insert(0, 0.0)
        return values

    def _search_status_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "last_target_seen_at_monotonic": self._last_target_seen_at,
                "last_search_step_at_monotonic": self._last_search_step_at,
                "search_direction": "right" if self._search_direction > 0.0 else "left",
                "search_tilt_index": self._search_tilt_index,
                "search_tilt_phase": self._search_tilt_phase,
                "search_when_no_face": bool(self._config.get("search_when_no_face", True)),
                "search_after_no_face_seconds": self._search_after_no_face_seconds(),
                "search_interval_seconds": self._search_interval_seconds(),
                "search_tilt_levels_degrees": self._search_tilt_levels(),
            }

    def _search_after_no_face_seconds(self) -> float:
        return max(0.05, min(10.0, _safe_float(self._config.get("search_after_no_face_seconds"), 0.12)))

    def _search_interval_seconds(self) -> float:
        return max(0.07, min(2.0, _safe_float(self._config.get("search_interval_seconds"), 0.10)))

    def _search_step_degrees(self) -> float:
        return self._runtime_search_step_degrees()

    def _pan_soft_limit_zone_degrees(self) -> float:
        return max(0.0, min(15.0, _safe_float(self._config.get("pan_soft_limit_zone_degrees"), 2.0)))

    def _tilt_soft_limit_zone_degrees(self) -> float:
        return max(0.0, min(15.0, _safe_float(self._config.get("tilt_soft_limit_zone_degrees"), 1.0)))

    def _movement_interval_seconds(self) -> float:
        value = self._config.get(
            "command_interval_seconds",
            self._config.get("movement_interval_seconds", 0.040),
        )
        return max(0.020, min(0.5, _safe_float(value, 0.040)))

    def _force_refresh_during_tracking(self) -> bool:
        return bool(self._config.get("force_refresh_during_tracking", False))

    def _min_move_degrees(self) -> float:
        return max(0.0, min(1.0, _safe_float(self._config.get("min_move_degrees", 0.04), 0.04)))

    def _stop_timeout_seconds(self) -> float:
        return max(0.2, min(5.0, _safe_float(self._config.get("stop_timeout_seconds", 1.5), 1.5)))

    def _session_deadline(self) -> float | None:
        max_seconds = _safe_float(self._config.get("max_session_seconds", 0.0), 0.0)
        if max_seconds <= 0.0:
            return None
        return time.monotonic() + max(1.0, max_seconds)

    def _mobile_base_yaw_assist_enabled(self) -> bool:
        return bool(self._config.get("mobile_base_yaw_assist_enabled", False))

    def _mobile_base_yaw_assist_available(self) -> bool:
        backend = self._mobility_backend
        return bool(
            self._mobile_base_yaw_assist_enabled()
            and self._mobile_base_contact_ok
            and callable(getattr(backend, "send_velocity", None))
        )

    def _mobile_base_contact_required_for_yaw(self) -> bool:
        return bool(self._config.get("mobile_base_contact_required_for_yaw", True))

    def _mobile_base_yaw_speed(self) -> float:
        configured = _safe_float(self._config.get("mobile_base_yaw_speed"), 0.12)
        return max(0.02, min(0.35, configured))

    def _mobile_base_yaw_assist_interval_seconds(self) -> float:
        configured = _safe_float(self._config.get("mobile_base_yaw_assist_interval_seconds"), 0.2)
        return max(0.05, min(1.0, configured))

    def _apply_yaw_assist_from_plan(self, plan_payload: dict[str, Any]) -> dict[str, Any]:
        yaw_required = bool(plan_payload.get("base_yaw_assist_required", False))
        diagnostics = dict(plan_payload.get("diagnostics") or {})
        pan_usage = _safe_float(diagnostics.get("pan_usage", 0.0), 0.0)
        stop_threshold = _safe_float(
            self._config.get("yaw_assist_pan_usage_stop", 0.35), 0.35
        )

        with self._lock:
            yaw_was_active = self._yaw_assist_active
            last_direction = self._yaw_assist_direction

        if not yaw_required:
            if not yaw_was_active:
                return {"requested": False, "executed": False, "reason": "not_required"}
            # Yaw was active: hold if still above stop threshold (hysteresis zone)
            if pan_usage < stop_threshold:
                self._stop_yaw_assist(reason="pan_usage_below_stop_threshold")
                return {
                    "requested": False,
                    "executed": False,
                    "reason": "pan_usage_below_stop_threshold",
                    "pan_usage": round(pan_usage, 4),
                }
            # Still in hysteresis zone — maintain previous direction
            if last_direction not in {"left", "right"}:
                self._stop_yaw_assist(reason="direction_unavailable_in_hysteresis")
                return {"requested": True, "executed": False, "reason": "hysteresis_no_direction"}
            return self._send_yaw_assist(direction=last_direction)

        direction = str(plan_payload.get("base_yaw_direction") or "").strip().lower()
        if direction not in {"left", "right"}:
            self._stop_yaw_assist(reason="invalid_yaw_direction")
            return {"requested": True, "executed": False, "reason": "invalid_direction"}

        return self._send_yaw_assist(direction=direction)

    def _send_yaw_assist(self, *, direction: str) -> dict[str, Any]:
        if not self._mobile_base_yaw_assist_enabled():
            return {"requested": True, "executed": False, "reason": "disabled_by_config"}

        self._ensure_mobile_base_backend_started()

        if self._mobile_base_contact_required_for_yaw() and not self._mobile_base_contact_ok:
            return {"requested": True, "executed": False, "reason": "mobile_base_contact_unavailable"}

        backend = self._mobility_backend
        if backend is None:
            return {"requested": True, "executed": False, "reason": "mobility_backend_unavailable"}

        send_velocity = getattr(backend, "send_velocity", None)
        if not callable(send_velocity):
            self._last_yaw_assist_error = "mobility_backend_send_velocity_unavailable"
            return {"requested": True, "executed": False, "reason": "send_velocity_unavailable"}

        now = time.monotonic()
        with self._lock:
            recently_sent_same_direction = (
                self._yaw_assist_active
                and self._yaw_assist_direction == direction
                and (now - self._last_yaw_assist_command_at)
                < self._mobile_base_yaw_assist_interval_seconds()
            )
        if recently_sent_same_direction:
            return {"requested": True, "executed": False, "reason": "rate_limited"}

        angular = self._mobile_base_yaw_speed()
        if direction == "right":
            angular = -angular

        try:
            raw_response = send_velocity(linear_x_mps=0.0, angular_z_rad_s=angular)
            # MobileBaseController.send_velocity returns str (the serialised JSON line);
            # test stubs and other backends may return dict — handle both.
            if isinstance(raw_response, dict):
                response: dict[str, Any] = raw_response
            elif raw_response is not None:
                response = {"sent_line": str(raw_response), "ok": True}
            else:
                response = {}
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            with self._lock:
                self._last_yaw_assist_error = message
                self._last_mobile_base_error = message
                self._yaw_assist_active = False
                self._yaw_assist_direction = None
            LOGGER.warning("Look-at-me mobile-base yaw assist was blocked: %s", message)
            return {
                "requested": True,
                "executed": False,
                "reason": "send_velocity_failed",
                "error": message,
            }

        ok = bool(response.get("ok", True))
        with self._lock:
            self._yaw_assist_active = ok
            self._yaw_assist_direction = direction if ok else None
            self._last_yaw_assist_command_at = now
            self._last_yaw_assist_error = None if ok else str(response.get("error") or "not_ok")
            self._last_mobile_base_command = {
                "linear_x_mps": 0.0,
                "angular_z_rad_s": round(float(angular), 4),
                "direction": direction,
            }
            self._last_mobile_base_error = None if ok else str(response.get("error") or "not_ok")

        return {
            "requested": True,
            "executed": ok,
            "reason": "yaw_assist_active" if ok else "yaw_assist_rejected",
            "direction": direction,
            "linear_x_mps": 0.0,
            "angular_z_rad_s": round(float(angular), 4),
            "backend_response": response,
        }

    def _stop_yaw_assist(self, *, reason: str) -> dict[str, Any]:
        with self._lock:
            was_active = self._yaw_assist_active
            self._yaw_assist_active = False
            self._yaw_assist_direction = None

        if not was_active:
            return {"stopped": False, "reason": reason}

        backend = self._mobility_backend
        if backend is None:
            return {"stopped": False, "reason": "mobility_backend_unavailable"}

        stop = getattr(backend, "stop", None)
        if callable(stop):
            try:
                response = stop(reason=f"look_at_me_{reason}")
            except TypeError:
                response = stop()
            except Exception as error:
                message = f"{type(error).__name__}: {error}"
                with self._lock:
                    self._last_yaw_assist_error = message
                    self._last_mobile_base_error = message
                LOGGER.warning("Failed to stop look-at-me mobile-base yaw assist: %s", message)
                return {"stopped": False, "reason": "stop_failed", "error": message}
            return {"stopped": True, "reason": reason, "backend_response": _as_mapping(response)}

        send_velocity = getattr(backend, "send_velocity", None)
        if callable(send_velocity):
            try:
                response = send_velocity(linear_x_mps=0.0, angular_z_rad_s=0.0)
            except Exception as error:
                message = f"{type(error).__name__}: {error}"
                with self._lock:
                    self._last_yaw_assist_error = message
                    self._last_mobile_base_error = message
                LOGGER.warning("Failed to zero look-at-me mobile-base yaw assist: %s", message)
                return {"stopped": False, "reason": "zero_velocity_failed", "error": message}
            return {"stopped": True, "reason": reason, "backend_response": _as_mapping(response)}

        return {"stopped": False, "reason": "stop_unavailable"}

    def _ensure_mobile_base_backend_started(self) -> dict[str, Any]:
        if not self._mobile_base_yaw_assist_enabled():
            return {"started": False, "reason": "yaw_assist_disabled"}

        backend = self._mobility_backend
        if backend is None:
            with self._lock:
                self._mobile_base_contact_ok = False
                self._last_mobile_base_error = "mobility_backend_unavailable"
            return {"started": False, "reason": "mobility_backend_unavailable"}

        open_method = getattr(backend, "open", None)
        try:
            with self._lock:
                already_started = self._mobile_base_backend_started
            if already_started:
                return {"started": False, "contact_ok": self._mobile_base_contact_ok}

            if callable(open_method):
                open_method()
                with self._lock:
                    self._mobile_base_backend_started = True
            else:
                with self._lock:
                    self._mobile_base_backend_started = False

            contact_ok = callable(getattr(backend, "send_velocity", None))
            read_available = getattr(backend, "read_available_lines", None)
            if callable(read_available):
                read_available(duration_sec=0.0)

            with self._lock:
                self._mobile_base_contact_ok = bool(contact_ok)
                self._last_mobile_base_error = None if contact_ok else "send_velocity_unavailable"
            return {"started": bool(callable(open_method)), "contact_ok": bool(contact_ok)}
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            with self._lock:
                self._mobile_base_contact_ok = False
                self._last_mobile_base_error = message
            LOGGER.warning("Look-at-me mobile-base backend contact failed: %s", message)
            return {"started": False, "contact_ok": False, "error": message}

    def _close_mobile_base_backend_if_started(self) -> None:
        with self._lock:
            should_close = self._mobile_base_backend_started
            self._mobile_base_backend_started = False
            self._mobile_base_contact_ok = False

        if not should_close:
            return

        close = getattr(self._mobility_backend, "close", None)
        if callable(close):
            try:
                close()
            except Exception as error:
                message = f"{type(error).__name__}: {error}"
                with self._lock:
                    self._last_mobile_base_error = message
                LOGGER.warning("Failed to close look-at-me mobile-base backend: %s", message)


class RuntimeBuilderLookAtMeMixin:
    def _build_look_at_me_session(
        self,
        *,
        vision_backend: Any,
        pan_tilt_backend: Any,
        vision_tracking_service: Any | None = None,
        mobility_backend: Any | None = None,
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
            mobility_backend=mobility_backend,
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
                "yaw_only_mobile_base_assist",
            ),
            metadata=session.status(),
        )


__all__ = ["LookAtMeSession", "RuntimeBuilderLookAtMeMixin"]
