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



def test_policy_requires_stable_target_hits_before_movement() -> None:
    policy = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(target_activation_hits=2, max_target_jump_norm=0.3)
    )
    limits = TrackingSafeLimits(pan_min_degrees=-20.0, pan_max_degrees=20.0)
    target = TrackingTarget(
        target_type="face",
        confidence=0.9,
        box={"x": 80, "y": 60, "width": 50, "height": 50},
        center_x_norm=0.7,
        center_y_norm=0.5,
        area_norm=0.05,
        source_index=0,
    )

    first = policy.plan_for_target(
        target,
        current_pan_degrees=0.0,
        current_tilt_degrees=0.0,
        safe_limits=limits,
    )
    second = policy.plan_for_target(
        target,
        current_pan_degrees=0.0,
        current_tilt_degrees=0.0,
        safe_limits=limits,
    )

    assert first.has_target is False
    assert first.reason == "target_waiting_for_stability"
    assert second.has_target is True
    assert second.reason == "recenter_target"
    assert second.pan_delta_degrees > 0.0


def test_policy_smooths_locked_target_before_planning_delta() -> None:
    policy = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(
            target_activation_hits=1,
            target_smoothing_alpha=0.5,
            max_target_jump_norm=0.5,
        )
    )
    limits = TrackingSafeLimits(pan_min_degrees=-20.0, pan_max_degrees=20.0)
    first_target = TrackingTarget(
        target_type="face",
        confidence=0.9,
        box={"x": 80, "y": 60, "width": 50, "height": 50},
        center_x_norm=0.6,
        center_y_norm=0.5,
        area_norm=0.05,
        source_index=0,
    )
    second_target = TrackingTarget(
        target_type="face",
        confidence=0.9,
        box={"x": 100, "y": 60, "width": 50, "height": 50},
        center_x_norm=0.8,
        center_y_norm=0.5,
        area_norm=0.05,
        source_index=0,
    )

    policy.plan_for_target(
        first_target,
        current_pan_degrees=0.0,
        current_tilt_degrees=0.0,
        safe_limits=limits,
    )
    plan = policy.plan_for_target(
        second_target,
        current_pan_degrees=0.0,
        current_tilt_degrees=0.0,
        safe_limits=limits,
    )

    assert plan.has_target is True
    assert plan.target is not None
    assert round(plan.target.center_x_norm, 2) == 0.7


def test_policy_clamps_tracking_tilt_to_center_when_face_is_lower() -> None:
    policy = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(
            dead_zone_y=0.02,
            tilt_gain_degrees=12.0,
            max_step_degrees=3.0,
            no_tilt_below_center=True,
        )
    )

    plan = policy.plan_for_target(
        _target(center_x=0.5, center_y=0.85),
        current_pan_degrees=0.0,
        current_tilt_degrees=0.0,
        safe_limits=TrackingSafeLimits(
            tilt_min_degrees=-12.0,
            tilt_center_degrees=0.0,
            tilt_max_degrees=80.0,
        ),
    )

    assert plan.tilt_delta_degrees == 0.0
    assert plan.clamped_tilt_degrees == 0.0
    assert plan.diagnostics["tilt_clamped_to_center"] is True
    assert plan.diagnostics["tilt_blocked_by_no_down_rule"] is True
    assert plan.diagnostics["no_tilt_below_center"] is True


def test_policy_allows_tracking_tilt_up_from_center() -> None:
    policy = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(
            dead_zone_y=0.02,
            tilt_gain_degrees=12.0,
            max_step_degrees=3.0,
            no_tilt_below_center=True,
        )
    )

    plan = policy.plan_for_target(
        _target(center_x=0.5, center_y=0.15),
        current_pan_degrees=0.0,
        current_tilt_degrees=0.0,
        safe_limits=TrackingSafeLimits(
            tilt_min_degrees=-12.0,
            tilt_center_degrees=0.0,
            tilt_max_degrees=80.0,
        ),
    )

    assert plan.tilt_delta_degrees > 0.0
    assert plan.clamped_tilt_degrees >= 0.0
    assert plan.diagnostics["tilt_clamped_to_center"] is False
    assert plan.diagnostics["tilt_blocked_by_no_down_rule"] is False


