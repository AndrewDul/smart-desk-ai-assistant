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
    requested_backend: str = ""
    runtime_mode: str = ""
    capabilities: list[str] = field(default_factory=list)
    primary: bool = False
    compatibility_mode: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
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
    primary_ready: bool = False
    premium_ready: bool = False
    startup_mode: str = "created"
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    premium_blockers: list[str] = field(default_factory=list)
    required_components: list[str] = field(default_factory=list)
    compatibility_components: list[str] = field(default_factory=list)
    degraded_components: list[str] = field(default_factory=list)
    services: dict[str, dict[str, Any]] = field(default_factory=dict)
    provider_inventory: dict[str, dict[str, Any]] = field(default_factory=dict)

    llm_enabled: bool = False
    llm_runner: str = ""
    llm_state: str = "disabled"
    llm_available: bool = False
    llm_healthy: bool = False
    llm_warmup_required: bool = False
    llm_warmup_ready: bool = False
    llm_primary_ready: bool = False
    llm_health_reason: str = ""
    llm_availability_requirement: str = "premium"
    llm_warmup_requirement: str = "premium"

    updated_at_iso: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "ProductRuntimeSnapshot",
    "ProductServiceStatus",
]