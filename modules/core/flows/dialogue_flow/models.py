from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DialogueRouteBridge:
    """
    Lightweight adapter for dialogue services that still expect the older
    route-like shape while the rest of the runtime uses RouteDecision.
    """

    kind: str
    reply_mode: str
    language: str
    raw_text: str
    normalized_text: str
    action_result: Any | None = None
    confidence: float = 0.0
    conversation_topics: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def has_action(self) -> bool:
        return self.action_result is not None


__all__ = ["DialogueRouteBridge"]