def test_policy_blocks_negative_tilt_delta_when_current_tilt_is_above_center() -> None:
    """Live failure case: current_tilt=14.335, face at center_y=0.614, raw_delta=-2.06.

    The old Codex implementation clamped only the absolute desired position to [center, max].
    Since desired_tilt (13.135) is still above center (0.0), no clamp triggered and delta=-1.2
    was sent to hardware. This test would have FAILED with the live evidence. The fix blocks
    any negative tilt delta when no_tilt_below_center=True.
    """
    policy = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(
            dead_zone_y=0.025,
            tilt_gain_degrees=18.0,
            max_step_degrees=1.2,
            no_tilt_below_center=True,
        )
    )

    plan = policy.plan_for_target(
        _target(center_x=0.49, center_y=0.614),
        current_pan_degrees=-22.793,
        current_tilt_degrees=14.335,
        safe_limits=TrackingSafeLimits(
            tilt_min_degrees=-12.0,
            tilt_center_degrees=0.0,
            tilt_max_degrees=80.0,
        ),
    )

    assert plan.tilt_delta_degrees == 0.0, (
        f"Expected zero tilt delta (blocked), got {plan.tilt_delta_degrees}"
    )
    assert plan.diagnostics["tilt_blocked_by_no_down_rule"] is True
    assert plan.diagnostics["tilt_clamped_to_center"] is True
    assert plan.diagnostics["raw_tilt_delta_degrees"] < 0.0


def test_policy_yaw_assist_triggers_at_60_percent_pan_usage() -> None:
    limits = TrackingSafeLimits(
        pan_min_degrees=-90.0,
        pan_center_degrees=0.0,
        pan_max_degrees=90.0,
    )
    policy = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(
            dead_zone_x=0.02,
            yaw_assist_pan_usage_start=0.60,
        )
    )

    plan_at_60 = policy.plan_for_target(
        _target(center_x=0.55),
        current_pan_degrees=54.0,
        current_tilt_degrees=0.0,
        safe_limits=limits,
    )
    assert plan_at_60.base_yaw_assist_required is True
    assert plan_at_60.diagnostics["pan_usage"] >= 0.60

    policy2 = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(
            dead_zone_x=0.02,
            yaw_assist_pan_usage_start=0.60,
        )
    )
    plan_below_60 = policy2.plan_for_target(
        _target(center_x=0.55),
        current_pan_degrees=53.0,
        current_tilt_degrees=0.0,
        safe_limits=limits,
    )
    assert plan_below_60.base_yaw_assist_required is False
    assert plan_below_60.diagnostics["pan_usage"] < 0.60


def test_policy_yaw_assist_required_at_high_pan_even_when_face_is_centered() -> None:
    """At high pan usage, yaw assist must fire even when the face happens to be
    centred in the camera frame.  Previously this was blocked by the dead_zone_x
    check; at ≥ 60 % pan the base must continue rotating regardless of offset_x."""
    limits = TrackingSafeLimits(pan_min_degrees=-90.0, pan_max_degrees=90.0)
    policy = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(
            dead_zone_x=0.05,
            yaw_assist_pan_usage_start=0.60,
        )
    )

    plan = policy.plan_for_target(
        _target(center_x=0.5),  # face is exactly centred — pan_usage = 60/90 = 0.667
        current_pan_degrees=60.0,
        current_tilt_degrees=0.0,
        safe_limits=limits,
    )

    assert plan.base_yaw_assist_required is True
    assert plan.base_yaw_direction == "right"  # pan_error = +60 → pan_sign direction
    assert plan.diagnostics["yaw_direction_source"] == "pan_sign_at_high_usage"


