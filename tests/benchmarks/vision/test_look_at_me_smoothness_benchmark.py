from __future__ import annotations

from modules.devices.vision.tracking.motion_executor import TrackingMotionExecutionResult
from modules.devices.vision.tracking.pan_tilt_execution_adapter import PanTiltExecutionAdapter


class _RecordingPanTiltBackend:
    def __init__(self) -> None:
        self.moves: list[tuple[float, float]] = []

    def move_delta(self, *, pan_delta_degrees: float, tilt_delta_degrees: float) -> dict[str, object]:
        self.moves.append((float(pan_delta_degrees), float(tilt_delta_degrees)))
        return {"ok": True, "movement_executed": True}


def _execution(*, pan_delta: float, tilt_delta: float = 0.0) -> TrackingMotionExecutionResult:
    return TrackingMotionExecutionResult(
        accepted=True,
        dry_run=False,
        has_target=True,
        would_move_pan_tilt=True,
        pan_delta_degrees=pan_delta,
        tilt_delta_degrees=tilt_delta,
        reason="recenter_target",
    )


def _stop_start_pattern_count(values: list[float]) -> int:
    return sum(
        1
        for left, center, right in zip(values, values[1:], values[2:])
        if abs(left) > 1e-6 and abs(center) <= 1e-6 and abs(right) > 1e-6
    )


def _direction_flip_count(values: list[float]) -> int:
    signs = [1 if value > 1e-6 else -1 if value < -1e-6 else 0 for value in values]
    nonzero = [sign for sign in signs if sign != 0]
    return sum(1 for left, right in zip(nonzero, nonzero[1:]) if left != right)


def test_look_at_me_command_generation_smoothness_benchmark() -> None:
    backend = _RecordingPanTiltBackend()
    adapter = PanTiltExecutionAdapter(
        pan_tilt_backend=backend,
        config={
            "dry_run": False,
            "backend_command_execution_enabled": True,
            "runtime_hardware_execution_enabled": True,
            "physical_movement_confirmed": True,
            "max_allowed_pan_delta_degrees": 1.2,
            "max_allowed_tilt_delta_degrees": 1.2,
            "smooth_follow_enabled": True,
            "smooth_follow_alpha": 0.62,
            "smooth_follow_lead_gain": 2.0,
            "smooth_follow_min_live_step_degrees": 0.28,
            "smooth_follow_command_interval_seconds": 0.0,
        },
    )

    simulated_target_pan_deltas = [
        0.30,
        0.34,
        0.38,
        0.44,
        0.50,
        0.56,
        0.62,
        0.68,
        0.72,
        0.76,
    ]
    for pan_delta in simulated_target_pan_deltas:
        adapter.prepare(_execution(pan_delta=pan_delta))

    pan_commands = [pan for pan, _tilt in backend.moves]
    zero_count = sum(1 for value in pan_commands if abs(value) <= 1e-6)
    nonzero_count = len(pan_commands) - zero_count
    delta_changes = [abs(right - left) for left, right in zip(pan_commands, pan_commands[1:])]
    metrics = {
        "command_count": len(pan_commands),
        "nonzero_command_ratio": nonzero_count / max(1, len(pan_commands)),
        "zero_command_ratio": zero_count / max(1, len(pan_commands)),
        "stop_start_pattern_count": _stop_start_pattern_count(pan_commands),
        "max_pan_delta_change": max(delta_changes) if delta_changes else 0.0,
        "max_tilt_delta_change": 0.0,
        "direction_flip_count": _direction_flip_count(pan_commands),
        "average_command_interval_target_seconds": 0.016,
        "smooth_enough": True,
    }

    assert metrics["command_count"] == len(simulated_target_pan_deltas), metrics
    assert metrics["nonzero_command_ratio"] >= 0.95, metrics
    assert metrics["zero_command_ratio"] <= 0.05, metrics
    assert metrics["stop_start_pattern_count"] == 0, metrics
    assert metrics["max_pan_delta_change"] <= 0.55, metrics
    assert metrics["direction_flip_count"] == 0, metrics
