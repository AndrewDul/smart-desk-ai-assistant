from __future__ import annotations

from modules.devices.vision.tracking import (
    PanTiltExecutionAdapter,
    TrackingMotionExecutionResult,
)


class _PanTiltBackendShouldNotBeCalled:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def move_direction(self, direction: str) -> dict:
        self.calls.append(direction)
        raise AssertionError("Pan-tilt backend must not be called in Sprint 8A.")

    def move_delta(self, *, pan_delta_degrees: float, tilt_delta_degrees: float) -> dict:
        self.calls.append(f"{pan_delta_degrees}:{tilt_delta_degrees}")
        raise AssertionError("Pan-tilt backend must not be called in Sprint 8A.")



class _PanTiltBackendWithDelta:
    def __init__(self) -> None:
        self.calls: list[dict[str, float]] = []

    def move_delta(self, *, pan_delta_degrees: float, tilt_delta_degrees: float) -> dict:
        self.calls.append(
            {
                "pan_delta_degrees": pan_delta_degrees,
                "tilt_delta_degrees": tilt_delta_degrees,
            }
        )
        return {
            "ok": True,
            "pan_delta_degrees": pan_delta_degrees,
            "tilt_delta_degrees": tilt_delta_degrees,
        }


def test_pan_tilt_adapter_prepares_dry_run_command_without_calling_backend() -> None:
    backend = _PanTiltBackendShouldNotBeCalled()
    adapter = PanTiltExecutionAdapter(pan_tilt_backend=backend)
    execution = TrackingMotionExecutionResult(
        status="dry_run_motion_blocked",
        has_target=True,
        would_move_pan_tilt=True,
        pan_delta_degrees=0.5,
        tilt_delta_degrees=-0.25,
        reason="dry_run_execution_only",
    )

    result = adapter.prepare(execution)

    assert result.accepted is True
    assert result.status == "dry_run_backend_command_blocked"
    assert result.dry_run is True
    assert result.has_target is True
    assert result.would_send_pan_tilt_command is True
    assert result.backend_command_execution_enabled is False
    assert result.backend_command_executed is False
    assert result.backend_name == "_PanTiltBackendShouldNotBeCalled"
    assert result.requested_pan_delta_degrees == 0.5
    assert result.requested_tilt_delta_degrees == -0.25
    assert result.clamped_pan_delta_degrees == 0.5
    assert result.clamped_tilt_delta_degrees == -0.25
    assert result.blocked_reason == "dry_run_backend_command_gate"
    assert backend.calls == []


def test_pan_tilt_adapter_clamps_large_requested_deltas_in_contract_metadata() -> None:
    adapter = PanTiltExecutionAdapter(
        config={
            "max_allowed_pan_delta_degrees": 2.0,
            "max_allowed_tilt_delta_degrees": 1.0,
        }
    )
    execution = TrackingMotionExecutionResult(
        has_target=True,
        would_move_pan_tilt=True,
        pan_delta_degrees=7.5,
        tilt_delta_degrees=-3.0,
    )

    result = adapter.prepare(execution)

    assert result.would_send_pan_tilt_command is True
    assert result.requested_pan_delta_degrees == 7.5
    assert result.requested_tilt_delta_degrees == -3.0
    assert result.clamped_pan_delta_degrees == 2.0
    assert result.clamped_tilt_delta_degrees == -1.0
    assert result.backend_command_executed is False


def test_pan_tilt_adapter_blocks_even_when_config_requests_backend_execution() -> None:
    backend = _PanTiltBackendShouldNotBeCalled()
    adapter = PanTiltExecutionAdapter(
        pan_tilt_backend=backend,
        config={
            "dry_run": False,
            "backend_command_execution_enabled": True,
        },
    )
    execution = TrackingMotionExecutionResult(
        has_target=True,
        would_move_pan_tilt=True,
        pan_delta_degrees=1.0,
    )

    result = adapter.prepare(execution)
    status = adapter.status()

    assert result.status == "dry_run_backend_command_blocked"
    assert result.backend_command_execution_enabled is False
    assert result.backend_command_executed is False
    assert status["requested_backend_command_execution_enabled"] is True
    assert status["effective_backend_command_execution_enabled"] is False
    assert backend.calls == []


