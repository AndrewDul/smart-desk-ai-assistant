from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


@dataclass(frozen=True, slots=True)
class TrackingTarget:
    target_type: str
    confidence: float
    box: dict[str, int]
    center_x_norm: float
    center_y_norm: float
    area_norm: float
    source_index: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.target_type not in {"face", "person"}:
            raise ValueError("TrackingTarget.target_type must be 'face' or 'person'.")
        object.__setattr__(self, "confidence", _clamp(self.confidence, 0.0, 1.0))
        object.__setattr__(self, "center_x_norm", _clamp(self.center_x_norm, 0.0, 1.0))
        object.__setattr__(self, "center_y_norm", _clamp(self.center_y_norm, 0.0, 1.0))
        object.__setattr__(self, "area_norm", _clamp(self.area_norm, 0.0, 1.0))


@dataclass(frozen=True, slots=True)
class TrackingSafeLimits:
    pan_min_degrees: float = -15.0
    pan_max_degrees: float = 15.0
    tilt_min_degrees: float = -8.0
    tilt_max_degrees: float = 8.0

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "TrackingSafeLimits":
        data = dict(payload or {})
        return cls(
            pan_min_degrees=float(data.get("pan_min_degrees", -15.0)),
            pan_max_degrees=float(data.get("pan_max_degrees", 15.0)),
            tilt_min_degrees=float(data.get("tilt_min_degrees", -8.0)),
            tilt_max_degrees=float(data.get("tilt_max_degrees", 8.0)),
        )

    def __post_init__(self) -> None:
        if self.pan_max_degrees < self.pan_min_degrees:
            raise ValueError("Pan max limit must be greater than or equal to pan min limit.")
        if self.tilt_max_degrees < self.tilt_min_degrees:
            raise ValueError("Tilt max limit must be greater than or equal to tilt min limit.")

    def clamp_pan(self, value: float) -> float:
        return _clamp(value, self.pan_min_degrees, self.pan_max_degrees)

    def clamp_tilt(self, value: float) -> float:
        return _clamp(value, self.tilt_min_degrees, self.tilt_max_degrees)


@dataclass(frozen=True, slots=True)
class TrackingPolicyConfig:
    enabled: bool = True
    dead_zone_x: float = 0.08
    dead_zone_y: float = 0.10
    pan_gain_degrees: float = 12.0
    tilt_gain_degrees: float = 8.0
    max_step_degrees: float = 2.0
    limit_margin_degrees: float = 1.0
    base_yaw_assist_edge_threshold: float = 0.42
    mobile_assist_edge_threshold: float | None = None

    def __post_init__(self) -> None:
        if self.mobile_assist_edge_threshold is not None:
            object.__setattr__(
                self,
                "base_yaw_assist_edge_threshold",
                max(0.0, min(0.5, float(self.mobile_assist_edge_threshold))),
            )

    @classmethod
    def from_mapping(cls, payload: dict[str, Any] | None) -> "TrackingPolicyConfig":
        data = dict(payload or {})
        base_threshold = data.get(
            "base_yaw_assist_edge_threshold",
            data.get("mobile_assist_edge_threshold", 0.42),
        )
        return cls(
            enabled=bool(data.get("enabled", True)),
            dead_zone_x=max(0.0, min(0.45, float(data.get("dead_zone_x", 0.08)))),
            dead_zone_y=max(0.0, min(0.45, float(data.get("dead_zone_y", 0.10)))),
            pan_gain_degrees=max(0.0, float(data.get("pan_gain_degrees", 12.0))),
            tilt_gain_degrees=max(0.0, float(data.get("tilt_gain_degrees", 8.0))),
            max_step_degrees=max(0.1, float(data.get("max_step_degrees", 2.0))),
            limit_margin_degrees=max(0.0, float(data.get("limit_margin_degrees", 1.0))),
            base_yaw_assist_edge_threshold=max(0.0, min(0.5, float(base_threshold))),
        )


@dataclass(frozen=True, slots=True)
class TrackingMotionPlan:
    has_target: bool
    target: TrackingTarget | None
    pan_delta_degrees: float = 0.0
    tilt_delta_degrees: float = 0.0
    desired_pan_degrees: float = 0.0
    desired_tilt_degrees: float = 0.0
    clamped_pan_degrees: float = 0.0
    clamped_tilt_degrees: float = 0.0
    pan_at_limit: bool = False
    tilt_at_limit: bool = False
    base_yaw_assist_required: bool = False
    base_yaw_direction: str | None = None
    base_forward_velocity: float = 0.0
    base_backward_velocity: float = 0.0
    mobile_assist_recommended: bool = False
    reason: str = "no_target"
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def movement_requested(self) -> bool:
        return abs(self.pan_delta_degrees) > 0.0 or abs(self.tilt_delta_degrees) > 0.0
