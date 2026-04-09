from __future__ import annotations

from typing import Any

from modules.runtime.contracts import (
    AssistantChunk,
    ChunkKind,
    ResponsePlan,
    StreamMode,
    clean_response_text,
)

from .helpers import LOGGER, ResponseStreamerHelpers


class ResponseStreamerPreparation(ResponseStreamerHelpers):
    """Chunk preparation and merge logic for response streaming."""

    short_ack_max_chars: int
    short_follow_up_merge_max_chars: int
    action_merge_target_chars: int
    dialogue_merge_target_chars: int
    dialogue_max_chunk_chars: int
    fast_lead_min_chars: int
    fast_lead_max_chars: int

    def _prepare_chunks(self, plan: ResponsePlan) -> list[AssistantChunk]:
        raw_chunks = [chunk for chunk in plan.speakable_chunks() if clean_response_text(chunk.text)]
        if not raw_chunks:
            return []

        if plan.stream_mode == StreamMode.WHOLE_RESPONSE:
            merged_text = " ".join(clean_response_text(chunk.text) for chunk in raw_chunks).strip()
            if not merged_text:
                return []
            return [
                AssistantChunk(
                    text=merged_text,
                    language=raw_chunks[0].language,
                    kind=raw_chunks[0].kind,
                    speak_now=True,
                    flush=True,
                    sequence_index=0,
                    metadata={"merged_for_whole_response": True},
                )
            ]

        normalized_chunks = self._normalize_sequence_indexes(raw_chunks)
        route_kind = self._route_kind_value(plan)

        if route_kind in {"conversation", "mixed", "unclear"}:
            return self._prepare_dialogue_like_chunks(normalized_chunks)

        return self._prepare_action_like_chunks(normalized_chunks)

    def _prepare_dialogue_like_chunks(self, chunks: list[AssistantChunk]) -> list[AssistantChunk]:
        if not chunks:
            return []

        ack_chunk: AssistantChunk | None = None
        body_source_chunks = chunks

        first = chunks[0]
        first_text = clean_response_text(first.text)

        if first.kind == ChunkKind.ACK and first_text and len(first_text) <= self.short_ack_max_chars:
            ack_chunk = self._clone_chunk(first, sequence_index=0)
            body_source_chunks = chunks[1:]

        if not body_source_chunks:
            return [ack_chunk] if ack_chunk else []

        merged_body_chunks = self._merge_chunks_by_target(
            body_source_chunks,
            target_chars=self.dialogue_merge_target_chars,
            max_chars=self.dialogue_max_chunk_chars,
        )

        if merged_body_chunks:
            merged_body_chunks = self._split_fast_lead_from_first_content(merged_body_chunks)

        prepared: list[AssistantChunk] = []
        if ack_chunk is not None:
            prepared.append(self._clone_chunk(ack_chunk, sequence_index=len(prepared)))

        for chunk in merged_body_chunks:
            prepared.append(self._clone_chunk(chunk, sequence_index=len(prepared)))

        return prepared

    def _prepare_action_like_chunks(self, chunks: list[AssistantChunk]) -> list[AssistantChunk]:
        if not chunks:
            return []

        merged = self._merge_chunks_by_target(
            chunks,
            target_chars=self.action_merge_target_chars,
            max_chars=max(self.action_merge_target_chars, 175),
        )
        merged = self._merge_short_tail_follow_up(merged)

        prepared: list[AssistantChunk] = []
        for chunk in merged:
            prepared.append(self._clone_chunk(chunk, sequence_index=len(prepared)))

        return prepared

    def _merge_chunks_by_target(
        self,
        chunks: list[AssistantChunk],
        *,
        target_chars: int,
        max_chars: int,
    ) -> list[AssistantChunk]:
        merged: list[AssistantChunk] = []
        buffer_texts: list[str] = []
        buffer_language: str | None = None
        buffer_kind: ChunkKind | None = None
        buffer_metadata: dict[str, Any] = {}
        buffer_chars = 0

        def flush_buffer() -> None:
            nonlocal buffer_texts, buffer_language, buffer_kind, buffer_metadata, buffer_chars

            if not buffer_texts or not buffer_language or buffer_kind is None:
                buffer_texts = []
                buffer_language = None
                buffer_kind = None
                buffer_metadata = {}
                buffer_chars = 0
                return

            text = clean_response_text(" ".join(buffer_texts))
            if text:
                merged.append(
                    AssistantChunk(
                        text=text,
                        language=buffer_language,
                        kind=buffer_kind,
                        speak_now=True,
                        flush=True,
                        sequence_index=len(merged),
                        metadata=dict(buffer_metadata),
                    )
                )

            buffer_texts = []
            buffer_language = None
            buffer_kind = None
            buffer_metadata = {}
            buffer_chars = 0

        for chunk in chunks:
            text = clean_response_text(chunk.text)
            if not text:
                continue

            if chunk.kind == ChunkKind.ERROR:
                flush_buffer()
                merged.append(self._clone_chunk(chunk, sequence_index=len(merged)))
                continue

            if not buffer_texts:
                buffer_texts = [text]
                buffer_language = chunk.language
                buffer_kind = chunk.kind
                buffer_metadata = dict(chunk.metadata)
                buffer_chars = len(text)
                continue

            same_language = chunk.language == buffer_language
            compatible_kinds = self._kinds_can_merge(buffer_kind, chunk.kind)
            projected_chars = buffer_chars + 1 + len(text)

            should_merge = (
                same_language
                and compatible_kinds
                and (
                    projected_chars <= target_chars
                    or (len(buffer_texts) == 1 and projected_chars <= max_chars)
                )
            )

            if should_merge:
                buffer_texts.append(text)
                buffer_chars = projected_chars
                continue

            flush_buffer()

            buffer_texts = [text]
            buffer_language = chunk.language
            buffer_kind = chunk.kind
            buffer_metadata = dict(chunk.metadata)
            buffer_chars = len(text)

        flush_buffer()
        return merged

    def _merge_short_tail_follow_up(self, chunks: list[AssistantChunk]) -> list[AssistantChunk]:
        if len(chunks) < 2:
            return chunks

        merged: list[AssistantChunk] = []
        index = 0

        while index < len(chunks):
            current = chunks[index]

            if index < len(chunks) - 1:
                nxt = chunks[index + 1]
                current_text = clean_response_text(current.text)
                next_text = clean_response_text(nxt.text)

                if (
                    current.language == nxt.language
                    and current.kind in {ChunkKind.CONTENT, ChunkKind.TOOL_STATUS}
                    and nxt.kind == ChunkKind.FOLLOW_UP
                    and next_text
                    and len(next_text) <= self.short_follow_up_merge_max_chars
                ):
                    merged.append(
                        AssistantChunk(
                            text=f"{current_text} {next_text}".strip(),
                            language=current.language,
                            kind=current.kind,
                            speak_now=True,
                            flush=True,
                            sequence_index=len(merged),
                            metadata={
                                **dict(current.metadata),
                                "merged_short_follow_up": True,
                            },
                        )
                    )
                    index += 2
                    continue

            merged.append(self._clone_chunk(current, sequence_index=len(merged)))
            index += 1

        return merged

    def _split_fast_lead_from_first_content(self, chunks: list[AssistantChunk]) -> list[AssistantChunk]:
        if not chunks:
            return []

        first = chunks[0]
        if first.kind not in {ChunkKind.CONTENT, ChunkKind.TOOL_STATUS, ChunkKind.FOLLOW_UP}:
            return chunks

        first_text = clean_response_text(first.text)
        if len(first_text) < 95:
            return chunks

        lead_and_body = self._extract_fast_lead(first_text)
        if lead_and_body is None:
            return chunks

        lead_text, body_text = lead_and_body
        if not lead_text or not body_text:
            return chunks

        rebuilt: list[AssistantChunk] = [
            AssistantChunk(
                text=lead_text,
                language=first.language,
                kind=first.kind,
                speak_now=True,
                flush=True,
                sequence_index=0,
                metadata={
                    **dict(first.metadata),
                    "fast_lead_chunk": True,
                },
            ),
            AssistantChunk(
                text=body_text,
                language=first.language,
                kind=first.kind,
                speak_now=True,
                flush=True,
                sequence_index=1,
                metadata={
                    **dict(first.metadata),
                    "post_fast_lead_chunk": True,
                },
            ),
        ]

        for chunk in chunks[1:]:
            rebuilt.append(self._clone_chunk(chunk, sequence_index=len(rebuilt)))

        LOGGER.info(
            "Fast lead split applied: lead_chars=%s, body_chars=%s",
            len(lead_text),
            len(body_text),
        )
        return rebuilt

    def _extract_fast_lead(self, text: str) -> tuple[str, str] | None:
        cleaned = clean_response_text(text)
        if not cleaned:
            return None

        sentence_parts = self._sentence_units(cleaned)
        if len(sentence_parts) < 2:
            return None

        first_sentence = sentence_parts[0]
        remainder = clean_response_text(" ".join(sentence_parts[1:]))

        if not remainder:
            return None

        if not (self.fast_lead_min_chars <= len(first_sentence) <= self.fast_lead_max_chars):
            return None

        return first_sentence, remainder


__all__ = ["ResponseStreamerPreparation"]