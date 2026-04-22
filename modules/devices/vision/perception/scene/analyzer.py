from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from modules.devices.vision.capture import FramePacket
from modules.devices.vision.perception.models import (
    NormalizedRegion,
    ObjectDetection,
    PersonDetection,
    SceneContext,
)

from .workspace_zones import WorkspaceZoneLayout, build_default_workspace_zone_layout

_SCREEN_OBJECT_LABELS = {"monitor", "screen", "laptop", "keyboard"}
_HANDHELD_OBJECT_LABELS = {"phone", "cell phone", "mobile phone", "smartphone"}


def _region_to_dict(region: NormalizedRegion) -> dict[str, float]:
    return {
        "x_min": region.x_min,
        "y_min": region.y_min,
        "x_max": region.x_max,
        "y_max": region.y_max,
    }


class SceneAnalyzer(Protocol):
    backend_label: str

    def analyze_scene(
        self,
        packet: FramePacket,
        people: tuple[PersonDetection, ...],
        objects: tuple[ObjectDetection, ...],
    ) -> SceneContext:
        ...


@dataclass(slots=True)
class NullSceneAnalyzer:
    """
    Lightweight rule-based scene analyzer.

    It does not perform heavy CV on its own. It only interprets spatial context
    from detections and workspace zones, which makes it safe to keep as a stable
    foundation for later detector upgrades.
    """

    backend_label: str = "zone_rules"
    zone_layout: WorkspaceZoneLayout = field(default_factory=build_default_workspace_zone_layout)

    def analyze_scene(
        self,
        packet: FramePacket,
        people: tuple[PersonDetection, ...],
        objects: tuple[ObjectDetection, ...],
    ) -> SceneContext:
        frame_width = packet.width
        frame_height = packet.height

        desk_zone_people_count = sum(
            1
            for person in people
            if self.zone_layout.desk_zone.contains_box_center(
                person.bounding_box,
                frame_width,
                frame_height,
            )
        )

        screen_candidate_count = sum(
            1
            for obj in objects
            if obj.label.strip().lower() in _SCREEN_OBJECT_LABELS
            and self.zone_layout.screen_zone.contains_box_center(
                obj.bounding_box,
                frame_width,
                frame_height,
            )
        )

        handheld_candidate_count = sum(
            1
            for obj in objects
            if obj.label.strip().lower() in _HANDHELD_OBJECT_LABELS
            and self.zone_layout.handheld_zone.contains_box_center(
                obj.bounding_box,
                frame_width,
                frame_height,
            )
        )

        labels: list[str] = []
        if desk_zone_people_count > 0:
            labels.append("person_in_desk_zone")
        if screen_candidate_count > 0:
            labels.append("screen_candidate_visible")
        if handheld_candidate_count > 0:
            labels.append("handheld_candidate_visible")

        return SceneContext(
            desk_zone_people_count=desk_zone_people_count,
            screen_candidate_count=screen_candidate_count,
            handheld_candidate_count=handheld_candidate_count,
            labels=tuple(labels),
            metadata={
                "zone_layout": {
                    "desk_zone": _region_to_dict(self.zone_layout.desk_zone),
                    "screen_zone": _region_to_dict(self.zone_layout.screen_zone),
                    "handheld_zone": _region_to_dict(self.zone_layout.handheld_zone),
                }
            },
        )