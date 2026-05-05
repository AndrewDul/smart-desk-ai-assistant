from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any

from .motion_executor import TrackingMotionExecutionResult


@dataclass(frozen=True, slots=True)
class PanTiltExecutionAdapterConfig:
    """
    Safety-gated pan-tilt adapter configuration.

    Default settings remain dry-run only. Backend execution is only possible
    when all explicit hardware gates are enabled by a future controlled sprint.
    """

    dry_run: bool = True
    backend_command_execution_enabled: bool = False
    runtime_hardware_execution_enabled: bool = False
    physical_movement_confirmed: bool = False
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
            runtime_hardware_execution_enabled=bool(
                data.get("runtime_hardware_execution_enabled", False)
            ),
            physical_movement_confirmed=bool(
                data.get("physical_movement_confirmed", False)
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
        return bool(
            not self.dry_run
            and self.backend_command_execution_enabled
            and self.runtime_hardware_execution_enabled
            and self.physical_movement_confirmed
        )


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

    Sprint 10A adds a hardware-capable path, but it is gated by explicit config
    and remains disabled by default. Existing runtime settings must still produce
    backend_command_executed=false.
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

        if not self._config.effective_backend_command_execution_enabled:
            return self._result(
                status="dry_run_backend_command_blocked",
                accepted=True,
                has_target=True,
                would_send_pan_tilt_command=True,
                requested_pan_delta_degrees=requested_pan,
                requested_tilt_delta_degrees=requested_tilt,
                clamped_pan_delta_degrees=clamped_pan,
                clamped_tilt_delta_degrees=clamped_tilt,
                blocked_reason=self._blocked_backend_execution_reason(),
                payload=payload,
            )

        return self._execute_backend_delta(
            payload=payload,
            requested_pan=requested_pan,
            requested_tilt=requested_tilt,
            clamped_pan=clamped_pan,
            clamped_tilt=clamped_tilt,
        )

    def status(self) -> dict[str, Any]:
        return {
            "dry_run": self._config.dry_run,
            "requested_backend_command_execution_enabled": (
                self._config.backend_command_execution_enabled
            ),
            "backend_command_execution_enabled": self._config.backend_command_execution_enabled,
            "runtime_hardware_execution_enabled": self._config.runtime_hardware_execution_enabled,
            "physical_movement_confirmed": self._config.physical_movement_confirmed,
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

    def _blocked_backend_execution_reason(self) -> str:
        if self._config.dry_run:
            return "dry_run_backend_command_gate"
        if not self._config.backend_command_execution_enabled:
            return "backend_command_execution_gate"
        if not self._config.runtime_hardware_execution_enabled:
            return "runtime_hardware_execution_gate"
        if not self._config.physical_movement_confirmed:
            return "physical_movement_confirmation_gate"
        return "runtime_hardware_execution_gate"

    def _execute_backend_delta(
        self,
        *,
        payload: dict[str, Any],
        requested_pan: float,
        requested_tilt: float,
        clamped_pan: float,
        clamped_tilt: float,
    ) -> PanTiltExecutionAdapterResult:
        if self._pan_tilt_backend is None:
            return self._result(
                status="backend_unavailable",
                accepted=False,
                has_target=True,
                would_send_pan_tilt_command=True,
                requested_pan_delta_degrees=requested_pan,
                requested_tilt_delta_degrees=requested_tilt,
                clamped_pan_delta_degrees=clamped_pan,
                clamped_tilt_delta_degrees=clamped_tilt,
                blocked_reason="backend_unavailable",
                payload=payload,
            )

        move_delta = getattr(self._pan_tilt_backend, "move_delta", None)
        if not callable(move_delta):
            return self._result(
                status="backend_move_delta_unavailable",
                accepted=False,
                has_target=True,
                would_send_pan_tilt_command=True,
                requested_pan_delta_degrees=requested_pan,
                requested_tilt_delta_degrees=requested_tilt,
                clamped_pan_delta_degrees=clamped_pan,
                clamped_tilt_delta_degrees=clamped_tilt,
                blocked_reason="backend_move_delta_unavailable",
                payload=payload,
            )

        try:
            backend_response = move_delta(
                pan_delta_degrees=clamped_pan,
                tilt_delta_degrees=clamped_tilt,
            )
        except Exception as error:
            return self._result(
                status="backend_command_failed",
                accepted=False,
                has_target=True,
                would_send_pan_tilt_command=True,
                requested_pan_delta_degrees=requested_pan,
                requested_tilt_delta_degrees=requested_tilt,
                clamped_pan_delta_degrees=clamped_pan,
                clamped_tilt_delta_degrees=clamped_tilt,
                blocked_reason=f"backend_command_failed:{error.__class__.__name__}",
                payload=payload,
                backend_response={"error": f"{error.__class__.__name__}: {error}"},
            )

        return self._result(
            status="backend_command_executed",
            accepted=True,
            has_target=True,
            would_send_pan_tilt_command=True,
            requested_pan_delta_degrees=requested_pan,
            requested_tilt_delta_degrees=requested_tilt,
            clamped_pan_delta_degrees=clamped_pan,
            clamped_tilt_delta_degrees=clamped_tilt,
            blocked_reason="",
            payload=payload,
            backend_command_executed=True,
            backend_response=_mapping_or_value(backend_response),
        )

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
        backend_command_executed: bool = False,
        backend_response: Any | None = None,
    ) -> PanTiltExecutionAdapterResult:
        effective_execution = self._config.effective_backend_command_execution_enabled
        return PanTiltExecutionAdapterResult(
            status=status,
            accepted=accepted,
            dry_run=not effective_execution,
            has_target=has_target,
            would_send_pan_tilt_command=would_send_pan_tilt_command,
            backend_command_execution_enabled=effective_execution,
            backend_command_executed=bool(backend_command_executed),
            backend_name=_backend_name(self._pan_tilt_backend),
            requested_pan_delta_degrees=round(float(requested_pan_delta_degrees), 4),
            requested_tilt_delta_degrees=round(float(requested_tilt_delta_degrees), 4),
            clamped_pan_delta_degrees=round(float(clamped_pan_delta_degrees), 4),
            clamped_tilt_delta_degrees=round(float(clamped_tilt_delta_degrees), 4),
            blocked_reason=blocked_reason,
            metadata={
                "tracking_execution_result": payload,
                "adapter_status": self.status(),
                "backend_response": backend_response,
                "safety_note": (
                    "Backend command execution is only allowed when dry_run=false, "
                    "backend_command_execution_enabled=true, "
                    "runtime_hardware_execution_enabled=true, and "
                    "physical_movement_confirmed=true."
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


def _mapping_or_value(value: Any) -> Any:
    if isinstance(value, dict):
        return dict(value)
    return value


__all__ = [
    "PanTiltExecutionAdapter",
    "PanTiltExecutionAdapterConfig",
    "PanTiltExecutionAdapterResult",
]
