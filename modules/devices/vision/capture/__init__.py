# modules/devices/vision/capture/__init__.py
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .continuous_worker import ContinuousCaptureWorker
    from .frame_packet import FramePacket
    from .reader import VisionCaptureReader

__all__ = ["ContinuousCaptureWorker", "FramePacket", "VisionCaptureReader"]


def __getattr__(name: str):
    if name == "FramePacket":
        from .frame_packet import FramePacket
        return FramePacket
    if name == "VisionCaptureReader":
        from .reader import VisionCaptureReader
        return VisionCaptureReader
    if name == "ContinuousCaptureWorker":
        from .continuous_worker import ContinuousCaptureWorker
        return ContinuousCaptureWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")