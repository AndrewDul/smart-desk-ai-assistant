from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .enums import InputSource, RouteKind
from .text import normalize_text


@dataclass(slots=True)
class TranscriptRequest:
    """Structured request passed into the speech recognition layer."""

    timeout_seconds: float = 8.0
    debug: bool = False
    source: InputSource = InputSource.VOICE
    mode: str = "command"
    metadata: dict[str, Any] = field(default_factory=dict)


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
    def wall_clock_duration_seconds(self) -> float:
        return max(0.0, self.ended_at - self.started_at)

    @property
    def audio_duration_seconds(self) -> float:
        raw = self.metadata.get("audio_duration_seconds")
        try:
            if raw is not None:
                return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass
        return self.wall_clock_duration_seconds

    @property
    def processing_duration_seconds(self) -> float:
        raw = self.metadata.get("transcription_elapsed_seconds")
        try:
            if raw is not None:
                return max(0.0, float(raw))
        except (TypeError, ValueError):
            pass

        wall_clock = self.wall_clock_duration_seconds
        audio_duration = self.audio_duration_seconds
        return max(0.0, wall_clock - audio_duration)

    @property
    def duration_seconds(self) -> float:
        return self.audio_duration_seconds

    @property
    def latency_ms(self) -> float:
        return self.processing_duration_seconds * 1000.0

    @property
    def normalized_text(self) -> str:
        return normalize_text(self.text)


@dataclass(slots=True)
class WakeDetectionResult:
    """Normalized wake-word detection event."""

    phrase: str
    accepted: bool = True
    confidence: float = 1.0
    source: InputSource = InputSource.VOICE
    started_at: float = field(default_factory=time.monotonic)
    ended_at: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def duration_seconds(self) -> float:
        return max(0.0, self.ended_at - self.started_at)

    @property
    def latency_ms(self) -> float:
        return self.duration_seconds * 1000.0

    @property
    def normalized_phrase(self) -> str:
        return normalize_text(self.phrase)


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
    "TranscriptRequest",
    "TranscriptResult",
    "WakeDetectionResult",
]