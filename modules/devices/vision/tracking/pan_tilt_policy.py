from __future__ import annotations

from dataclasses import replace

from modules.runtime.contracts import VisionObservation

from .models import TrackingMotionPlan, TrackingPolicyConfig, TrackingSafeLimits, TrackingTarget
from .target_selector import TrackingTargetSelector


def _clamp_step(value: float, max_step: float) -> float:
    if value > max_step:
        return max_step
    if value < -max_step:
        return -max_step
    return value


def _target_distance(first: TrackingTarget, second: TrackingTarget) -> float:
    return abs(first.center_x_norm - second.center_x_norm) + abs(
        first.center_y_norm - second.center_y_norm
    )


class PanTiltTrackingPolicy:
    """
    Convert a selected face/person target into a safe pan/tilt movement plan.

    The policy stays non-blocking and never talks to hardware. It also keeps a
    small in-memory target lock so one-frame Haar false positives do not jerk
    the pan/tilt head away from the real user.
    """

    def __init__(
        self,
        *,
        config: TrackingPolicyConfig | None = None,
        selector: TrackingTargetSelector | None = None,
    ) -> None:
        self._config = config or TrackingPolicyConfig()
        self._selector = selector or TrackingTargetSelector()
        self._locked_target: TrackingTarget | None = None
        self._candidate_target: TrackingTarget | None = None
        self._candidate_hits = 0

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

        stable_target, stable_reason, stable_diagnostics = self._stabilize_target(target)
        if stable_target is None:
            return TrackingMotionPlan(
                has_target=False,
                target=None,
                desired_pan_degrees=float(current_pan_degrees),
                desired_tilt_degrees=float(current_tilt_degrees),
                clamped_pan_degrees=safe_limits.clamp_pan(current_pan_degrees),
                clamped_tilt_degrees=safe_limits.clamp_tilt(current_tilt_degrees),
                reason=stable_reason,
                diagnostics=stable_diagnostics,
            )

        offset_x = stable_target.center_x_norm - 0.5
        offset_y = stable_target.center_y_norm - 0.5

        raw_pan_delta = 0.0
        raw_tilt_delta = 0.0
        if abs(offset_x) > self._config.dead_zone_x:
            raw_pan_delta = offset_x * self._config.pan_gain_degrees
        if abs(offset_y) > self._config.dead_zone_y:
            raw_tilt_delta = -offset_y * self._config.tilt_gain_degrees

        pan_delta = _clamp_step(raw_pan_delta, self._config.max_step_degrees)
        tilt_delta = _clamp_step(raw_tilt_delta, self._config.max_step_degrees)

        # Block any downward tilt correction when no_tilt_below_center is enabled.
        # This applies regardless of current position — even returning from above center
        # is blocked during active look-at-me tracking (camera should only look up).
        tilt_blocked_by_no_down = False
        if self._config.no_tilt_below_center and tilt_delta < 0.0:
            tilt_blocked_by_no_down = True
            tilt_delta = 0.0

        desired_pan = float(current_pan_degrees) + pan_delta
        desired_tilt = float(current_tilt_degrees) + tilt_delta
        clamped_pan = safe_limits.clamp_pan(desired_pan)
        if self._config.no_tilt_below_center:
            clamped_tilt = safe_limits.clamp_tilt_not_below_center(desired_tilt)
        else:
            clamped_tilt = safe_limits.clamp_tilt(desired_tilt)
        tilt_clamped_to_center = bool(
            self._config.no_tilt_below_center
            and (tilt_blocked_by_no_down or desired_tilt < safe_limits.tilt_center_degrees)
        )

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

        # Pan usage as fraction of usable range from center (0.0 = center, 1.0 = hard limit).
        pan_half_range = max(
            abs(safe_limits.pan_max_degrees - safe_limits.pan_center_degrees),
            abs(safe_limits.pan_center_degrees - safe_limits.pan_min_degrees),
            1e-6,
        )
        pan_usage = min(
            1.0,
            abs(float(current_pan_degrees) - safe_limits.pan_center_degrees) / pan_half_range,
        )

        # Yaw assist is eligible when pan usage reaches the start threshold.
        # Direction uses face offset when the face is off-center; when the face sits
        # in the dead zone (camera already pointing at the user but head is angled far
        # left or right), direction falls back to the sign of current pan so the base
        # continues to unwind toward center.
        base_yaw_assist_required = bool(pan_usage >= self._config.yaw_assist_pan_usage_start)
        yaw_direction_source = "none"
        if base_yaw_assist_required:
            if abs(offset_x) > self._config.dead_zone_x:
                base_yaw_direction = _base_yaw_direction_from_offset(offset_x)
                yaw_direction_source = "face_offset"
            else:
                pan_error = float(current_pan_degrees) - safe_limits.pan_center_degrees
                base_yaw_direction = "left" if pan_error < 0.0 else "right"
                yaw_direction_source = "pan_sign_at_high_usage"
        else:
            base_yaw_direction = None

        reason = "target_centered"
        if abs(pan_delta) > 0.0 or abs(tilt_delta) > 0.0:
            reason = "recenter_target"
        if base_yaw_assist_required:
            reason = "pan_limit_base_yaw_assist_required"

        return TrackingMotionPlan(
            has_target=True,
            target=stable_target,
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
                "tilt_center_degrees": round(safe_limits.tilt_center_degrees, 4),
                "no_tilt_below_center": self._config.no_tilt_below_center,
                "tilt_clamped_to_center": tilt_clamped_to_center,
                "tilt_blocked_by_no_down_rule": tilt_blocked_by_no_down,
                "pan_usage": round(pan_usage, 4),
                "yaw_assist_pan_usage_start_threshold": self._config.yaw_assist_pan_usage_start,
                "yaw_assist_pan_usage_stop_threshold": self._config.yaw_assist_pan_usage_stop,
                "yaw_direction_source": yaw_direction_source,
                "dead_zone_x": self._config.dead_zone_x,
                "dead_zone_y": self._config.dead_zone_y,
                "base_yaw_assist_edge_threshold": self._config.base_yaw_assist_edge_threshold,
                **stable_diagnostics,
            },
        )

    def _stabilize_target(
        self,
        target: TrackingTarget | None,
    ) -> tuple[TrackingTarget | None, str, dict[str, object]]:
        if target is None:
            self._candidate_target = None
            self._candidate_hits = 0
            self._locked_target = None
            return None, "no_target", {"target_lock": "cleared"}

        if target.confidence < self._config.min_target_confidence:
            return None, "target_confidence_below_threshold", {
                "target_confidence": round(target.confidence, 4),
                "min_target_confidence": self._config.min_target_confidence,
            }

        min_area = (
            self._config.min_face_area_norm
            if target.target_type == "face"
            else self._config.min_person_area_norm
        )
        if target.area_norm < min_area:
            return None, "target_area_below_threshold", {
                "target_area_norm": round(target.area_norm, 4),
                "min_target_area_norm": min_area,
                "target_type": target.target_type,
            }

        locked = self._locked_target
        if locked is not None:
            distance = _target_distance(target, locked)
            if distance <= self._config.max_target_jump_norm:
                alpha = self._config.target_smoothing_alpha
                smoothed = replace(
                    target,
                    center_x_norm=(locked.center_x_norm * (1.0 - alpha)) + (target.center_x_norm * alpha),
                    center_y_norm=(locked.center_y_norm * (1.0 - alpha)) + (target.center_y_norm * alpha),
                )
                self._locked_target = smoothed
                self._candidate_target = None
                self._candidate_hits = 0
                return smoothed, "target_locked", {
                    "target_lock": "locked",
                    "target_distance_norm": round(distance, 4),
                    "target_smoothing_alpha": alpha,
                }

            self._candidate_target = target
            self._candidate_hits = 1
            return locked, "target_jump_rejected_using_previous_lock", {
                "target_lock": "jump_rejected",
                "target_distance_norm": round(distance, 4),
                "max_target_jump_norm": self._config.max_target_jump_norm,
            }

        candidate = self._candidate_target
        if candidate is None or _target_distance(target, candidate) > self._config.max_target_jump_norm:
            self._candidate_target = target
            self._candidate_hits = 1
        else:
            self._candidate_target = target
            self._candidate_hits += 1

        if self._candidate_hits < self._config.target_activation_hits:
            return None, "target_waiting_for_stability", {
                "target_lock": "candidate",
                "candidate_hits": self._candidate_hits,
                "target_activation_hits": self._config.target_activation_hits,
            }

        self._locked_target = target
        self._candidate_target = None
        self._candidate_hits = 0
        return target, "target_locked", {
            "target_lock": "activated",
            "target_activation_hits": self._config.target_activation_hits,
        }


def _base_yaw_direction_from_offset(offset_x: float) -> str:
    return "right" if offset_x > 0.0 else "left"


def _near_pan_limit(value: float, limits: TrackingSafeLimits, margin: float) -> bool:
    return value <= limits.pan_min_degrees + margin or value >= limits.pan_max_degrees - margin


def _near_tilt_limit(value: float, limits: TrackingSafeLimits, margin: float) -> bool:
    return value <= limits.tilt_min_degrees + margin or value >= limits.tilt_max_degrees - margin
