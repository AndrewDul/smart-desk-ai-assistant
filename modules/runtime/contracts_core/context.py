from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .understanding import RouteDecision, TranscriptResult


@dataclass(slots=True)
class VisionObservation:
    """Stable contract for the future camera stack."""

    detected: bool = False
    user_present: bool = False
    studying_likely: bool = False
    on_phone_likely: bool = False
    computer_work_likely: bool = False
    desk_active: bool = False
    labels: list[str] = field(default_factory=list)
    confidence: float = 0.0
    captured_at: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TurnContext:
    """Snapshot passed across the speech, understanding, and response pipeline."""

    transcript: TranscriptResult
    route: RouteDecision
    vision: VisionObservation | None = None
    memory_hints: list[str] = field(default_factory=list)
    user_profile: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "TurnContext",
    "VisionObservation",
]