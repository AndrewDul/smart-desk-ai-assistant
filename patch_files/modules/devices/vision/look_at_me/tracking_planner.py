"""
Pure tracking planner.

Given a face center (normalized 0..1 in frame coordinates) and the current
pan/tilt angles, produce a (pan_delta, tilt_delta) movement command in degrees
that moves the face toward the frame center.

This module deliberately contains NO threading, NO hardware, NO I/O. All
behavior is testable with synthetic inputs.

Coordinate convention:
    - x_norm = 0.5 means face is at horizontal center
    - y_norm = 0.5 means face is at vertical center
    - x_norm < 0.5 means face is on the LEFT side of frame  -> pan LEFT (negative)
    - y_norm < 0.5 means face is in the UPPER part of frame -> tilt UP

The sign convention for pan/tilt deltas matches WaveshareSerialPanTiltBackend:
    - positive pan_delta  -> pan right
    - positive tilt_delta -> tilt up
You can flip tilt direction with `invert_tilt=True` if your hardware mounts
the servo differently.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TrackingCommand:
    """One pan/tilt move suggestion in degrees."""

    pan_delta_degrees: float
    tilt_delta_degrees: float
    in_hold_zone: bool
    reason: str


class TrackingPlanner:
    """Translate a normalized face position into a pan/tilt delta."""

    def __init__(
        self,
        *,
        pan_gain_degrees: float = 22.0,
        tilt_gain_degrees: float = 24.0,
        target_x_norm: float = 0.5,
        target_y_norm: float = 0.5,
        hold_zone_x: float = 0.020,
        hold_zone_y: float = 0.025,
        max_step_degrees: float = 1.4,
        fast_offset_threshold: float = 0.045,
        fast_gain_boost: float = 1.35,
        invert_tilt: bool = False,
    ) -> None:
        self.pan_gain = float(pan_gain_degrees)
        self.tilt_gain = float(tilt_gain_degrees)
        self.target_x = float(target_x_norm)
        self.target_y = float(target_y_norm)
        self.hold_zone_x = max(0.0, float(hold_zone_x))
        self.hold_zone_y = max(0.0, float(hold_zone_y))
        self.max_step = max(0.0, float(max_step_degrees))
        self.fast_threshold = max(0.0, float(fast_offset_threshold))
        self.fast_boost = max(1.0, float(fast_gain_boost))
        self.invert_tilt = bool(invert_tilt)

    def plan(self, *, face_x_norm: float, face_y_norm: float) -> TrackingCommand:
        """Return the pan/tilt delta needed to move the face toward the target."""
        offset_x = float(face_x_norm) - self.target_x
        offset_y = float(face_y_norm) - self.target_y

        in_hold_x = abs(offset_x) <= self.hold_zone_x
        in_hold_y = abs(offset_y) <= self.hold_zone_y

        if in_hold_x and in_hold_y:
            return TrackingCommand(
                pan_delta_degrees=0.0,
                tilt_delta_degrees=0.0,
                in_hold_zone=True,
                reason="face_centered",
            )

        # Fast-lane gain boost when the offset is large — faces moving quickly
        # benefit from a stronger correction so the head can catch up before
        # the small per-frame step caps lose them.
        pan_gain = self.pan_gain
        tilt_gain = self.tilt_gain
        if abs(offset_x) >= self.fast_threshold:
            pan_gain *= self.fast_boost
        if abs(offset_y) >= self.fast_threshold:
            tilt_gain *= self.fast_boost

        # Sign convention:
        #   face on the left (offset_x < 0) -> pan LEFT (negative delta)
        #   face above center (offset_y < 0) -> tilt UP. If servo is mounted
        #   inverted, the caller flips the sign via invert_tilt.
        pan_delta = offset_x * pan_gain
        tilt_delta = -offset_y * tilt_gain
        if self.invert_tilt:
            tilt_delta = -tilt_delta

        # Per-step safety cap — the pan/tilt service ALSO clamps this, but
        # capping here keeps planner output predictable for tests.
        pan_delta = self._clamp(pan_delta, self.max_step)
        tilt_delta = self._clamp(tilt_delta, self.max_step)

        return TrackingCommand(
            pan_delta_degrees=pan_delta,
            tilt_delta_degrees=tilt_delta,
            in_hold_zone=False,
            reason="tracking",
        )

    @staticmethod
    def _clamp(value: float, limit: float) -> float:
        if limit <= 0.0:
            return 0.0
        if value > limit:
            return limit
        if value < -limit:
            return -limit
        return value


__all__ = ["TrackingPlanner", "TrackingCommand"]
