from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class FramePacket:
    pixels: Any
    width: int
    height: int
    channels: int
    backend_label: str
    captured_at: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)