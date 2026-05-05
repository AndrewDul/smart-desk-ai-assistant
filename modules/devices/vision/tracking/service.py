from __future__ import annotations

from dataclasses import asdict
from typing import Any

from modules.runtime.contracts import VisionObservation

from .models import TrackingMotionPlan, TrackingPolicyConfig, TrackingSafeLimits
from .pan_tilt_policy import PanTiltTrackingPolicy


class VisionTrackingService:
    """
    Low-latency dry-run tracking coordinator.

    The service reads only the latest cached vision observation by default,
    computes a pure tracking motion plan, and never moves pan-tilt or the
    mobile base directly.
    """

    def __init__(
        self,
        *,
        vision_backend: Any,
        pan_tilt_backend: Any | None = None,
        config: dict[str, Any] | None = None,
        policy: PanTiltTrackingPolicy | None = None,
    ) -> None:
        self._vision_backend = vision_backend
        self._pan_tilt_backend = pan_tilt_backend
        self._config = dict(config or {})
        policy_config_payload = dict(self._config.get("policy", self._config) or {})
        self._policy = policy or PanTiltTrackingPolicy(
            config=TrackingPolicyConfig.from_mapping(policy_config_payload)
        )
        self._last_plan: TrackingMotionPlan | None = None
        self._last_error: str | None = None

    def plan_once(self, *, force_refresh: bool = False) -> TrackingMotionPlan:
        """
        Compute one tracking plan from the latest observation.

        force_refresh defaults to False because this service is meant for the
        hot tracking path. It should not force camera capture unless a caller
        explicitly asks for that slower behavior.
        """
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
            self._last_error = None
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
            return plan

    def latest_plan(self) -> TrackingMotionPlan | None:
        return self._last_plan

    def status(self) -> dict[str, Any]:
        return {
            "ok": self._last_error is None,
            "dry_run": True,
            "movement_execution_enabled": False,
            "last_error": self._last_error,
            "last_plan": None if self._last_plan is None else asdict(self._last_plan),
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


def _float_from(payload: Any, key: str, default: float) -> float:
    if not isinstance(payload, dict):
        return float(default)
    try:
        return float(payload.get(key, default))
    except (TypeError, ValueError):
        return float(default)
