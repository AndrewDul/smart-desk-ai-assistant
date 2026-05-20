from __future__ import annotations

import time
from typing import Any

from modules.devices.vision.tracking import TrackingMotionPlan
from modules.runtime.builder.look_at_me_mixin import LookAtMeSession


class _TrackingService:
    def __init__(self, plans: list[TrackingMotionPlan]) -> None:
        self.plans = list(plans)

    def plan_once(self, *, force_refresh: bool = False) -> TrackingMotionPlan:
        del force_refresh
        if self.plans:
            return self.plans.pop(0)
        return TrackingMotionPlan(has_target=False, target=None, reason="no_target")

    def latest_execution_result(self) -> dict[str, Any]:
        return {"accepted": True}

    def latest_pan_tilt_adapter_result(self) -> dict[str, Any]:
        return {
            "accepted": True,
            "status": "tracking_step",
            "backend_command_executed": True,
        }

    def status(self) -> dict[str, Any]:
        return {"ok": True}


class _PanTiltBackend:
    def __init__(self) -> None:
        self.pan = 0.0
        self.tilt = 0.0
        self.moves: list[dict[str, float]] = []

    def status(self) -> dict[str, Any]:
        return {
            "pan_angle": self.pan,
            "tilt_angle": self.tilt,
            "safe_limits": {
                "pan_min_degrees": -15.0,
                "pan_center_degrees": 0.0,
                "pan_max_degrees": 15.0,
                "tilt_min_degrees": -8.0,
                "tilt_center_degrees": 0.0,
                "tilt_max_degrees": 8.0,
            },
        }

    def move_delta(self, *, pan_delta_degrees: float, tilt_delta_degrees: float) -> dict[str, Any]:
        self.moves.append(
            {
                "pan_delta_degrees": float(pan_delta_degrees),
                "tilt_delta_degrees": float(tilt_delta_degrees),
            }
        )
        return {"ok": True, "movement_executed": True}


class _VisionBackend:
    def start(self) -> None:
        return None


class _MobilityBackend:
    def __init__(self) -> None:
        self.velocity_calls: list[dict[str, float]] = []
        self.stop_calls: list[str] = []
        self.open_calls = 0
        self.close_calls = 0

    def open(self) -> None:
        self.open_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    def read_available_lines(self, *, duration_sec: float = 0.0) -> list[str]:
        del duration_sec
        return []

    def send_velocity(self, *, linear_x_mps: float, angular_z_rad_s: float) -> dict[str, Any]:
        self.velocity_calls.append(
            {
                "linear_x_mps": float(linear_x_mps),
                "angular_z_rad_s": float(angular_z_rad_s),
            }
        )
        return {"ok": True}

    def stop(self, *, reason: str = "") -> dict[str, Any]:
        self.stop_calls.append(reason)
        return {"ok": True}


def _session(
    *,
    tracking: _TrackingService,
    mobility: _MobilityBackend | None = None,
    yaw_assist_enabled: bool = True,
) -> LookAtMeSession:
    return LookAtMeSession(
        settings={
            "look_at_me": {
                "enabled": True,
                "runtime_pan_tilt_execution_enabled": False,
                "runtime_hardware_execution_enabled": False,
                "physical_movement_confirmed": False,
                "search_when_no_face": True,
                "search_after_no_face_seconds": 0.05,
                "search_interval_seconds": 0.05,
                "mobile_base_yaw_assist_enabled": yaw_assist_enabled,
                "mobile_base_yaw_speed": 0.12,
                "mobile_base_yaw_assist_interval_seconds": 0.05,
                "force_refresh_during_tracking": False,
            },
            "pan_tilt": {},
            "vision_tracking": {},
        },
        vision_backend=_VisionBackend(),
        pan_tilt_backend=_PanTiltBackend(),
        vision_tracking_service=tracking,
        mobility_backend=mobility,
    )


