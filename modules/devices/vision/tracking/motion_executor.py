from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

from .models import TrackingMotionPlan


@dataclass(frozen=True, slots=True)
class TrackingMotionExecutorConfig:
    """
    Safety gate configuration for tracking motion execution.

    Sprint 5A is dry-run only. Even if config asks for movement execution,
    this executor will not call pan-tilt or mobile-base hardware yet.
    """

    dry_run: bool = True
    movement_execution_enabled: bool = False
    pan_tilt_movement_execution_enabled: bool = False
    base_yaw_assist_execution_enabled: bool = False
    base_forward_backward_movement_enabled: bool = False

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "TrackingMotionExecutorConfig":
        data = dict(payload or {})
        return cls(
            dry_run=bool(data.get("dry_run", True)),
            movement_execution_enabled=bool(data.get("movement_execution_enabled", False)),
            pan_tilt_movement_execution_enabled=bool(
                data.get("pan_tilt_movement_execution_enabled", False)
            ),
            base_yaw_assist_execution_enabled=bool(
                data.get("base_yaw_assist_execution_enabled", False)
            ),
            base_forward_backward_movement_enabled=bool(
                data.get("base_forward_backward_movement_enabled", False)
            ),
        )

    @property
    def effective_movement_execution_enabled(self) -> bool:
        """
        Sprint 5A intentionally blocks physical execution.

        Future sprints can replace this once hardware smoke tests and safety
        gates are ready.
        """
        return False


@dataclass(frozen=True, slots=True)
class TrackingMotionExecutionResult:
    action: str = "tracking_motion_execute"
    status: str = "dry_run"
    accepted: bool = True
    dry_run: bool = True
    has_target: bool = False
    would_move_pan_tilt: bool = False
    would_request_base_yaw_assist: bool = False
    movement_execution_enabled: bool = False
    pan_tilt_movement_execution_enabled: bool = False
    base_yaw_assist_execution_enabled: bool = False
    base_forward_backward_movement_enabled: bool = False
    pan_tilt_movement_executed: bool = False
    base_movement_executed: bool = False
    pan_delta_degrees: float = 0.0
    tilt_delta_degrees: float = 0.0
    base_yaw_direction: str | None = None
    reason: str = "no_plan"
    metadata: dict[str, Any] = field(default_factory=dict)


class TrackingMotionExecutor:
    """
    Dry-run execution boundary for vision tracking motion plans.

    This class is intentionally separate from the tracking policy:
    - policy decides what should happen,
    - executor decides whether anything may be executed,
    - Sprint 5A always blocks physical movement.
    """

    def __init__(
        self,
        *,
        pan_tilt_backend: Any | None = None,
        mobile_base_backend: Any | None = None,
        config: dict[str, Any] | TrackingMotionExecutorConfig | None = None,
    ) -> None:
        self._pan_tilt_backend = pan_tilt_backend
        self._mobile_base_backend = mobile_base_backend
        if isinstance(config, TrackingMotionExecutorConfig):
            self._config = config
        else:
            self._config = TrackingMotionExecutorConfig.from_mapping(config)

    def execute(self, plan: TrackingMotionPlan | dict[str, Any] | None) -> TrackingMotionExecutionResult:
        plan_metadata = _plan_to_mapping(plan)

        if not plan_metadata:
            return self._result(
                status="no_plan",
                accepted=False,
                reason="no_plan",
                plan_metadata={},
            )

        has_target = bool(plan_metadata.get("has_target", False))
        pan_delta = _safe_float(plan_metadata.get("pan_delta_degrees", 0.0))
        tilt_delta = _safe_float(plan_metadata.get("tilt_delta_degrees", 0.0))
        base_yaw_assist_required = bool(plan_metadata.get("base_yaw_assist_required", False))
        base_yaw_direction = _safe_direction(plan_metadata.get("base_yaw_direction"))

        would_move_pan_tilt = bool(has_target and (abs(pan_delta) > 0.0 or abs(tilt_delta) > 0.0))
        would_request_base_yaw_assist = bool(has_target and base_yaw_assist_required)

        if not has_target:
            status = "no_target"
            reason = "no_target"
        elif would_move_pan_tilt or would_request_base_yaw_assist:
            status = "dry_run_motion_blocked"
            reason = "dry_run_execution_only"
        else:
            status = "no_motion_required"
            reason = str(plan_metadata.get("reason", "target_centered") or "target_centered")

        return self._result(
            status=status,
            accepted=True,
            reason=reason,
            has_target=has_target,
            would_move_pan_tilt=would_move_pan_tilt,
            would_request_base_yaw_assist=would_request_base_yaw_assist,
            pan_delta_degrees=pan_delta,
            tilt_delta_degrees=tilt_delta,
            base_yaw_direction=base_yaw_direction,
            plan_metadata=plan_metadata,
        )

    def status(self) -> dict[str, Any]:
        return {
            "dry_run": True,
            "movement_execution_enabled": False,
            "pan_tilt_movement_execution_enabled": False,
            "base_yaw_assist_execution_enabled": False,
            "base_forward_backward_movement_enabled": False,
            "effective_movement_execution_enabled": self._config.effective_movement_execution_enabled,
            "pan_tilt_backend_attached": self._pan_tilt_backend is not None,
            "mobile_base_backend_attached": self._mobile_base_backend is not None,
        }

    def _result(
        self,
        *,
        status: str,
        accepted: bool,
        reason: str,
        plan_metadata: dict[str, Any],
        has_target: bool = False,
        would_move_pan_tilt: bool = False,
        would_request_base_yaw_assist: bool = False,
        pan_delta_degrees: float = 0.0,
        tilt_delta_degrees: float = 0.0,
        base_yaw_direction: str | None = None,
    ) -> TrackingMotionExecutionResult:
        return TrackingMotionExecutionResult(
            status=status,
            accepted=accepted,
            dry_run=True,
            has_target=has_target,
            would_move_pan_tilt=would_move_pan_tilt,
            would_request_base_yaw_assist=would_request_base_yaw_assist,
            movement_execution_enabled=False,
            pan_tilt_movement_execution_enabled=False,
            base_yaw_assist_execution_enabled=False,
            base_forward_backward_movement_enabled=False,
            pan_tilt_movement_executed=False,
            base_movement_executed=False,
            pan_delta_degrees=round(float(pan_delta_degrees), 4),
            tilt_delta_degrees=round(float(tilt_delta_degrees), 4),
            base_yaw_direction=base_yaw_direction,
            reason=reason,
            metadata={
                "plan": plan_metadata,
                "executor_status": self.status(),
                "safety_note": (
                    "Sprint 5A is dry-run only. Physical pan-tilt and "
                    "mobile-base movement remain blocked."
                ),
            },
        )


def _plan_to_mapping(plan: TrackingMotionPlan | dict[str, Any] | None) -> dict[str, Any]:
    if plan is None:
        return {}

    if is_dataclass(plan):
        return dict(asdict(plan))

    if isinstance(plan, dict):
        return dict(plan)

    return {}


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_direction(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"left", "right"}:
        return text
    return None


__all__ = [
    "TrackingMotionExecutionResult",
    "TrackingMotionExecutor",
    "TrackingMotionExecutorConfig",
]
