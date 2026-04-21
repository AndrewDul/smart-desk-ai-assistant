from __future__ import annotations

from typing import Protocol

from modules.devices.vision.capture import FramePacket
from modules.devices.vision.perception.models import ObjectDetection


class ObjectDetector(Protocol):
    backend_label: str

    def detect_objects(self, packet: FramePacket) -> tuple[ObjectDetection, ...]:
        ...


class NullObjectDetector:
    """
    Stable no-op detector used until the real object detector is enabled.
    """

    backend_label = "null"

    def detect_objects(self, packet: FramePacket) -> tuple[ObjectDetection, ...]:
        del packet
        return ()