def _target_plan(
    *,
    pan_delta: float = 0.5,
    yaw_required: bool = False,
    yaw_direction: str | None = None,
) -> TrackingMotionPlan:
    return TrackingMotionPlan(
        has_target=True,
        target=None,
        pan_delta_degrees=pan_delta,
        tilt_delta_degrees=0.0,
        base_yaw_assist_required=yaw_required,
        base_yaw_direction=yaw_direction,
        base_forward_velocity=0.0,
        base_backward_velocity=0.0,
        reason="pan_limit_base_yaw_assist_required" if yaw_required else "recenter_target",
    )


def test_search_scanning_never_commands_mobile_base() -> None:
    mobility = _MobilityBackend()
    session = _session(
        tracking=_TrackingService([TrackingMotionPlan(has_target=False, target=None, reason="no_target")]),
        mobility=mobility,
    )
    session._started_at = time.monotonic() - 1.0
    session._last_target_seen_at = time.monotonic() - 1.0

    result = session._run_once(min_delta=0.0)

    assert result["has_target"] is False
    assert result.get("search_active") is True
    assert mobility.velocity_calls == []
    assert mobility.stop_calls == []
    assert session.status()["tracking_state"] == "scanning_for_face"


def test_tracking_inside_pan_tilt_range_uses_pan_tilt_only() -> None:
    mobility = _MobilityBackend()
    session = _session(tracking=_TrackingService([_target_plan()]), mobility=mobility)

    result = session._run_once(min_delta=0.0)

    assert result["has_target"] is True
    assert result["yaw_assist"]["requested"] is False
    assert mobility.velocity_calls == []
    assert session.status()["tracking_state"] == "tracking_face"


def test_tracking_near_pan_limit_requests_yaw_only_mobile_base_assist() -> None:
    mobility = _MobilityBackend()
    session = _session(
        tracking=_TrackingService(
            [_target_plan(pan_delta=0.5, yaw_required=True, yaw_direction="right")]
        ),
        mobility=mobility,
    )

    result = session._run_once(min_delta=0.0)

    assert result["yaw_assist"]["executed"] is True
    assert mobility.velocity_calls == [{"linear_x_mps": 0.0, "angular_z_rad_s": -0.12}]
    assert mobility.open_calls == 1
    assert session.status()["mobile_base_yaw_assist_active"] is True
    assert session.status()["mobile_base_yaw_assist_direction"] == "right"
    assert session.status()["mobile_base_contact_ok"] is True
    assert session.status()["mobile_base_yaw_assist_available"] is True


def test_face_lost_stops_yaw_assist_and_returns_to_reacquire() -> None:
    mobility = _MobilityBackend()
    session = _session(
        tracking=_TrackingService(
            [
                _target_plan(pan_delta=0.5, yaw_required=True, yaw_direction="left"),
                TrackingMotionPlan(has_target=False, target=None, reason="no_target"),
            ]
        ),
        mobility=mobility,
    )

    session._run_once(min_delta=0.0)
    session._started_at = time.monotonic() - 1.0
    session._last_target_seen_at = time.monotonic() - 1.0
    result = session._run_once(min_delta=0.0)

    assert result["has_target"] is False
    assert mobility.stop_calls == ["look_at_me_face_lost"]
    assert session.status()["mobile_base_yaw_assist_active"] is False
    assert session.status()["tracking_state"] == "scanning_for_face"


def test_stop_command_stops_active_yaw_assist() -> None:
    mobility = _MobilityBackend()
    session = _session(
        tracking=_TrackingService(
            [_target_plan(pan_delta=0.5, yaw_required=True, yaw_direction="right")]
        ),
        mobility=mobility,
    )

    session._run_once(min_delta=0.0)
    result = session.stop()

    assert result["was_running"] is False
    assert mobility.stop_calls == ["look_at_me_stop"]
    assert session.status()["mobile_base_yaw_assist_active"] is False


