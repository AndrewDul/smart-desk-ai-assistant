from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ReminderMatch:
    reminder: dict[str, Any]
    score: float
    exact: bool = False


__all__ = ["ReminderMatch"]