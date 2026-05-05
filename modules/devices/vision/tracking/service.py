from __future__ import annotations

import time
from dataclasses import asdict
from typing import Any

from modules.runtime.contracts import VisionObservation

from .models import TrackingMotionPlan, TrackingPolicyConfig, TrackingSafeLimits
from .motion_executor import TrackingMotionExecutionResult, TrackingMotionExecutor
from .pan_tilt_policy import PanTiltTrackingPolicy
from .telemetry import VisionTrackingTelemetryWriter


class VisionTrackingService:
    """
    Low-latency dry-run tracking coordinator.

    The service reads only the latest cached vision observation by default,
    computes a pure tracking motion plan, creates a dry-run execution result,
    and never moves pan-tilt or the mobile base directly.
    """

    def __init__(
        self,
        *,
        vision_backend: Any,
        pan_tilt_backend: Any | None = None,
        config: dict[str, Any] | None = None,
        policy: PanTiltTrackingPolicy | None = None,
        motion_executor: TrackingMotionExecutor | None = None,
    ) -> None:
        self._vision_backend = vision_backend
        self._pan_tilt_backend = pan_tilt_backend
        self._config = dict(config or {})
        policy_config_payload = dict(self._config.get("policy", self._config) or {})
        self._policy = policy or PanTiltTrackingPolicy(
            config=TrackingPolicyConfig.from_mapping(policy_config_payload)
        )

        motion_executor_config = dict(
            self._config.get("motion_executor", self._config.get("executor", {})) or {}
        )
        self._motion_executor = motion_executor or TrackingMotionExecutor(
            pan_tilt_backend=pan_tilt_backend,
            mobile_base_backend=None,
            config=motion_executor_config,
        )

        self._last_plan: TrackingMotionPlan | None = None
        self._last_execution_result: TrackingMotionExecutionResult | None = None
        self._last_error: str | None = None
        self._last_telemetry_error: str | None = None
        self._last_plan_timestamp_monotonic: float | None = None
        self._persist_status = bool(self._config.get("persist_status", True))
        self._status_path = str(
            self._config.get("status_path", "var/data/vision_tracking_status.json")
        )
        self._telemetry_writer = VisionTrackingTelemetryWriter(path=self._status_path)

    def plan_once(self, *, force_refresh: bool = False) -> TrackingMotionPlan:
        """
        Compute one tracking plan from the latest observation.

        force_refresh defaults to False because this service is meant for the
        hot tracking path. It should not force camera capture unless a caller
        explicitly asks for that slower behavior.
        """
        started_at = time.monotonic()
        try:
            observation = self._latest_observation(force_refresh=force_refresh)
            pan_state = self._pan_tilt_state()
            plan = self._policy.plan_from_observation(
                observation,
                current_pan_degrees=pan_state["pan_degrees"],
                current_tilt_degrees=pan_state["tilt_degrees"],
                safe_limits=pan_state["safe_limits"],
            )
            self._last_plan = plan
            self._last_execution_result = self._motion_executor.execute(plan)
            self._last_error = None
            self._last_plan_timestamp_monotonic = time.monotonic()
            self._persist_latest_status(
                force_refresh=force_refresh,
                elapsed_ms=(time.monotonic() - started_at) * 1000.0,
            )
            return plan
        except Exception as error:
            self._last_error = f"{error.__class__.__name__}: {error}"
            plan = TrackingMotionPlan(
                has_target=False,
                target=None,
                reason="tracking_service_error",
                diagnostics={"error": self._last_error},
            )
            self._last_plan = plan
            self._last_execution_result = self._motion_executor.execute(plan)
            self._last_plan_timestamp_monotonic = time.monotonic()
            self._persist_latest_status(
                force_refresh=force_refresh,
                elapsed_ms=(time.monotonic() - started_at) * 1000.0,
            )
            return plan

    def execute_plan_dry_run(
        self,
        plan: TrackingMotionPlan | dict[str, Any] | None,
    ) -> TrackingMotionExecutionResult:
        result = self._motion_executor.execute(plan)
        self._last_execution_result = result
        return result

    def latest_plan(self) -> TrackingMotionPlan | None:
        return self._last_plan

    def latest_execution_result(self) -> TrackingMotionExecutionResult | None:
        return self._last_execution_result

    def status(self) -> dict[str, Any]:
        return {
            "ok": self._last_error is None,
            "dry_run": True,
            "movement_execution_enabled": False,
            "pan_tilt_movement_execution_enabled": False,
            "base_yaw_assist_execution_enabled": False,
            "base_forward_backward_movement_enabled": False,
            "persist_status": self._persist_status,
            "status_path": self._status_path,
            "last_error": self._last_error,
            "last_telemetry_error": self._last_telemetry_error,
            "last_plan_timestamp_monotonic": self._last_plan_timestamp_monotonic,
            "last_plan": None if self._last_plan is None else asdict(self._last_plan),
            "last_execution_result": (
                None if self._last_execution_result is None else asdict(self._last_execution_result)
            ),
            "motion_executor_status": self._motion_executor.status(),
        }

    def _latest_observation(self, *, force_refresh: bool) -> VisionObservation | None:
        method = getattr(self._vision_backend, "latest_observation", None)
        if not callable(method):
            return None
        return method(force_refresh=force_refresh)

    def _pan_tilt_state(self) -> dict[str, Any]:
        status = self._pan_tilt_status()
        safe_limits_payload = status.get("safe_limits") if isinstance(status, dict) else None
        safe_limits = TrackingSafeLimits.from_mapping(
            safe_limits_payload if isinstance(safe_limits_payload, dict) else None
        )
        pan_degrees = _float_from(
            status,
            "pan_angle",
            _float_from(safe_limits_payload, "pan_center_degrees", 0.0),
        )
        tilt_degrees = _float_from(
            status,
            "tilt_angle",
            _float_from(safe_limits_payload, "tilt_center_degrees", 0.0),
        )
        return {
            "pan_degrees": pan_degrees,
            "tilt_degrees": tilt_degrees,
            "safe_limits": safe_limits,
        }

    def _pan_tilt_status(self) -> dict[str, Any]:
        if self._pan_tilt_backend is None:
            return {}
        method = getattr(self._pan_tilt_backend, "status", None)
        if not callable(method):
            return {}
        result = method()
        return result if isinstance(result, dict) else {}

    def _persist_latest_status(self, *, force_refresh: bool, elapsed_ms: float) -> None:
        self._last_telemetry_error = None
        if not self._persist_status:
            return

        try:
            payload = self.status()
            payload["event"] = "vision_tracking_plan"
            payload["force_refresh"] = bool(force_refresh)
            payload["plan_elapsed_ms"] = round(float(elapsed_ms), 4)
            self._telemetry_writer.write_snapshot(payload)
        except Exception as error:
            self._last_telemetry_error = f"{error.__class__.__name__}: {error}"


def _float_from(payload: Any, key: str, default: float) -> float:
    if not isinstance(payload, dict):
        return float(default)
    try:
        return float(payload.get(key, default))
    except (TypeError, ValueError):
        return float(default)


__all__ = ["VisionTrackingService"]
