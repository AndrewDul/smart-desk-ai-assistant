from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ResolvedAction:
    name: str
    payload: dict[str, Any]
    source: str
    confidence: float = 0.0