from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class InputSource(str, Enum):
    """Normalized source of an incoming user turn."""

    VOICE = "voice"
    TEXT = "text"
    SYSTEM = "system"
    VISION = "vision"


class RouteKind(str, Enum):
    """High-level decision made by the understanding layer."""

    ACTION = "action"
    CONVERSATION = "conversation"
    MIXED = "mixed"
    UNCLEAR = "unclear"


class StreamMode(str, Enum):
    """How NeXa should release spoken output."""

    WHOLE_RESPONSE = "whole_response"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"


class ChunkKind(str, Enum):
    """Logical meaning of an assistant output chunk."""

    ACK = "ack"
    CONTENT = "content"
    TOOL_STATUS = "tool_status"
    FOLLOW_UP = "follow_up"
    ERROR = "error"
    FINAL = "final"


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
    """One intent candidate detected by the NLU layer."""

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

    This is the key migration contract for the new NeXa architecture.
    It lets the current parser/router coexist with the future streaming stack.
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


@dataclass(slots=True)
class AssistantChunk:
    """
    One streamable piece of NeXa output.

    `speak_now=True` means the TTS layer is allowed to speak the chunk immediately.
    `flush=True` means the chunk is a clean boundary and should not wait for more text.
    """

    text: str
    language: str = "en"
    kind: ChunkKind = ChunkKind.CONTENT
    speak_now: bool = True
    flush: bool = True
    sequence_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_text(self) -> str:
        return normalize_text(self.text)

    @property
    def is_empty(self) -> bool:
        return not bool(self.normalized_text)


@dataclass(slots=True)
class ResponsePlan:
    """
    Output plan produced by dialogue/tool orchestration.

    The plan is intentionally neutral:
    - text-only mode can join all chunks into one reply
    - streaming TTS mode can speak sentence chunks immediately
    - future UI/OLED layers can react chunk-by-chunk
    """

    turn_id: str
    language: str
    route_kind: RouteKind
    stream_mode: StreamMode = StreamMode.SENTENCE
    chunks: list[AssistantChunk] = field(default_factory=list)
    follow_up_suggestions: list[str] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_chunk(
        self,
        text: str,
        *,
        kind: ChunkKind = ChunkKind.CONTENT,
        speak_now: bool = True,
        flush: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        cleaned = clean_response_text(text)
        if not cleaned:
            return

        self.chunks.append(
            AssistantChunk(
                text=cleaned,
                language=self.language,
                kind=kind,
                speak_now=speak_now,
                flush=flush,
                sequence_index=len(self.chunks),
                metadata=metadata or {},
            )
        )

    def add_text(
        self,
        text: str,
        *,
        kind: ChunkKind = ChunkKind.CONTENT,
        mode: StreamMode | None = None,
    ) -> None:
        selected_mode = mode or self.stream_mode
        for chunk in chunk_text_for_streaming(text, self.language, selected_mode):
            chunk.kind = kind
            chunk.sequence_index = len(self.chunks)
            self.chunks.append(chunk)

    def extend_tool_results(self, results: list[ToolResult]) -> None:
        self.tool_results.extend(results)

    def full_text(self) -> str:
        return " ".join(chunk.text.strip() for chunk in self.chunks if not chunk.is_empty).strip()

    def speakable_chunks(self) -> list[AssistantChunk]:
        return [chunk for chunk in self.chunks if chunk.speak_now and not chunk.is_empty]


@dataclass(slots=True)
class VisionObservation:
    """
    Placeholder contract for the future camera stack.

    This is included now so the voice/dialogue layers can grow around a stable API.
    """

    detected: bool = False
    user_present: bool = False
    studying_likely: bool = False
    on_phone_likely: bool = False
    desk_active: bool = False
    labels: list[str] = field(default_factory=list)
    confidence: float = 0.0
    captured_at: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TurnContext:
    """Snapshot passed across the speech, understanding, and response pipeline."""

    transcript: TranscriptResult
    route: RouteDecision
    vision: VisionObservation | None = None
    memory_hints: list[str] = field(default_factory=list)
    user_profile: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def create_turn_id(prefix: str = "turn") -> str:
    """Return a short stable ID that is easy to log and trace."""

    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def normalize_text(text: str) -> str:
    """Normalize free-form user or assistant text for comparisons."""

    lowered = str(text or "").strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def clean_response_text(text: str) -> str:
    """Prepare assistant text before it becomes a stream chunk."""

    cleaned = str(text or "").strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return cleaned


def chunk_text_for_streaming(
    text: str,
    language: str,
    mode: StreamMode = StreamMode.SENTENCE,
    *,
    min_chunk_chars: int = 24,
) -> list[AssistantChunk]:
    """
    Convert assistant text into chunks suitable for premium low-latency TTS.

    Design goals:
    - sentence-first output rather than awkward token streaming
    - avoid tiny fragments unless the message is genuinely short
    - keep the function dependency-free and safe for Raspberry Pi use
    """

    cleaned = clean_response_text(text)
    if not cleaned:
        return []

    if mode == StreamMode.WHOLE_RESPONSE:
        return [AssistantChunk(text=cleaned, language=language, sequence_index=0)]

    if mode == StreamMode.PARAGRAPH:
        paragraphs = [part.strip() for part in re.split(r"\n{2,}", cleaned) if part.strip()]
        return [
            AssistantChunk(text=paragraph, language=language, sequence_index=index)
            for index, paragraph in enumerate(paragraphs)
        ]

    sentences = _split_into_sentences(cleaned)
    merged_sentences = _merge_short_sentences(sentences, min_chunk_chars=min_chunk_chars)

    return [
        AssistantChunk(text=sentence, language=language, sequence_index=index)
        for index, sentence in enumerate(merged_sentences)
    ]


def _split_into_sentences(text: str) -> list[str]:
    """
    Split text into clean sentence-like units.

    The regex is intentionally conservative.
    It respects the premium UX goal: speak natural chunks, not token soup.
    """

    protected = text
    protected = re.sub(
        r"\b(e\.g|i\.e|mr|mrs|ms|dr|prof)\.",
        lambda match: match.group(0).replace(".", "<DOT>"),
        protected,
        flags=re.IGNORECASE,
    )
    protected = re.sub(
        r"\b(np|itd|itp|dr|prof)\.",
        lambda match: match.group(0).replace(".", "<DOT>"),
        protected,
        flags=re.IGNORECASE,
    )
    protected = re.sub(r"(?<=\d)\.(?=\d)", "<DOT>", protected)

    parts = re.split(r"(?<=[.!?])\s+", protected)
    sentences = [part.replace("<DOT>", ".").strip() for part in parts if part and part.strip()]

    if sentences:
        return sentences

    fallback = clean_response_text(text)
    return [fallback] if fallback else []


def _merge_short_sentences(sentences: list[str], *, min_chunk_chars: int) -> list[str]:
    if not sentences:
        return []

    merged: list[str] = []
    buffer = ""

    for sentence in sentences:
        current = sentence.strip()
        if not current:
            continue

        if not buffer:
            buffer = current
            continue

        if len(buffer) < min_chunk_chars:
            buffer = f"{buffer} {current}".strip()
            continue

        merged.append(buffer)
        buffer = current

    if buffer:
        if merged and len(buffer) < max(12, min_chunk_chars // 2):
            merged[-1] = f"{merged[-1]} {buffer}".strip()
        else:
            merged.append(buffer)

    return merged