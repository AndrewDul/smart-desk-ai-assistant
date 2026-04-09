from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .enums import InputSource, RouteKind
from .text import normalize_text


@dataclass(slots=True)
class TranscriptResult:
    """Final or partial text produced by the speech layer."""

    text: str
    language: str = "auto"
    confidence: float = 0.0
    is_final: bool = True
    source: InputSource = InputSource.VOICE
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.ended_at - self.started_at)

    @property
    def normalized_text(self) -> str:
        return normalize_text(self.text)


@dataclass(slots=True)
class EntityValue:
    """Structured value extracted from the user request."""

    name: str
    value: Any
    confidence: float = 1.0
    source_text: str = ""


@dataclass(slots=True)
class IntentMatch:
    """One intent candidate detected by the understanding layer."""

    name: str
    confidence: float
    entities: list[EntityValue] = field(default_factory=list)
    requires_clarification: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolInvocation:
    """Tool request prepared by the routing layer."""

    tool_name: str
    payload: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    confidence: float = 1.0
    execute_immediately: bool = True


@dataclass(slots=True)
class ToolResult:
    """Normalized result returned by a tool or internal action service."""

    tool_name: str
    ok: bool
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    completed_at: float = field(default_factory=time.monotonic)


@dataclass(slots=True)
class RouteDecision:
    """
    Unified decision shared between STT, NLU, dialogue, and tool execution.
    """

    turn_id: str
    raw_text: str
    normalized_text: str
    language: str
    kind: RouteKind
    confidence: float
    primary_intent: str = "unknown"
    intents: list[IntentMatch] = field(default_factory=list)
    conversation_topics: list[str] = field(default_factory=list)
    tool_invocations: list[ToolInvocation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def has_tool_work(self) -> bool:
        return bool(self.tool_invocations)

    @property
    def should_reply_naturally(self) -> bool:
        return self.kind in {RouteKind.CONVERSATION, RouteKind.MIXED, RouteKind.UNCLEAR}

    @property
    def should_execute_tools(self) -> bool:
        return self.kind in {RouteKind.ACTION, RouteKind.MIXED} and self.has_tool_work


__all__ = [
    "EntityValue",
    "IntentMatch",
    "RouteDecision",
    "ToolInvocation",
    "ToolResult",
    "TranscriptResult",
]