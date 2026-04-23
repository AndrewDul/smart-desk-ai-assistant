from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AiBrokerMode(str, Enum):
    IDLE_BASELINE = "idle_baseline"
    CONVERSATION_ANSWER = "conversation_answer"
    VISION_ACTION = "vision_action"
    FOCUS_SENTINEL = "focus_sentinel"
    RECOVERY_WINDOW = "recovery_window"


class AiBrokerOwner(str, Enum):
    BALANCED = "balanced"
    ANSWER_PATH = "answer_path"
    VISION_PATH = "vision_path"
    MONITOR_PATH = "monitor_path"


@dataclass(frozen=True, slots=True)
class AiLaneProfile:
    heavy_lane_cadence_hz: float
    keep_fast_lane_alive: bool = True
    llm_priority: str = "normal"
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "heavy_lane_cadence_hz": float(self.heavy_lane_cadence_hz),
            "keep_fast_lane_alive": bool(self.keep_fast_lane_alive),
            "llm_priority": str(self.llm_priority),
            "notes": list(self.notes),
        }


@dataclass(slots=True)
class AiBrokerSnapshot:
    mode: AiBrokerMode
    owner: AiBrokerOwner
    profile: AiLaneProfile
    recovery_window_active: bool = False
    recovery_until_monotonic: float | None = None
    last_reason: str = ""
    last_error: str | None = None
    vision_control_available: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "owner": self.owner.value,
            "profile": self.profile.to_dict(),
            "recovery_window_active": bool(self.recovery_window_active),
            "recovery_until_monotonic": self.recovery_until_monotonic,
            "last_reason": str(self.last_reason),
            "last_error": self.last_error,
            "vision_control_available": bool(self.vision_control_available),
            "metadata": dict(self.metadata),
        }