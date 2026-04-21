from __future__ import annotations

from dataclasses import dataclass

from modules.devices.vision.perception.models import NormalizedRegion


@dataclass(frozen=True, slots=True)
class WorkspaceZoneLayout:
    desk_zone: NormalizedRegion
    screen_zone: NormalizedRegion
    handheld_zone: NormalizedRegion


def build_default_workspace_zone_layout() -> WorkspaceZoneLayout:
    """
    Default normalized zones for a desk-facing camera.

    These are intentionally conservative and are meant to be calibrated later.
    """
    return WorkspaceZoneLayout(
        desk_zone=NormalizedRegion(0.12, 0.32, 0.88, 0.98),
        screen_zone=NormalizedRegion(0.16, 0.05, 0.84, 0.62),
        handheld_zone=NormalizedRegion(0.18, 0.42, 0.82, 0.98),
    )