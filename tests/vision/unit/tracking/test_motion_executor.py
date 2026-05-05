from __future__ import annotations

from modules.devices.vision.tracking import (
    TrackingMotionExecutor,
    TrackingMotionPlan,
)


class _PanTiltBackendShouldNotBeCalled:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def move_direction(self, direction: str) -> dict:
        self.calls.append(direction)
        raise AssertionError("Pan-tilt backend must not be called in Sprint 5A dry-run.")


class _MobileBaseBackendShouldNotBeCalled:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def rotate(self, direction: str) -> dict:
        self.calls.append(direction)
        raise AssertionError("Mobile base backend must not be called in Sprint 5A dry-run.")


def test_motion_executor_reports_pan_tilt_and_base_yaw_dry_run_without_movement() -> None:
    pan_tilt = _PanTiltBackendShouldNotBeCalled()
    base = _MobileBaseBackendShouldNotBeCalled()
    executor = TrackingMotionExecutor(
        pan_tilt_backend=pan_tilt,
        mobile_base_backend=base,
    )
    plan = TrackingMotionPlan(
        has_target=True,
        target=None,
        pan_delta_degrees=0.5,
        tilt_delta_degrees=0.0,
        desired_pan_degrees=15.5,
        clamped_pan_degrees=15.0,
        pan_at_limit=True,
        base_yaw_assist_required=True,
        base_yaw_direction="right",
        base_forward_velocity=0.0,
        base_backward_velocity=0.0,
        reason="pan_limit_base_yaw_assist_required",
    )

    result = executor.execute(plan)

    assert result.accepted is True
    assert result.status == "dry_run_motion_blocked"
    assert result.dry_run is True
    assert result.has_target is True
    assert result.would_move_pan_tilt is True
    assert result.would_request_base_yaw_assist is True
    assert result.base_yaw_direction == "right"
    assert result.movement_execution_enabled is False
    assert result.pan_tilt_movement_execution_enabled is False
    assert result.base_yaw_assist_execution_enabled is False
    assert result.base_forward_backward_movement_enabled is False
    assert result.pan_tilt_movement_executed is False
    assert result.base_movement_executed is False
    assert pan_tilt.calls == []
    assert base.calls == []


def test_motion_executor_blocks_even_if_config_accidentally_requests_execution() -> None:
    pan_tilt = _PanTiltBackendShouldNotBeCalled()
    base = _MobileBaseBackendShouldNotBeCalled()
    executor = TrackingMotionExecutor(
        pan_tilt_backend=pan_tilt,
        mobile_base_backend=base,
        config={
            "dry_run": False,
            "movement_execution_enabled": True,
            "pan_tilt_movement_execution_enabled": True,
            "base_yaw_assist_execution_enabled": True,
            "base_forward_backward_movement_enabled": True,
        },
    )
    plan = TrackingMotionPlan(
        has_target=True,
        target=None,
        pan_delta_degrees=2.0,
        tilt_delta_degrees=1.0,
        base_yaw_assist_required=True,
        base_yaw_direction="left",
        reason="recenter_target",
    )

    result = executor.execute(plan)

    assert result.status == "dry_run_motion_blocked"
    assert result.movement_execution_enabled is False
    assert result.pan_tilt_movement_execution_enabled is False
    assert result.base_yaw_assist_execution_enabled is False
    assert result.base_forward_backward_movement_enabled is False
    assert result.pan_tilt_movement_executed is False
    assert result.base_movement_executed is False
    assert result.metadata["executor_status"]["effective_movement_execution_enabled"] is False
    assert pan_tilt.calls == []
    assert base.calls == []


def test_motion_executor_reports_no_motion_required_for_centered_target() -> None:
    executor = TrackingMotionExecutor()
    plan = TrackingMotionPlan(
        has_target=True,
        target=None,
        pan_delta_degrees=0.0,
        tilt_delta_degrees=0.0,
        base_yaw_assist_required=False,
        reason="target_centered",
    )

    result = executor.execute(plan)

    assert result.status == "no_motion_required"
    assert result.would_move_pan_tilt is False
    assert result.would_request_base_yaw_assist is False
    assert result.pan_tilt_movement_executed is False
    assert result.base_movement_executed is False


def test_motion_executor_reports_no_target_without_movement() -> None:
    executor = TrackingMotionExecutor()
    plan = TrackingMotionPlan(
        has_target=False,
        target=None,
        reason="no_target",
    )

    result = executor.execute(plan)

    assert result.status == "no_target"
    assert result.has_target is False
    assert result.would_move_pan_tilt is False
    assert result.would_request_base_yaw_assist is False
    assert result.pan_tilt_movement_executed is False
    assert result.base_movement_executed is False


def test_motion_executor_rejects_missing_plan() -> None:
    executor = TrackingMotionExecutor()

    result = executor.execute(None)

    assert result.accepted is False
    assert result.status == "no_plan"
    assert result.reason == "no_plan"
    assert result.pan_tilt_movement_executed is False
    assert result.base_movement_executed is False
