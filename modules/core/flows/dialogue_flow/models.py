from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.runtime.contracts import RouteDecision, RouteKind, ToolInvocation


@dataclass(slots=True)
class DialogueRequest:
    turn_id: str
    kind: RouteKind
    reply_mode: str
    language: str
    raw_text: str
    normalized_text: str
    confidence: float = 0.0
    primary_intent: str = "unknown"
    conversation_topics: list[str] = field(default_factory=list)
    suggested_actions: list[str] = field(default_factory=list)
    immediate_actions: list[str] = field(default_factory=list)
    tool_invocations: list[ToolInvocation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    route: RouteDecision | None = None

    @classmethod
    def from_route(
        cls,
        *,
        route: RouteDecision,
        language: str,
        reply_mode: str,
        suggested_actions: list[str] | None = None,
        immediate_actions: list[str] | None = None,
    ) -> "DialogueRequest":
        metadata = dict(route.metadata or {})
        metadata.setdefault("turn_id", str(route.turn_id or "").strip())
        metadata.setdefault("route_kind", route.kind.value)
        metadata.setdefault("primary_intent", str(route.primary_intent or "unknown").strip() or "unknown")

        return cls(
            turn_id=str(route.turn_id or "").strip(),
            kind=route.kind,
            reply_mode=str(reply_mode or "reply").strip().lower() or "reply",
            language=str(language or route.language or "en").strip().lower() or "en",
            raw_text=str(route.raw_text or "").strip(),
            normalized_text=str(route.normalized_text or "").strip(),
            confidence=float(route.confidence or 0.0),
            primary_intent=str(route.primary_intent or "unknown").strip() or "unknown",
            conversation_topics=list(route.conversation_topics or []),
            suggested_actions=list(suggested_actions or []),
            immediate_actions=list(immediate_actions or []),
            tool_invocations=list(route.tool_invocations or []),
            notes=list(route.notes or []),
            metadata=metadata,
            route=route,
        )

    @property
    def action_result(self) -> Any | None:
        if not self.immediate_actions:
            return None

        class _Payload:
            def __init__(self, action: str, normalized_text: str) -> None:
                self.action = action
                self.data = {}
                self.normalized_text = normalized_text
                self.confidence = 1.0
                self.needs_confirmation = False
                self.suggestions = []

        return _Payload(self.immediate_actions[0], self.normalized_text)

    @property
    def has_action(self) -> bool:
        return bool(self.immediate_actions)

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
class DialogueResult:
    handled: bool
    delivered: bool = False
    status: str = "completed"
    source: str = "dialogue_flow"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.handled)

    @property
    def ok(self) -> bool:
        return bool(self.handled)


DialogueRouteBridge = DialogueRequest


__all__ = ["DialogueRequest", "DialogueResult", "DialogueRouteBridge"]