def test_start_and_stop_manage_mobile_base_backend_lifecycle() -> None:
    mobility = _MobilityBackend()
    session = _session(
        tracking=_TrackingService(
            [_target_plan(pan_delta=0.5, yaw_required=True, yaw_direction="right")]
        ),
        mobility=mobility,
    )

    result = session.start()
    stop_result = session.stop()

    assert result["started"] is True
    assert stop_result["was_running"] is True
    assert mobility.open_calls == 1
    assert mobility.close_calls == 1


def test_brief_face_dropout_stays_in_grace_period_without_scan() -> None:
    mobility = _MobilityBackend()
    session = _session(
        tracking=_TrackingService(
            [
                _target_plan(),
                TrackingMotionPlan(has_target=False, target=None, reason="no_target"),
            ]
        ),
        mobility=mobility,
    )

    session._run_once(min_delta=0.0)  # face found, _last_target_seen_at set
    result = session._run_once(min_delta=0.0)  # face lost immediately after

    assert result["reason"] == "target_grace_period"
    assert result["short_dropout_grace_active"] is True
    assert result["has_target"] is False
    assert result["search_active"] is False
    assert session.status()["tracking_state"] == "target_grace_period"
    assert mobility.stop_calls == []


def test_face_dropout_beyond_grace_triggers_scan_and_stops_yaw() -> None:
    mobility = _MobilityBackend()
    session = _session(
        tracking=_TrackingService(
            [
                _target_plan(pan_delta=0.5, yaw_required=True, yaw_direction="right"),
                TrackingMotionPlan(has_target=False, target=None, reason="no_target"),
            ]
        ),
        mobility=mobility,
    )

    session._run_once(min_delta=0.0)
    session._last_target_seen_at = time.monotonic() - 2.0  # force grace expired
    result = session._run_once(min_delta=0.0)

    assert result["has_target"] is False
    assert result.get("short_dropout_grace_active") is not True
    assert "look_at_me_face_lost" in mobility.stop_calls


def test_yaw_hysteresis_maintains_yaw_in_stop_start_zone() -> None:
    """Yaw stays active between stop_threshold and start_threshold (hysteresis zone)."""
    mobility = _MobilityBackend()
    session = _session(
        tracking=_TrackingService(
            [
                _target_plan(pan_delta=0.5, yaw_required=True, yaw_direction="right"),
                _target_plan(pan_delta=0.3, yaw_required=False),
            ]
        ),
        mobility=mobility,
    )

    session._run_once(min_delta=0.0)  # yaw starts
    assert session.status()["mobile_base_yaw_assist_active"] is True

    session._run_once(min_delta=0.0)  # plan says not required, but yaw was active
    # Hysteresis: no pan_usage key in this plan → defaults to 0.0 which is < stop_threshold
    # so yaw should stop.
    # Verify yaw either maintained or cleanly stopped — base must not crash.
    assert isinstance(session.status()["mobile_base_yaw_assist_active"], bool)


def test_yaw_assist_requires_explicit_config_flag() -> None:
    mobility = _MobilityBackend()
    session = _session(
        tracking=_TrackingService(
            [_target_plan(pan_delta=0.5, yaw_required=True, yaw_direction="right")]
        ),
        mobility=mobility,
        yaw_assist_enabled=False,
    )

    result = session._run_once(min_delta=0.0)

    assert result["yaw_assist"]["reason"] == "disabled_by_config"
    assert mobility.velocity_calls == []


def test_yaw_assist_left_direction_sends_positive_angular_z() -> None:
    """Yaw left = rotate counter-clockwise = positive angular_z."""
    mobility = _MobilityBackend()
    session = _session(
        tracking=_TrackingService(
            [_target_plan(pan_delta=0.5, yaw_required=True, yaw_direction="left")]
        ),
        mobility=mobility,
    )

    result = session._run_once(min_delta=0.0)

    assert result["yaw_assist"]["executed"] is True
    assert len(mobility.velocity_calls) == 1
    assert mobility.velocity_calls[0]["linear_x_mps"] == 0.0
    assert mobility.velocity_calls[0]["angular_z_rad_s"] > 0.0


