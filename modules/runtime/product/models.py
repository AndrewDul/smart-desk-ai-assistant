from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class ProductServiceStatus:
    component: str
    backend: str
    state: str
    detail: str = ""
    required: bool = False
    recoverable: bool = False
    fallback_used: bool = False
    last_checked_iso: str = ""
    recovery_attempted: bool = False
    recovery_ok: bool = False
    recovery_error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProductRuntimeSnapshot:
    lifecycle_state: str = "created"
    status_message: str = ""
    ready: bool = False
    degraded: bool = False
    startup_allowed: bool = False
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    services: dict[str, dict[str, Any]] = field(default_factory=dict)
    updated_at_iso: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "ProductRuntimeSnapshot",
    "ProductServiceStatus",
]