def test_policy_yaw_assist_uses_face_offset_direction_when_face_is_off_center_at_high_pan() -> None:
    """When pan is high AND face is off-center, direction should come from the face,
    not from the pan sign."""
    limits = TrackingSafeLimits(pan_min_degrees=-90.0, pan_max_degrees=90.0)
    policy = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(
            dead_zone_x=0.05,
            yaw_assist_pan_usage_start=0.60,
        )
    )

    plan = policy.plan_for_target(
        _target(center_x=0.3),  # face is left of center
        current_pan_degrees=60.0,  # pan is rightward
        current_tilt_degrees=0.0,
        safe_limits=limits,
    )

    assert plan.base_yaw_assist_required is True
    assert plan.base_yaw_direction == "left"  # face offset wins
    assert plan.diagnostics["yaw_direction_source"] == "face_offset"


def test_policy_yaw_assist_not_triggered_below_pan_usage_threshold() -> None:
    """Yaw assist must not fire when pan usage is below the start threshold,
    regardless of face position."""
    limits = TrackingSafeLimits(pan_min_degrees=-90.0, pan_max_degrees=90.0)
    policy = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(
            dead_zone_x=0.05,
            yaw_assist_pan_usage_start=0.60,
        )
    )

    plan = policy.plan_for_target(
        _target(center_x=0.9),  # face far off-center
        current_pan_degrees=50.0,  # pan_usage = 50/90 = 0.556 < 0.60
        current_tilt_degrees=0.0,
        safe_limits=limits,
    )

    assert plan.base_yaw_assist_required is False
    assert plan.base_yaw_direction is None
    assert plan.diagnostics["yaw_direction_source"] == "none"


def test_policy_default_yaw_assist_triggers_at_50_percent_pan_usage() -> None:
    """Default yaw_assist_pan_usage_start is 0.50 (≈ 45° on a ±90° range)."""
    limits = TrackingSafeLimits(
        pan_min_degrees=-90.0,
        pan_center_degrees=0.0,
        pan_max_degrees=90.0,
    )
    policy = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(dead_zone_x=0.02)
    )

    plan_at_50 = policy.plan_for_target(
        _target(center_x=0.55),
        current_pan_degrees=45.0,
        current_tilt_degrees=0.0,
        safe_limits=limits,
    )
    assert plan_at_50.base_yaw_assist_required is True
    assert plan_at_50.diagnostics["yaw_assist_pan_usage_start_threshold"] == 0.50

    plan_below_50 = policy.plan_for_target(
        _target(center_x=0.55),
        current_pan_degrees=44.0,
        current_tilt_degrees=0.0,
        safe_limits=limits,
    )
    assert plan_below_50.base_yaw_assist_required is False
    assert plan_below_50.diagnostics["pan_usage"] < 0.50


def test_policy_yaw_assist_fires_left_and_right() -> None:
    """base_yaw_direction must match which side the face is on."""
    limits = TrackingSafeLimits(
        pan_min_degrees=-90.0,
        pan_center_degrees=0.0,
        pan_max_degrees=90.0,
    )
    policy_left = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(dead_zone_x=0.02, yaw_assist_pan_usage_start=0.50)
    )
    policy_right = PanTiltTrackingPolicy(
        config=TrackingPolicyConfig(dead_zone_x=0.02, yaw_assist_pan_usage_start=0.50)
    )

    # Face is left of center (center_x < 0.5) at high left pan
    plan_left = policy_left.plan_for_target(
        _target(center_x=0.30),
        current_pan_degrees=-46.0,
        current_tilt_degrees=0.0,
        safe_limits=limits,
    )
    assert plan_left.base_yaw_assist_required is True
    assert plan_left.base_yaw_direction == "left"

    # Face is right of center at high right pan
    plan_right = policy_right.plan_for_target(
        _target(center_x=0.70),
        current_pan_degrees=46.0,
        current_tilt_degrees=0.0,
        safe_limits=limits,
    )
    assert plan_right.base_yaw_assist_required is True
    assert plan_right.base_yaw_direction == "right"
