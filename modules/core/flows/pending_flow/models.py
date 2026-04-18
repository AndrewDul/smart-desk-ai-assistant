from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PendingFlowDecision:
    handled: bool
    response: bool | None = None
    consumed_by: str = ""
    pending_kind: str = ""
    pending_type: str = ""
    language: str = ""
    keeps_pending_state: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PendingIntentPayload:
    """
    Lightweight action payload compatible with the old parser IntentResult shape.
    """

    action: str
    data: dict[str, Any]
    normalized_text: str
    confidence: float = 1.0
    needs_confirmation: bool = False
    suggestions: list[dict[str, Any]] | None = None