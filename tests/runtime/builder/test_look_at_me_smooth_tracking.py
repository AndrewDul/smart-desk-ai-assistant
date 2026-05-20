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
    count = 0
    for left, center, right in zip(values, values[1:], values[2:]):
        if abs(left) > 1e-6 and abs(center) <= 1e-6 and abs(right) > 1e-6:
            count += 1
    return count


def test_smooth_tracking_stream_does_not_emit_nonzero_zero_nonzero_pattern() -> None:
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

    for pan_delta in [0.30, 0.35, 0.42, 0.50, 0.58, 0.64, 0.70]:
        result = adapter.prepare(_execution(pan_delta=pan_delta))
        assert result.backend_command_executed is True

    pan_commands = [pan for pan, _tilt in backend.moves]
    assert len(pan_commands) == 7
    assert all(pan > 0.0 for pan in pan_commands)
    assert _stop_start_pattern_count(pan_commands) == 0

    delta_changes = [abs(right - left) for left, right in zip(pan_commands, pan_commands[1:])]
    assert max(delta_changes) <= 0.55


def test_smooth_tracking_stream_does_not_flip_direction_without_target_crossing_center() -> None:
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
            "smooth_follow_command_interval_seconds": 0.0,
        },
    )

    for pan_delta in [0.8, 0.7, 0.6, 0.5, 0.4]:
        adapter.prepare(_execution(pan_delta=pan_delta))

    assert all(pan > 0.0 for pan, _tilt in backend.moves)


def _no_motion_execution() -> TrackingMotionExecutionResult:
    return TrackingMotionExecutionResult(
        accepted=True,
        dry_run=False,
        has_target=True,
        would_move_pan_tilt=False,
        pan_delta_degrees=0.0,
        tilt_delta_degrees=0.0,
        reason="target_centered",
    )


def test_smooth_state_decays_when_face_centered_not_resets_to_zero() -> None:
    """When plan says centered (would_move_pan_tilt=False) but has_target=True,
    the smooth-follow state must decay via EWM rather than hard-reset to zero.
    A hard reset is the primary stop-start cause: the next off-center frame
    restarts from zero and produces a single choppy micro-step."""
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
            "smooth_follow_alpha": 0.72,
            "smooth_follow_lead_gain": 2.0,
            "smooth_follow_min_live_step_degrees": 0.28,
            "smooth_follow_command_interval_seconds": 0.0,
        },
    )

    # Prime the smooth state with several off-center frames.
    for _ in range(4):
        adapter.prepare(_execution(pan_delta=0.8))

    state_after_tracking = adapter._smooth_pan_delta_degrees
    assert abs(state_after_tracking) > 0.3, "smooth state must be non-trivial before centered frame"

    # Simulate one "centered" frame (plan says no motion, face still visible).
    adapter.prepare(_no_motion_execution())

    state_after_centered = adapter._smooth_pan_delta_degrees
    # Must decay, not zero.
    assert abs(state_after_centered) > 1e-6, (
        "smooth state must not be hard-reset to zero when face is still visible"
    )
    # Must have decayed by approximately (1 - alpha).
    expected_decay = abs(state_after_tracking) * (1.0 - 0.72)
    assert abs(state_after_centered - expected_decay) < 0.02


def test_smooth_state_decays_on_no_target_not_resets_to_zero() -> None:
    """When has_target=False (no new camera frame) the smooth state must decay via
    EWM rather than hard-reset to zero.

    At 15 fps with a 25 ms tracking loop, roughly 2 of every 3 iterations have
    no new frame, producing has_target=False.  A hard reset every frameless
    iteration zeroes momentum just before the next live frame arrives, causing a
    fresh zero-start step each time — the classic move→stop→move stutter.

    With decay the head decelerates naturally; after ~5 no-target cycles the
    value is effectively zero, so truly-lost faces still clean up in ~125 ms."""
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
            "smooth_follow_alpha": 0.62,
            "smooth_follow_command_interval_seconds": 0.0,
        },
    )

    for _ in range(3):
        adapter.prepare(_execution(pan_delta=1.0))

    state_before = adapter._smooth_pan_delta_degrees
    assert abs(state_before) > 0.1, "smooth state must be non-trivial before face-lost frame"

    no_face = TrackingMotionExecutionResult(
        accepted=True,
        dry_run=False,
        has_target=False,
        would_move_pan_tilt=False,
        reason="no_target",
    )
    adapter.prepare(no_face)

    state_after = adapter._smooth_pan_delta_degrees
    # Must have decayed — not zeroed.
    assert abs(state_after) > 1e-6, (
        "smooth state must not be hard-reset to zero on a frameless (no_target) iteration"
    )
    expected = abs(state_before) * (1.0 - 0.62)
    assert abs(abs(state_after) - expected) < 0.02

    # After many no-target frames the state converges to near-zero naturally.
    for _ in range(20):
        adapter.prepare(no_face)
    assert abs(adapter._smooth_pan_delta_degrees) < 0.001
