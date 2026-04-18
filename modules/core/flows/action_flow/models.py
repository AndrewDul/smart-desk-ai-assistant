from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.runtime.contracts import RouteDecision


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


@dataclass(slots=True)
class SkillRequest:
    turn_id: str
    action: str
    language: str
    route: RouteDecision
    resolved: ResolvedAction
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    confidence: float = 0.0
    route_kind: str = ""
    primary_intent: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_route(
        cls,
        *,
        route: RouteDecision,
        resolved: ResolvedAction,
        language: str,
    ) -> "SkillRequest":
        metadata = dict(route.metadata or {})
        metadata.setdefault("turn_id", str(route.turn_id or "").strip())
        metadata.setdefault("route_kind", getattr(route.kind, "value", str(route.kind)))
        metadata.setdefault("primary_intent", str(route.primary_intent or "").strip())
        metadata.setdefault("resolved_source", str(resolved.source or "").strip())

        return cls(
            turn_id=str(route.turn_id or "").strip(),
            action=str(resolved.name or "").strip().lower() or "unknown",
            language=str(language or "").strip().lower() or "en",
            route=route,
            resolved=resolved,
            payload=dict(resolved.payload or {}),
            source=str(resolved.source or "").strip(),
            confidence=float(resolved.confidence or route.confidence or 0.0),
            route_kind=str(resolved.route_kind or getattr(route.kind, "value", str(route.kind))).strip(),
            primary_intent=str(resolved.primary_intent or route.primary_intent or "").strip(),
            metadata=metadata,
        )

    @property
    def raw_text(self) -> str:
        return str(self.route.raw_text or "").strip()

    @property
    def normalized_text(self) -> str:
        return str(self.route.normalized_text or "").strip()

    @property
    def capture_phase(self) -> str:
        return str(self.metadata.get("capture_phase", "") or "").strip()

    @property
    def capture_mode(self) -> str:
        return str(self.metadata.get("capture_mode", "") or "").strip()

    @property
    def capture_backend(self) -> str:
        return str(self.metadata.get("capture_backend", "") or "").strip()


@dataclass(slots=True)
class SkillResult:
    action: str
    handled: bool
    response_delivered: bool = False
    status: str = "completed"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.handled)

    @property
    def ok(self) -> bool:
        return bool(self.handled)


__all__ = ["ResolvedAction", "SkillRequest", "SkillResult"]