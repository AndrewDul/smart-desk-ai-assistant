from __future__ import annotations

from typing import Protocol

from .frame_packet import FramePacket


class FrameSource(Protocol):
    backend_label: str

    def open(self) -> None: ...

    def read_frame(self) -> FramePacket: ...

    def close(self) -> None: ...