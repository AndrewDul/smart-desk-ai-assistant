from __future__ import annotations

from typing import Protocol

from modules.devices.vision.capture import FramePacket
from modules.devices.vision.perception.models import FaceDetection


class FaceDetector(Protocol):
    backend_label: str

    def detect_faces(self, packet: FramePacket) -> tuple[FaceDetection, ...]:
        ...


class NullFaceDetector:
    """
    Stable no-op face detector used until a real face detector is enabled.
    """

    backend_label = "null"

    def detect_faces(self, packet: FramePacket) -> tuple[FaceDetection, ...]:
        del packet
        return ()