from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from modules.runtime.contracts import (
    AssistantChunk,
    ChunkKind,
    ResponsePlan,
    StreamMode,
    clean_response_text,
)

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class StreamExecutionReport:
    chunks_spoken: int
    full_text: str
    display_title: str
    display_lines: list[str]


class ResponseStreamer:
    """
    Premium low-pause response streamer for NeXa.

    Design goals:
    - minimize audible latency before first useful speech
    - reduce long pauses between spoken chunks
    - keep OLED/LCD output short, stable, and legible
    - prewarm likely next TTS chunk when possible
    - remain interruption-aware throughout the whole response flow
    """

    def __init__(
        self,
        *,
        voice_output: Any,
        display: Any,
        default_display_seconds: float = 10.0,
        inter_chunk_pause_seconds: float = 0.0,
        max_display_lines: int = 2,
        max_display_chars_per_line: int = 20,
        interrupt_requested: Any | None = None,
    ) -> None:
        self.voice_output = voice_output
        self.display = display
        self.default_display_seconds = float(default_display_seconds)
        self.inter_chunk_pause_seconds = max(0.0, float(inter_chunk_pause_seconds))
        self.max_display_lines = max(1, int(max_display_lines))
        self.max_display_chars_per_line = max(8, int(max_display_chars_per_line))
        self.interrupt_requested = interrupt_requested

        self.short_ack_max_chars = 28
        self.short_follow_up_merge_max_chars = 46
        self.action_merge_target_chars = 150
        self.dialogue_merge_target_chars = 210
        self.dialogue_max_chunk_chars = 260
        self.prefetch_max_chars = 220
        self.fast_lead_min_chars = 10
        self.fast_lead_max_chars = 44

    def execute(self, plan: ResponsePlan) -> StreamExecutionReport:
        prepared_chunks = self._prepare_chunks(plan)
        display_title, display_lines = self._resolve_display_content(plan, prepared_chunks)

        if not prepared_chunks:
            self._show_display_block(display_title, display_lines)
            return StreamExecutionReport(
                chunks_spoken=0,
                full_text="",
                display_title=display_title,
                display_lines=display_lines,
            )

        spoken_count = 0
        full_text_parts: list[str] = []
        response_started_at = time.monotonic()

        defer_display_until_after_first = self._should_defer_display_until_after_first(prepared_chunks)
        display_shown = False

        if not defer_display_until_after_first:
            display_shown = self._show_display_block(display_title, display_lines)

        for index, chunk in enumerate(prepared_chunks):
            if self._interrupted():
                LOGGER.info("Response stream interrupted before chunk index=%s.", index)
                break

            text = clean_response_text(chunk.text)
            if not text:
                continue

            next_hint = self._next_prefetch_payload(prepared_chunks, index + 1)
            self._prepare_next_chunk(next_hint)

            speak_started_at = time.monotonic()
            spoken_ok = self._speak_chunk(chunk, text, next_hint=next_hint)
            speak_elapsed = time.monotonic() - speak_started_at

            if not spoken_ok:
                if self._interrupted():
                    LOGGER.info("Response stream interrupted during chunk index=%s.", index)
                    break

                LOGGER.warning(
                    "Response stream failed to speak chunk index=%s, kind=%s, chars=%s",
                    index,
                    chunk.kind.value,
                    len(text),
                )
                continue

            spoken_count += 1
            full_text_parts.append(text)

            if defer_display_until_after_first and not display_shown:
                display_shown = self._show_display_block(display_title, display_lines)

            LOGGER.info(
                "Response chunk spoken: index=%s, kind=%s, chars=%s, elapsed=%.3fs",
                index,
                chunk.kind.value,
                len(text),
                speak_elapsed,
            )

            pause_seconds = self._pause_after_chunk(
                previous_chunk=chunk,
                next_chunk=prepared_chunks[index + 1] if index + 1 < len(prepared_chunks) else None,
                is_last=index == len(prepared_chunks) - 1,
            )
            if pause_seconds > 0 and not self._sleep_interruptibly(pause_seconds):
                LOGGER.info(
                    "Response stream interrupted during inter-chunk pause after index=%s.",
                    index,
                )
                break

        if not display_shown:
            self._show_display_block(display_title, display_lines)

        full_text = " ".join(full_text_parts).strip()
        total_elapsed = time.monotonic() - response_started_at

        LOGGER.info(
            "Response plan executed: turn_id=%s, route_kind=%s, stream_mode=%s, "
            "spoken_chunks=%s, chunk_kinds=%s, display_deferred=%s, total_elapsed=%.3fs",
            plan.turn_id,
            self._route_kind_value(plan),
            self._stream_mode_value(plan),
            spoken_count,
            [chunk.kind.value for chunk in prepared_chunks],
            defer_display_until_after_first,
            total_elapsed,
        )

        return StreamExecutionReport(
            chunks_spoken=spoken_count,
            full_text=full_text,
            display_title=display_title,
            display_lines=display_lines,
        )

    def preview_display(self, plan: ResponsePlan) -> tuple[str, list[str]]:
        prepared_chunks = self._prepare_chunks(plan)
        return self._resolve_display_content(plan, prepared_chunks)

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

    def _resolve_display_content(
        self,
        plan: ResponsePlan,
        prepared_chunks: list[AssistantChunk],
    ) -> tuple[str, list[str]]:
        metadata = dict(plan.metadata or {})

        title = clean_response_text(str(metadata.get("display_title", "")).strip())
        if not title:
            title = self._fallback_display_title(plan)

        explicit_lines = metadata.get("display_lines")
        if isinstance(explicit_lines, list):
            cleaned_lines = [
                clean_response_text(str(line))
                for line in explicit_lines
                if clean_response_text(str(line))
            ]
            if cleaned_lines:
                return title, cleaned_lines[: self.max_display_lines]

        generated_lines = self._build_display_lines_from_chunks(prepared_chunks)
        return title, generated_lines

    def _fallback_display_title(self, plan: ResponsePlan) -> str:
        route_kind = self._route_kind_value(plan)

        if route_kind == "action":
            return "ACTION"
        if route_kind == "mixed":
            return "ASSISTANT"
        if route_kind == "conversation":
            return "CHAT"
        if route_kind == "unclear":
            return "UNCLEAR"
        return "NEXA"

    def _build_display_lines_from_chunks(self, chunks: list[AssistantChunk]) -> list[str]:
        if not chunks:
            return []

        text_pool = " ".join(
            clean_response_text(chunk.text)
            for chunk in chunks
            if clean_response_text(chunk.text)
        )
        if not text_pool:
            return []

        candidate_units = self._sentence_units(text_pool)
        if not candidate_units:
            candidate_units = [text_pool]

        lines: list[str] = []
        for unit in candidate_units:
            compact = clean_response_text(unit)
            if not compact:
                continue

            if len(compact) <= self.max_display_chars_per_line:
                lines.append(compact)
            else:
                shortened = compact[: self.max_display_chars_per_line - 3].rstrip() + "..."
                lines.append(shortened)

            if len(lines) >= self.max_display_lines:
                break

        return lines

    def _show_display_block(self, title: str, lines: list[str]) -> bool:
        if not title or not lines:
            return False

        show_block = getattr(self.display, "show_block", None)
        if callable(show_block):
            try:
                show_block(title, lines, duration=self.default_display_seconds)
                return True
            except Exception as error:
                LOGGER.warning("Display show_block failed: %s", error)
                return False

        return False

    def _next_prefetch_payload(
        self,
        chunks: list[AssistantChunk],
        start_index: int,
    ) -> tuple[str, str] | None:
        for index in range(start_index, len(chunks)):
            candidate = chunks[index]
            text = clean_response_text(candidate.text)
            if not text:
                continue
            if len(text) > self.prefetch_max_chars:
                return None
            return text, candidate.language
        return None

    def _prepare_next_chunk(self, next_hint: tuple[str, str] | None) -> None:
        if next_hint is None:
            return

        prepare_method = getattr(self.voice_output, "prepare_speech", None)
        if not callable(prepare_method):
            return

        try:
            prepare_method(next_hint[0], next_hint[1])
        except Exception as error:
            LOGGER.warning("Response stream prepare warning: %s", error)

    def _speak_chunk(
        self,
        chunk: AssistantChunk,
        text: str,
        *,
        next_hint: tuple[str, str] | None = None,
    ) -> bool:
        speak_method = getattr(self.voice_output, "speak", None)
        if not callable(speak_method):
            return False

        try:
            return bool(
                speak_method(
                    text,
                    language=chunk.language,
                    prepare_next=next_hint,
                )
            )
        except TypeError:
            try:
                return bool(speak_method(text, language=chunk.language))
            except TypeError:
                return bool(speak_method(text))

    def _should_defer_display_until_after_first(self, chunks: list[AssistantChunk]) -> bool:
        if not chunks:
            return False

        first = chunks[0]
        first_text = clean_response_text(first.text)
        return first.kind == ChunkKind.ACK and len(first_text) <= self.short_ack_max_chars

    def _pause_after_chunk(
        self,
        *,
        previous_chunk: AssistantChunk,
        next_chunk: AssistantChunk | None,
        is_last: bool,
    ) -> float:
        del next_chunk

        if is_last:
            return 0.0

        if previous_chunk.kind in {
            ChunkKind.ACK,
            ChunkKind.CONTENT,
            ChunkKind.TOOL_STATUS,
            ChunkKind.FOLLOW_UP,
            ChunkKind.FINAL,
        }:
            return min(self.inter_chunk_pause_seconds, 0.01)

        if previous_chunk.kind == ChunkKind.ERROR:
            return min(max(self.inter_chunk_pause_seconds, 0.0), 0.03)

        return 0.0

    def _interrupted(self) -> bool:
        if not callable(self.interrupt_requested):
            return False

        try:
            return bool(self.interrupt_requested())
        except Exception:
            return False

    def _sleep_interruptibly(self, seconds: float) -> bool:
        remaining = max(0.0, float(seconds))
        step = 0.01

        while remaining > 0:
            if self._interrupted():
                return False
            interval = min(step, remaining)
            time.sleep(interval)
            remaining -= interval

        return True

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


__all__ = ["ResponseStreamer", "StreamExecutionReport"]