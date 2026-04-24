from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class VisualEventName(StrEnum):
    """Runtime events that can be mapped to Visual Shell states."""

    BOOT_READY = "BOOT_READY"
    WAKE_DETECTED = "WAKE_DETECTED"
    LISTENING_STARTED = "LISTENING_STARTED"
    LISTENING_FINISHED = "LISTENING_FINISHED"
    THINKING_STARTED = "THINKING_STARTED"
    SPEAKING_STARTED = "SPEAKING_STARTED"
    SPEAKING_FINISHED = "SPEAKING_FINISHED"
    VISION_SCAN_STARTED = "VISION_SCAN_STARTED"
    VISION_SCAN_FINISHED = "VISION_SCAN_FINISHED"
    DESKTOP_REQUESTED = "DESKTOP_REQUESTED"
    ASSISTANT_SCREEN_REQUESTED = "ASSISTANT_SCREEN_REQUESTED"
    SHOW_SELF_REQUESTED = "SHOW_SELF_REQUESTED"
    DEGRADED = "DEGRADED"


@dataclass(slots=True)
class VisualEvent:
    """Input event produced by NEXA runtime subsystems."""

    name: VisualEventName
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "nexa-runtime"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["name"] = self.name.value
        data["payload"] = dict(self.payload)
        return data