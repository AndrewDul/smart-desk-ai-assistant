from __future__ import annotations

from modules.devices.vision.tracking import (
    PanTiltTrackingPolicy,
    TrackingPolicyConfig,
    TrackingSafeLimits,
    TrackingTarget,
)


def _target(center_x: float, center_y: float = 0.5) -> TrackingTarget:
    return TrackingTarget(
        target_type="face",
        confidence=0.9,
        box={"left": 0, "top": 0, "right": 100, "bottom": 100},
        center_x_norm=center_x,
        center_y_norm=center_y,
        area_norm=0.05,
        source_index=0,
    )


def test_policy_does_not_move_when_target_is_inside_dead_zone() -> None:
    policy = PanTiltTrackingPolicy(config=TrackingPolicyConfig(dead_zone_x=0.08, dead_zone_y=0.10))

    plan = policy.plan_for_target(
        _target(center_x=0.53, center_y=0.55),
        current_pan_degrees=0.0,
        current_tilt_degrees=0.0,
        safe_limits=TrackingSafeLimits(),
    )

    assert plan.has_target is True
    assert plan.movement_requested() is False
    assert plan.reason == "target_centered"


def test_policy_plans_small_clamped_pan_step_for_target_on_right() -> None:
    policy = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(dead_zone_x=0.05, pan_gain_degrees=12.0, max_step_degrees=2.0)
    )

    plan = policy.plan_for_target(
        _target(center_x=0.80),
        current_pan_degrees=0.0,
        current_tilt_degrees=0.0,
        safe_limits=TrackingSafeLimits(),
    )

    assert plan.pan_delta_degrees == 2.0
    assert plan.tilt_delta_degrees == 0.0
    assert plan.clamped_pan_degrees == 2.0
    assert plan.reason == "recenter_target"


def test_policy_clamps_to_safe_limit_and_requires_base_yaw_assist_at_edge() -> None:
    policy = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(
            dead_zone_x=0.05,
            pan_gain_degrees=12.0,
            max_step_degrees=2.0,
            limit_margin_degrees=1.0,
            base_yaw_assist_edge_threshold=0.40,
        )
    )

    plan = policy.plan_for_target(
        _target(center_x=0.95),
        current_pan_degrees=14.5,
        current_tilt_degrees=0.0,
        safe_limits=TrackingSafeLimits(pan_min_degrees=-15.0, pan_max_degrees=15.0),
    )

    assert plan.pan_delta_degrees == 0.5
    assert plan.clamped_pan_degrees == 15.0
    assert plan.pan_at_limit is True
    assert plan.base_yaw_assist_required is True
    assert plan.base_yaw_direction == "right"
    assert plan.base_forward_velocity == 0.0
    assert plan.base_backward_velocity == 0.0
    assert plan.mobile_assist_recommended is True
    assert plan.reason == "pan_limit_base_yaw_assist_required"


def test_policy_accepts_legacy_mobile_assist_threshold_name_temporarily() -> None:
    policy = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(
            mobile_assist_edge_threshold=0.40,
            limit_margin_degrees=1.0,
        )
    )

    plan = policy.plan_for_target(
        _target(center_x=0.95),
        current_pan_degrees=14.5,
        current_tilt_degrees=0.0,
        safe_limits=TrackingSafeLimits(pan_min_degrees=-15.0, pan_max_degrees=15.0),
    )

    assert plan.base_yaw_assist_required is True
    assert plan.mobile_assist_recommended is True


def test_disabled_policy_returns_no_motion_plan() -> None:
    policy = PanTiltTrackingPolicy(config=TrackingPolicyConfig(enabled=False))

    plan = policy.plan_for_target(
        _target(center_x=0.95),
        current_pan_degrees=3.0,
        current_tilt_degrees=-1.0,
        safe_limits=TrackingSafeLimits(),
    )

    assert plan.has_target is True
    assert plan.movement_requested() is False
    assert plan.reason == "tracking_disabled"