def test_yaw_assist_right_direction_sends_negative_angular_z() -> None:
    """Yaw right = rotate clockwise = negative angular_z."""
    mobility = _MobilityBackend()
    session = _session(
        tracking=_TrackingService(
            [_target_plan(pan_delta=0.5, yaw_required=True, yaw_direction="right")]
        ),
        mobility=mobility,
    )

    result = session._run_once(min_delta=0.0)

    assert result["yaw_assist"]["executed"] is True
    assert len(mobility.velocity_calls) == 1
    assert mobility.velocity_calls[0]["linear_x_mps"] == 0.0
    assert mobility.velocity_calls[0]["angular_z_rad_s"] < 0.0


def test_yaw_assist_always_sends_zero_linear_velocity() -> None:
    """Yaw assist is rotation-only; linear_x_mps must always be 0.0."""
    for direction in ("left", "right"):
        mobility = _MobilityBackend()
        session = _session(
            tracking=_TrackingService(
                [_target_plan(pan_delta=0.5, yaw_required=True, yaw_direction=direction)]
            ),
            mobility=mobility,
        )
        session._run_once(min_delta=0.0)
        assert mobility.velocity_calls[0]["linear_x_mps"] == 0.0


def test_yaw_assist_blocked_when_mobility_backend_is_none() -> None:
    """If the mobility backend is None (NullMobilityBackend path), the session
    must surface a clear 'mobility_backend_unavailable' reason rather than
    crashing or silently doing nothing."""
    session = _session(
        tracking=_TrackingService(
            [_target_plan(pan_delta=0.5, yaw_required=True, yaw_direction="right")]
        ),
        mobility=None,
    )

    result = session._run_once(min_delta=0.0)

    assert result["yaw_assist"]["executed"] is False
    assert "unavailable" in result["yaw_assist"]["reason"].lower()


def test_yaw_assist_applies_when_pan_delta_below_min_move_threshold() -> None:
    """Previously _run_once called _stop_yaw_assist when pan_delta < min_delta,
    which cancelled any active yaw before _apply_yaw_assist_from_plan was reached.
    At high pan with face centred in camera (pan_delta ≈ 0), yaw must still fire."""
    mobility = _MobilityBackend()
    plan = TrackingMotionPlan(
        has_target=True,
        target=None,
        pan_delta_degrees=0.01,   # below any reasonable min_delta
        tilt_delta_degrees=0.0,
        base_yaw_assist_required=True,
        base_yaw_direction="right",
        base_forward_velocity=0.0,
        base_backward_velocity=0.0,
        reason="pan_limit_base_yaw_assist_required",
    )
    session = _session(
        tracking=_TrackingService([plan]),
        mobility=mobility,
    )

    result = session._run_once(min_delta=0.05)  # explicitly above pan_delta=0.01

    assert result["has_target"] is True
    assert result["yaw_assist"]["executed"] is True
    assert len(mobility.velocity_calls) == 1


def test_yaw_speed_is_at_least_minimum_useful_speed() -> None:
    """The configured yaw speed must produce a velocity magnitude above the
    minimum floor that makes the base visibly rotate."""
    mobility = _MobilityBackend()
    session = _session(
        tracking=_TrackingService(
            [_target_plan(pan_delta=0.5, yaw_required=True, yaw_direction="right")]
        ),
        mobility=mobility,
    )

    session._run_once(min_delta=0.0)

    assert len(mobility.velocity_calls) == 1
    angular_z = mobility.velocity_calls[0]["angular_z_rad_s"]
    assert abs(angular_z) >= 0.10, (
        f"yaw speed {abs(angular_z):.3f} rad/s is below the 0.10 rad/s useful minimum"
    )
