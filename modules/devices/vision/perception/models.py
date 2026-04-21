from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


@dataclass(frozen=True, slots=True)
class BoundingBox:
    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        if self.right <= self.left:
            raise ValueError("BoundingBox.right must be greater than left.")
        if self.bottom <= self.top:
            raise ValueError("BoundingBox.bottom must be greater than top.")

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center_x(self) -> float:
        return self.left + (self.width / 2.0)

    @property
    def center_y(self) -> float:
        return self.top + (self.height / 2.0)

    def normalized(self, frame_width: int, frame_height: int) -> "NormalizedRegion":
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("Frame dimensions must be positive.")

        return NormalizedRegion(
            x_min=_clamp(self.left / frame_width, 0.0, 1.0),
            y_min=_clamp(self.top / frame_height, 0.0, 1.0),
            x_max=_clamp(self.right / frame_width, 0.0, 1.0),
            y_max=_clamp(self.bottom / frame_height, 0.0, 1.0),
        )


@dataclass(frozen=True, slots=True)
class NormalizedRegion:
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.x_min < self.x_max <= 1.0):
            raise ValueError("NormalizedRegion x-range must satisfy 0 <= x_min < x_max <= 1.")
        if not (0.0 <= self.y_min < self.y_max <= 1.0):
            raise ValueError("NormalizedRegion y-range must satisfy 0 <= y_min < y_max <= 1.")

    def contains_point(self, x: float, y: float) -> bool:
        return self.x_min <= x <= self.x_max and self.y_min <= y <= self.y_max

    def contains_box_center(self, box: BoundingBox, frame_width: int, frame_height: int) -> bool:
        if frame_width <= 0 or frame_height <= 0:
            return False

        normalized_x = box.center_x / frame_width
        normalized_y = box.center_y / frame_height
        return self.contains_point(normalized_x, normalized_y)


@dataclass(frozen=True, slots=True)
class PersonDetection:
    bounding_box: BoundingBox
    confidence: float
    label: str = "person"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ObjectDetection:
    label: str
    bounding_box: BoundingBox
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SceneContext:
    desk_zone_people_count: int = 0
    screen_candidate_count: int = 0
    handheld_candidate_count: int = 0
    labels: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PerceptionSnapshot:
    frame_width: int
    frame_height: int
    people: tuple[PersonDetection, ...] = ()
    objects: tuple[ObjectDetection, ...] = ()
    scene: SceneContext = field(default_factory=SceneContext)
    metadata: dict[str, Any] = field(default_factory=dict)