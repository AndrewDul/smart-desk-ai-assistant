from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .frame_packet import FramePacket
    from .reader import VisionCaptureReader

__all__ = ["FramePacket", "VisionCaptureReader"]


def __getattr__(name: str):
    if name == "FramePacket":
        from .frame_packet import FramePacket

        return FramePacket
    if name == "VisionCaptureReader":
        from .reader import VisionCaptureReader

        return VisionCaptureReader
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")