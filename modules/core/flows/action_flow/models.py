from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ResolvedAction:
    name: str
    payload: dict[str, Any]
    source: str
    confidence: float = 0.0
    route_kind: str = ""
    primary_intent: str = ""
    route_notes: tuple[str, ...] = ()
    route_metadata: dict[str, Any] = field(default_factory=dict)