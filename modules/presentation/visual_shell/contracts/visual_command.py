from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class VisualCommandName(StrEnum):
    """Commands sent from NEXA runtime to the visual shell renderer."""

    SET_STATE = "SET_STATE"
    SHOW_DESKTOP = "SHOW_DESKTOP"
    HIDE_DESKTOP = "HIDE_DESKTOP"
    SHOW_SELF = "SHOW_SELF"
    SHOW_EYES = "SHOW_EYES"
    SHOW_FACE_CONTOUR = "SHOW_FACE_CONTOUR"
    START_SCANNING = "START_SCANNING"
    RETURN_TO_IDLE = "RETURN_TO_IDLE"
    REPORT_DEGRADED = "REPORT_DEGRADED"
    SHOW_TEMPERATURE = "SHOW_TEMPERATURE"
    SHOW_BATTERY = "SHOW_BATTERY"
    SHOW_DATE = "SHOW_DATE"
    SHOW_TIME = "SHOW_TIME"
    SHOW_HELP = "SHOW_HELP"


@dataclass(slots=True)
class VisualCommand:
    """Serializable command envelope for the Visual Shell transport layer."""

    command: VisualCommandName
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "nexa-runtime"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["command"] = self.command.value
        data["payload"] = dict(self.payload)
        return data