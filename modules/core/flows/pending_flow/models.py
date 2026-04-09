from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PendingFlowDecision:
    handled: bool
    response: bool | None = None
    consumed_by: str = ""


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