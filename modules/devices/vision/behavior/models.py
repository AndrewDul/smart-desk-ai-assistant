from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, value))


@dataclass(frozen=True, slots=True)
class ActivitySignal:
    active: bool = False
    confidence: float = 0.0
    reasons: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "confidence", _clamp_confidence(float(self.confidence)))


@dataclass(frozen=True, slots=True)
class BehaviorSnapshot:
    presence: ActivitySignal = field(default_factory=ActivitySignal)
    desk_activity: ActivitySignal = field(default_factory=ActivitySignal)
    computer_work: ActivitySignal = field(default_factory=ActivitySignal)
    phone_usage: ActivitySignal = field(default_factory=ActivitySignal)
    study_activity: ActivitySignal = field(default_factory=ActivitySignal)
    metadata: dict[str, Any] = field(default_factory=dict)