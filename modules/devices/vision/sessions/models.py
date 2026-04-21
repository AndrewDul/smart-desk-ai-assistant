from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ActivitySessionSnapshot:
    active: bool = False
    state: str = "inactive"
    current_active_seconds: float = 0.0
    last_active_streak_seconds: float = 0.0
    total_active_seconds: float = 0.0
    activations: int = 0
    last_started_at: float | None = None
    last_ended_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class VisionSessionSnapshot:
    presence: ActivitySessionSnapshot = field(default_factory=ActivitySessionSnapshot)
    desk_activity: ActivitySessionSnapshot = field(default_factory=ActivitySessionSnapshot)
    computer_work: ActivitySessionSnapshot = field(default_factory=ActivitySessionSnapshot)
    phone_usage: ActivitySessionSnapshot = field(default_factory=ActivitySessionSnapshot)
    study_activity: ActivitySessionSnapshot = field(default_factory=ActivitySessionSnapshot)
    metadata: dict[str, Any] = field(default_factory=dict)