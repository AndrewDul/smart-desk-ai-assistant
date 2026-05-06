"""
Pure scan planner.

When the face tracker has not seen a face for several frames, the head should
sweep the room looking for one. This planner produces a sequence of absolute
pan/tilt targets covering both the horizontal axis (left ↔ right) AND a few
vertical levels — NEXA sits low and the user is usually standing, so a
strictly horizontal scan misses faces above the camera.

This module contains NO hardware, NO I/O. The session adapter calls
`next_target()` on each scan tick and converts the absolute target into a
delta against the current pan/tilt angles.

Pattern:
    For each tilt level in tilt_levels:
        sweep pan from pan_min to pan_max in pan_step increments
        then reverse: pan_max → pan_min
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScanCommand:
    """Absolute pan/tilt target for the scan sweep."""

    target_pan_degrees: float
    target_tilt_degrees: float
    direction: str  # "left", "right", "up", "down", "settle"


class ScanPlanner:
    """Stateful sweep planner. Call next_target() each scan tick."""

    def __init__(
        self,
        *,
        pan_limit_degrees: float = 50.0,
        pan_step_degrees: float = 6.0,
        tilt_levels_degrees: tuple[float, ...] = (0.0, 6.0, 10.0),
    ) -> None:
        self.pan_limit = abs(float(pan_limit_degrees))
        self.pan_step = max(0.5, float(pan_step_degrees))
        # Filter out duplicates and keep order.
        seen: set[float] = set()
        ordered: list[float] = []
        for level in tilt_levels_degrees:
            value = float(level)
            if value not in seen:
                seen.add(value)
                ordered.append(value)
        self.tilt_levels: tuple[float, ...] = tuple(ordered) if ordered else (0.0,)

        self._current_pan = -self.pan_limit
        self._tilt_index = 0
        self._pan_direction = +1  # +1 = sweeping right, -1 = sweeping left

    def reset(self) -> None:
        """Restart the sweep from the leftmost position, lowest tilt level."""
        self._current_pan = -self.pan_limit
        self._tilt_index = 0
        self._pan_direction = +1

    def next_target(self) -> ScanCommand:
        """Advance the sweep one step and return the new absolute target."""
        target_pan = self._current_pan
        target_tilt = self.tilt_levels[self._tilt_index]
        direction = "right" if self._pan_direction > 0 else "left"

        # Advance state for the NEXT tick.
        self._current_pan += self._pan_direction * self.pan_step

        if self._current_pan > self.pan_limit:
            # Reached right edge. Bounce back.
            self._current_pan = self.pan_limit
            self._pan_direction = -1
            self._advance_tilt_level()
        elif self._current_pan < -self.pan_limit:
            # Reached left edge. Bounce back.
            self._current_pan = -self.pan_limit
            self._pan_direction = +1
            self._advance_tilt_level()

        return ScanCommand(
            target_pan_degrees=float(target_pan),
            target_tilt_degrees=float(target_tilt),
            direction=direction,
        )

    def _advance_tilt_level(self) -> None:
        self._tilt_index = (self._tilt_index + 1) % len(self.tilt_levels)


__all__ = ["ScanPlanner", "ScanCommand"]
