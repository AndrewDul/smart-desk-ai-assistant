from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

from .motion_executor import TrackingMotionExecutionResult


@dataclass(frozen=True, slots=True)
class PanTiltExecutionAdapterConfig:
    """
    Dry-run pan-tilt adapter configuration.

    Sprint 8A defines the adapter contract only. It does not allow physical
    backend calls even if a future config accidentally asks for them.
    """

    dry_run: bool = True
    backend_command_execution_enabled: bool = False
    require_calibrated_limits: bool = True
    require_no_motion_startup_policy: bool = True
    max_allowed_pan_delta_degrees: float = 2.0
    max_allowed_tilt_delta_degrees: float = 2.0

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "PanTiltExecutionAdapterConfig":
        data = dict(payload or {})
        return cls(
            dry_run=bool(data.get("dry_run", True)),
            backend_command_execution_enabled=bool(
                data.get("backend_command_execution_enabled", False)
            ),
            require_calibrated_limits=bool(data.get("require_calibrated_limits", True)),
            require_no_motion_startup_policy=bool(
                data.get("require_no_motion_startup_policy", True)
            ),
            max_allowed_pan_delta_degrees=max(
                0.0,
                float(data.get("max_allowed_pan_delta_degrees", 2.0)),
            ),
            max_allowed_tilt_delta_degrees=max(
                0.0,
                float(data.get("max_allowed_tilt_delta_degrees", 2.0)),
            ),
        )

    @property
    def effective_backend_command_execution_enabled(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class PanTiltExecutionAdapterResult:
    action: str = "pan_tilt_tracking_execute"
    status: str = "dry_run"
    accepted: bool = True
    dry_run: bool = True
    has_target: bool = False
    would_send_pan_tilt_command: bool = False
    backend_command_execution_enabled: bool = False
    backend_command_executed: bool = False
    backend_name: str = "none"
    requested_pan_delta_degrees: float = 0.0
    requested_tilt_delta_degrees: float = 0.0
    clamped_pan_delta_degrees: float = 0.0
    clamped_tilt_delta_degrees: float = 0.0
    blocked_reason: str = "dry_run_contract"
    metadata: dict[str, Any] = field(default_factory=dict)


class PanTiltExecutionAdapter:
    """
    Contract boundary between tracking execution results and pan-tilt hardware.

    Sprint 8A never calls the backend. It only converts a dry-run tracking
    execution result into adapter-level metadata for future tiny movement work.
    """

    def __init__(
        self,
        *,
        pan_tilt_backend: Any | None = None,
        config: dict[str, Any] | PanTiltExecutionAdapterConfig | None = None,
    ) -> None:
        self._pan_tilt_backend = pan_tilt_backend
        if isinstance(config, PanTiltExecutionAdapterConfig):
            self._config = config
        else:
            self._config = PanTiltExecutionAdapterConfig.from_mapping(config)

    def prepare(
        self,
        execution: TrackingMotionExecutionResult | dict[str, Any] | None,
    ) -> PanTiltExecutionAdapterResult:
        payload = _execution_to_mapping(execution)
        if not payload:
            return self._result(
                status="no_execution_result",
                accepted=False,
                blocked_reason="no_execution_result",
                payload={},
            )

        has_target = bool(payload.get("has_target", False))
        would_move_pan_tilt = bool(payload.get("would_move_pan_tilt", False))
        requested_pan = _safe_float(payload.get("pan_delta_degrees", 0.0))
        requested_tilt = _safe_float(payload.get("tilt_delta_degrees", 0.0))

        clamped_pan = _clamp_delta(
            requested_pan,
            self._config.max_allowed_pan_delta_degrees,
        )
        clamped_tilt = _clamp_delta(
            requested_tilt,
            self._config.max_allowed_tilt_delta_degrees,
        )

        if not has_target:
            return self._result(
                status="no_target",
                accepted=True,
                has_target=False,
                would_send_pan_tilt_command=False,
                requested_pan_delta_degrees=requested_pan,
                requested_tilt_delta_degrees=requested_tilt,
                clamped_pan_delta_degrees=clamped_pan,
                clamped_tilt_delta_degrees=clamped_tilt,
                blocked_reason="no_target",
                payload=payload,
            )

        if not would_move_pan_tilt:
            return self._result(
                status="no_pan_tilt_motion_required",
                accepted=True,
                has_target=True,
                would_send_pan_tilt_command=False,
                requested_pan_delta_degrees=requested_pan,
                requested_tilt_delta_degrees=requested_tilt,
                clamped_pan_delta_degrees=clamped_pan,
                clamped_tilt_delta_degrees=clamped_tilt,
                blocked_reason="no_motion_required",
                payload=payload,
            )

        return self._result(
            status="dry_run_backend_command_blocked",
            accepted=True,
            has_target=True,
            would_send_pan_tilt_command=True,
            requested_pan_delta_degrees=requested_pan,
            requested_tilt_delta_degrees=requested_tilt,
            clamped_pan_delta_degrees=clamped_pan,
            clamped_tilt_delta_degrees=clamped_tilt,
            blocked_reason="dry_run_backend_command_gate",
            payload=payload,
        )

    def status(self) -> dict[str, Any]:
        return {
            "dry_run": True,
            "backend_command_execution_enabled": False,
            "requested_backend_command_execution_enabled": (
                self._config.backend_command_execution_enabled
            ),
            "effective_backend_command_execution_enabled": (
                self._config.effective_backend_command_execution_enabled
            ),
            "require_calibrated_limits": self._config.require_calibrated_limits,
            "require_no_motion_startup_policy": self._config.require_no_motion_startup_policy,
            "max_allowed_pan_delta_degrees": self._config.max_allowed_pan_delta_degrees,
            "max_allowed_tilt_delta_degrees": self._config.max_allowed_tilt_delta_degrees,
            "pan_tilt_backend_attached": self._pan_tilt_backend is not None,
            "backend_name": _backend_name(self._pan_tilt_backend),
        }

    def _result(
        self,
        *,
        status: str,
        accepted: bool,
        blocked_reason: str,
        payload: dict[str, Any],
        has_target: bool = False,
        would_send_pan_tilt_command: bool = False,
        requested_pan_delta_degrees: float = 0.0,
        requested_tilt_delta_degrees: float = 0.0,
        clamped_pan_delta_degrees: float = 0.0,
        clamped_tilt_delta_degrees: float = 0.0,
    ) -> PanTiltExecutionAdapterResult:
        return PanTiltExecutionAdapterResult(
            status=status,
            accepted=accepted,
            dry_run=True,
            has_target=has_target,
            would_send_pan_tilt_command=would_send_pan_tilt_command,
            backend_command_execution_enabled=False,
            backend_command_executed=False,
            backend_name=_backend_name(self._pan_tilt_backend),
            requested_pan_delta_degrees=round(float(requested_pan_delta_degrees), 4),
            requested_tilt_delta_degrees=round(float(requested_tilt_delta_degrees), 4),
            clamped_pan_delta_degrees=round(float(clamped_pan_delta_degrees), 4),
            clamped_tilt_delta_degrees=round(float(clamped_tilt_delta_degrees), 4),
            blocked_reason=blocked_reason,
            metadata={
                "tracking_execution_result": payload,
                "adapter_status": self.status(),
                "safety_note": (
                    "Sprint 8A defines the pan-tilt adapter contract only. "
                    "No backend command is executed."
                ),
            },
        )


def _execution_to_mapping(
    execution: TrackingMotionExecutionResult | dict[str, Any] | None,
) -> dict[str, Any]:
    if execution is None:
        return {}

    if is_dataclass(execution):
        return dict(asdict(execution))

    if isinstance(execution, dict):
        return dict(execution)

    return {}


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp_delta(value: float, max_abs_value: float) -> float:
    limit = abs(float(max_abs_value))
    return max(-limit, min(limit, float(value)))


def _backend_name(backend: Any | None) -> str:
    if backend is None:
        return "none"
    return backend.__class__.__name__


__all__ = [
    "PanTiltExecutionAdapter",
    "PanTiltExecutionAdapterConfig",
    "PanTiltExecutionAdapterResult",
]
