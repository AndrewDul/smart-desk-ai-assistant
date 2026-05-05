from __future__ import annotations

from modules.runtime.contracts import VisionObservation

from .models import TrackingMotionPlan, TrackingPolicyConfig, TrackingSafeLimits, TrackingTarget
from .target_selector import TrackingTargetSelector


def _clamp_step(value: float, max_step: float) -> float:
    if value > max_step:
        return max_step
    if value < -max_step:
        return -max_step
    return value


class PanTiltTrackingPolicy:
    """
    Convert a selected face/person target into a safe pan/tilt dry-run movement plan.

    The policy is intentionally pure and non-blocking: it does not read frames,
    does not run inference, never talks to hardware, and only marks required
    yaw-only base assist when pan-tilt reaches or approaches its pan limit.
    """

    def __init__(
        self,
        *,
        config: TrackingPolicyConfig | None = None,
        selector: TrackingTargetSelector | None = None,
    ) -> None:
        self._config = config or TrackingPolicyConfig()
        self._selector = selector or TrackingTargetSelector()

    def plan_from_observation(
        self,
        observation: VisionObservation | None,
        *,
        current_pan_degrees: float,
        current_tilt_degrees: float,
        safe_limits: TrackingSafeLimits,
    ) -> TrackingMotionPlan:
        target = self._selector.select(observation)
        return self.plan_for_target(
            target,
            current_pan_degrees=current_pan_degrees,
            current_tilt_degrees=current_tilt_degrees,
            safe_limits=safe_limits,
        )

    def plan_for_target(
        self,
        target: TrackingTarget | None,
        *,
        current_pan_degrees: float,
        current_tilt_degrees: float,
        safe_limits: TrackingSafeLimits,
    ) -> TrackingMotionPlan:
        if not self._config.enabled:
            return TrackingMotionPlan(
                has_target=target is not None,
                target=target,
                desired_pan_degrees=float(current_pan_degrees),
                desired_tilt_degrees=float(current_tilt_degrees),
                clamped_pan_degrees=safe_limits.clamp_pan(current_pan_degrees),
                clamped_tilt_degrees=safe_limits.clamp_tilt(current_tilt_degrees),
                reason="tracking_disabled",
            )

        if target is None:
            return TrackingMotionPlan(
                has_target=False,
                target=None,
                desired_pan_degrees=float(current_pan_degrees),
                desired_tilt_degrees=float(current_tilt_degrees),
                clamped_pan_degrees=safe_limits.clamp_pan(current_pan_degrees),
                clamped_tilt_degrees=safe_limits.clamp_tilt(current_tilt_degrees),
                reason="no_target",
            )

        offset_x = target.center_x_norm - 0.5
        offset_y = target.center_y_norm - 0.5

        raw_pan_delta = 0.0
        raw_tilt_delta = 0.0
        if abs(offset_x) > self._config.dead_zone_x:
            raw_pan_delta = offset_x * self._config.pan_gain_degrees
        if abs(offset_y) > self._config.dead_zone_y:
            raw_tilt_delta = -offset_y * self._config.tilt_gain_degrees

        pan_delta = _clamp_step(raw_pan_delta, self._config.max_step_degrees)
        tilt_delta = _clamp_step(raw_tilt_delta, self._config.max_step_degrees)

        desired_pan = float(current_pan_degrees) + pan_delta
        desired_tilt = float(current_tilt_degrees) + tilt_delta
        clamped_pan = safe_limits.clamp_pan(desired_pan)
        clamped_tilt = safe_limits.clamp_tilt(desired_tilt)

        pan_at_limit = abs(clamped_pan - desired_pan) > 1e-6 or _near_pan_limit(
            clamped_pan,
            safe_limits,
            self._config.limit_margin_degrees,
        )
        tilt_at_limit = abs(clamped_tilt - desired_tilt) > 1e-6 or _near_tilt_limit(
            clamped_tilt,
            safe_limits,
            self._config.limit_margin_degrees,
        )

        base_yaw_assist_required = bool(
            pan_at_limit and abs(offset_x) >= self._config.base_yaw_assist_edge_threshold
        )
        base_yaw_direction = (
            _base_yaw_direction_from_offset(offset_x)
            if base_yaw_assist_required
            else None
        )

        reason = "target_centered"
        if abs(pan_delta) > 0.0 or abs(tilt_delta) > 0.0:
            reason = "recenter_target"
        if base_yaw_assist_required:
            reason = "pan_limit_base_yaw_assist_required"

        return TrackingMotionPlan(
            has_target=True,
            target=target,
            pan_delta_degrees=round(clamped_pan - float(current_pan_degrees), 4),
            tilt_delta_degrees=round(clamped_tilt - float(current_tilt_degrees), 4),
            desired_pan_degrees=round(desired_pan, 4),
            desired_tilt_degrees=round(desired_tilt, 4),
            clamped_pan_degrees=round(clamped_pan, 4),
            clamped_tilt_degrees=round(clamped_tilt, 4),
            pan_at_limit=pan_at_limit,
            tilt_at_limit=tilt_at_limit,
            base_yaw_assist_required=base_yaw_assist_required,
            base_yaw_direction=base_yaw_direction,
            base_forward_velocity=0.0,
            base_backward_velocity=0.0,
            mobile_assist_recommended=base_yaw_assist_required,
            reason=reason,
            diagnostics={
                "offset_x": round(offset_x, 4),
                "offset_y": round(offset_y, 4),
                "raw_pan_delta_degrees": round(raw_pan_delta, 4),
                "raw_tilt_delta_degrees": round(raw_tilt_delta, 4),
                "dead_zone_x": self._config.dead_zone_x,
                "dead_zone_y": self._config.dead_zone_y,
                "base_yaw_assist_edge_threshold": self._config.base_yaw_assist_edge_threshold,
            },
        )


def _base_yaw_direction_from_offset(offset_x: float) -> str:
    return "right" if offset_x > 0.0 else "left"


def _near_pan_limit(value: float, limits: TrackingSafeLimits, margin: float) -> bool:
    return value <= limits.pan_min_degrees + margin or value >= limits.pan_max_degrees - margin


def _near_tilt_limit(value: float, limits: TrackingSafeLimits, margin: float) -> bool:
    return value <= limits.tilt_min_degrees + margin or value >= limits.tilt_max_degrees - margin