def test_pan_tilt_adapter_reports_no_motion_required_for_centered_target() -> None:
    adapter = PanTiltExecutionAdapter()
    execution = TrackingMotionExecutionResult(
        has_target=True,
        would_move_pan_tilt=False,
        pan_delta_degrees=0.0,
        tilt_delta_degrees=0.0,
    )

    result = adapter.prepare(execution)

    assert result.status == "no_pan_tilt_motion_required"
    assert result.would_send_pan_tilt_command is False
    assert result.backend_command_executed is False
    assert result.blocked_reason == "no_motion_required"


def test_pan_tilt_adapter_reports_no_target_without_backend_command() -> None:
    adapter = PanTiltExecutionAdapter()
    execution = TrackingMotionExecutionResult(
        has_target=False,
        would_move_pan_tilt=False,
        reason="no_target",
    )

    result = adapter.prepare(execution)

    assert result.status == "no_target"
    assert result.has_target is False
    assert result.would_send_pan_tilt_command is False
    assert result.backend_command_executed is False
    assert result.blocked_reason == "no_target"


def test_pan_tilt_adapter_rejects_missing_execution_result() -> None:
    adapter = PanTiltExecutionAdapter()

    result = adapter.prepare(None)

    assert result.accepted is False
    assert result.status == "no_execution_result"
    assert result.backend_command_executed is False
    assert result.blocked_reason == "no_execution_result"



def test_pan_tilt_adapter_executes_backend_delta_only_when_all_runtime_gates_are_enabled() -> None:
    backend = _PanTiltBackendWithDelta()
    adapter = PanTiltExecutionAdapter(
        pan_tilt_backend=backend,
        config={
            "dry_run": False,
            "backend_command_execution_enabled": True,
            "runtime_hardware_execution_enabled": True,
            "physical_movement_confirmed": True,
            "max_allowed_pan_delta_degrees": 2.0,
            "max_allowed_tilt_delta_degrees": 2.0,
        },
    )
    execution = TrackingMotionExecutionResult(
        has_target=True,
        would_move_pan_tilt=True,
        pan_delta_degrees=0.75,
        tilt_delta_degrees=-0.25,
    )

    result = adapter.prepare(execution)

    assert result.status == "backend_command_executed"
    assert result.accepted is True
    assert result.dry_run is False
    assert result.would_send_pan_tilt_command is True
    assert result.backend_command_execution_enabled is True
    assert result.backend_command_executed is True
    assert result.clamped_pan_delta_degrees == 0.75
    assert result.clamped_tilt_delta_degrees == -0.25
    assert result.blocked_reason == ""
    assert backend.calls == [
        {
            "pan_delta_degrees": 0.75,
            "tilt_delta_degrees": -0.25,
        }
    ]


def test_pan_tilt_adapter_keeps_backend_blocked_when_runtime_gate_is_missing() -> None:
    backend = _PanTiltBackendWithDelta()
    adapter = PanTiltExecutionAdapter(
        pan_tilt_backend=backend,
        config={
            "dry_run": False,
            "backend_command_execution_enabled": True,
            "runtime_hardware_execution_enabled": False,
            "physical_movement_confirmed": True,
        },
    )
    execution = TrackingMotionExecutionResult(
        has_target=True,
        would_move_pan_tilt=True,
        pan_delta_degrees=0.5,
    )

    result = adapter.prepare(execution)

    assert result.status == "dry_run_backend_command_blocked"
    assert result.backend_command_execution_enabled is False
    assert result.backend_command_executed is False
    assert result.blocked_reason == "runtime_hardware_execution_gate"
    assert backend.calls == []


def test_pan_tilt_adapter_reports_missing_move_delta_when_execution_is_enabled() -> None:
    class _BackendWithoutMoveDelta:
        pass

    adapter = PanTiltExecutionAdapter(
        pan_tilt_backend=_BackendWithoutMoveDelta(),
        config={
            "dry_run": False,
            "backend_command_execution_enabled": True,
            "runtime_hardware_execution_enabled": True,
            "physical_movement_confirmed": True,
        },
    )
    execution = TrackingMotionExecutionResult(
        has_target=True,
        would_move_pan_tilt=True,
        pan_delta_degrees=0.5,
    )

    result = adapter.prepare(execution)

    assert result.status == "backend_move_delta_unavailable"
    assert result.accepted is False
    assert result.backend_command_execution_enabled is True
    assert result.backend_command_executed is False
    assert result.blocked_reason == "backend_move_delta_unavailable"
