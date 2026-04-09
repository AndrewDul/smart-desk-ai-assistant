from __future__ import annotations

from dataclasses import dataclass, field

from .enums import ChunkKind, RouteKind, StreamMode
from .text import chunk_text_for_streaming, clean_response_text, normalize_text
from .understanding import ToolResult


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
    metadata: dict[str, object] = field(default_factory=dict)

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
    """

    turn_id: str
    language: str
    route_kind: RouteKind
    stream_mode: StreamMode = StreamMode.SENTENCE
    chunks: list[AssistantChunk] = field(default_factory=list)
    follow_up_suggestions: list[str] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def add_chunk(
        self,
        text: str,
        *,
        kind: ChunkKind = ChunkKind.CONTENT,
        speak_now: bool = True,
        flush: bool = True,
        metadata: dict[str, object] | None = None,
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


__all__ = [
    "AssistantChunk",
    "ResponsePlan",
]