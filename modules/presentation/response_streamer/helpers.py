from __future__ import annotations

import logging
import re

from modules.runtime.contracts import (
    AssistantChunk,
    ChunkKind,
    ResponsePlan,
    clean_response_text,
)

LOGGER = logging.getLogger(__name__)


class ResponseStreamerHelpers:
    """Shared helper methods for response streaming."""

    @staticmethod
    def _clone_chunk(chunk: AssistantChunk, *, sequence_index: int) -> AssistantChunk:
        return AssistantChunk(
            text=chunk.text,
            language=chunk.language,
            kind=chunk.kind,
            speak_now=chunk.speak_now,
            flush=chunk.flush,
            sequence_index=sequence_index,
            metadata=dict(chunk.metadata),
        )

    @staticmethod
    def _kinds_can_merge(left: ChunkKind | None, right: ChunkKind) -> bool:
        if left is None:
            return True

        mergeable = {
            ChunkKind.ACK,
            ChunkKind.CONTENT,
            ChunkKind.TOOL_STATUS,
            ChunkKind.FOLLOW_UP,
            ChunkKind.FINAL,
        }

        if left not in mergeable or right not in mergeable:
            return False

        if left == ChunkKind.ERROR or right == ChunkKind.ERROR:
            return False

        return True

    @staticmethod
    def _sentence_units(text: str) -> list[str]:
        cleaned = clean_response_text(text)
        if not cleaned:
            return []

        parts = re.split(r"(?<=[.!?])\s+", cleaned)
        return [clean_response_text(part) for part in parts if clean_response_text(part)]

    @staticmethod
    def _normalize_sequence_indexes(chunks: list[AssistantChunk]) -> list[AssistantChunk]:
        normalized: list[AssistantChunk] = []
        for index, chunk in enumerate(chunks):
            normalized.append(
                AssistantChunk(
                    text=chunk.text,
                    language=chunk.language,
                    kind=chunk.kind,
                    speak_now=chunk.speak_now,
                    flush=chunk.flush,
                    sequence_index=index,
                    metadata=dict(chunk.metadata),
                )
            )
        return normalized

    @staticmethod
    def _route_kind_value(plan: ResponsePlan) -> str:
        route_kind = getattr(plan, "route_kind", "")
        return getattr(route_kind, "value", str(route_kind))

    @staticmethod
    def _stream_mode_value(plan: ResponsePlan) -> str:
        stream_mode = getattr(plan, "stream_mode", "")
        return getattr(stream_mode, "value", str(stream_mode))


__all__ = ["LOGGER", "ResponseStreamerHelpers"]