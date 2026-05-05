from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

from .models import TrackingMotionPlan


@dataclass(frozen=True, slots=True)
class TrackingMotionExecutorConfig:
    """
    Safety gate configuration for tracking motion execution.

    Sprint 6A exposes requested execution gates separately from effective
    execution gates. Physical movement remains blocked at the effective layer.
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
    def requested_any_physical_execution(self) -> bool:
        return bool(
            self.movement_execution_enabled
            or self.pan_tilt_movement_execution_enabled
            or self.base_yaw_assist_execution_enabled
            or self.base_forward_backward_movement_enabled
        )

    @property
    def effective_dry_run(self) -> bool:
        return True

    @property
    def effective_movement_execution_enabled(self) -> bool:
        return False

    @property
    def effective_pan_tilt_movement_execution_enabled(self) -> bool:
        return False

    @property
    def effective_base_yaw_assist_execution_enabled(self) -> bool:
        return False

    @property
    def effective_base_forward_backward_movement_enabled(self) -> bool:
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

    requested_movement_execution_enabled: bool = False
    requested_pan_tilt_movement_execution_enabled: bool = False
    requested_base_yaw_assist_execution_enabled: bool = False
    requested_base_forward_backward_movement_enabled: bool = False

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
    execution_block_reason: str = "dry_run_safety_gate"
    metadata: dict[str, Any] = field(default_factory=dict)


class TrackingMotionExecutor:
    """
    Dry-run execution boundary for vision tracking motion plans.

    The executor shows what would be requested, but Sprint 6A keeps all
    effective execution gates closed.
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
            "execution_block_reason": "dry_run_safety_gate",
            "requested_any_physical_execution": self._config.requested_any_physical_execution,
            "requested_dry_run": self._config.dry_run,
            "requested_movement_execution_enabled": self._config.movement_execution_enabled,
            "requested_pan_tilt_movement_execution_enabled": (
                self._config.pan_tilt_movement_execution_enabled
            ),
            "requested_base_yaw_assist_execution_enabled": (
                self._config.base_yaw_assist_execution_enabled
            ),
            "requested_base_forward_backward_movement_enabled": (
                self._config.base_forward_backward_movement_enabled
            ),
            "effective_dry_run": self._config.effective_dry_run,
            "effective_movement_execution_enabled": (
                self._config.effective_movement_execution_enabled
            ),
            "effective_pan_tilt_movement_execution_enabled": (
                self._config.effective_pan_tilt_movement_execution_enabled
            ),
            "effective_base_yaw_assist_execution_enabled": (
                self._config.effective_base_yaw_assist_execution_enabled
            ),
            "effective_base_forward_backward_movement_enabled": (
                self._config.effective_base_forward_backward_movement_enabled
            ),
            "movement_execution_enabled": False,
            "pan_tilt_movement_execution_enabled": False,
            "base_yaw_assist_execution_enabled": False,
            "base_forward_backward_movement_enabled": False,
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
        executor_status = self.status()
        return TrackingMotionExecutionResult(
            status=status,
            accepted=accepted,
            dry_run=True,
            has_target=has_target,
            would_move_pan_tilt=would_move_pan_tilt,
            would_request_base_yaw_assist=would_request_base_yaw_assist,
            requested_movement_execution_enabled=self._config.movement_execution_enabled,
            requested_pan_tilt_movement_execution_enabled=(
                self._config.pan_tilt_movement_execution_enabled
            ),
            requested_base_yaw_assist_execution_enabled=(
                self._config.base_yaw_assist_execution_enabled
            ),
            requested_base_forward_backward_movement_enabled=(
                self._config.base_forward_backward_movement_enabled
            ),
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
            execution_block_reason="dry_run_safety_gate",
            metadata={
                "plan": plan_metadata,
                "executor_status": executor_status,
                "safety_note": (
                    "Sprint 6A exposes requested execution gates, but all "
                    "effective physical movement gates remain closed."
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
