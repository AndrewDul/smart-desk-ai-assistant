from __future__ import annotations

from typing import Protocol

from modules.devices.vision.capture import FramePacket
from modules.devices.vision.perception.models import PersonDetection


class PeopleDetector(Protocol):
    backend_label: str

    def detect_people(self, packet: FramePacket) -> tuple[PersonDetection, ...]:
        ...


class NullPeopleDetector:
    """
    Stable no-op detector used until the real people detector is enabled.
    """

    backend_label = "null"

    def detect_people(self, packet: FramePacket) -> tuple[PersonDetection, ...]:
        del packet
        return ()