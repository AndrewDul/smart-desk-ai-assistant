from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from modules.runtime_contracts import AssistantChunk, ChunkKind, ResponsePlan, StreamMode, clean_response_text
from modules.system.utils import append_log


@dataclass(slots=True)
class StreamExecutionReport:
    chunks_spoken: int
    full_text: str
    display_title: str
    display_lines: list[str]


class StreamingResponseService:
    """
    Executes a ResponsePlan in a premium-friendly way.

    Current goals:
    - keep short ACK chunks as quick first reactions
    - reduce the feeling of waiting between chunks
    - avoid unnecessary extra TTS calls for tiny tail follow-ups
    - keep OLED/display summaries focused on content, not filler
    """

    def __init__(
        self,
        *,
        voice_output: Any,
        display: Any,
        default_display_seconds: float = 10.0,
        inter_chunk_pause_seconds: float = 0.05,
        max_display_lines: int = 2,
        max_display_chars_per_line: int = 20,
    ) -> None:
        self.voice_output = voice_output
        self.display = display
        self.default_display_seconds = float(default_display_seconds)
        self.inter_chunk_pause_seconds = max(0.0, float(inter_chunk_pause_seconds))
        self.max_display_lines = max(1, int(max_display_lines))
        self.max_display_chars_per_line = max(8, int(max_display_chars_per_line))

        self.fast_ack_max_chars = 28
        self.short_tail_follow_up_max_chars = 42

    def execute(self, plan: ResponsePlan) -> StreamExecutionReport:
        prepared_chunks = self._prepare_chunks(plan)
        display_title, display_lines = self._resolve_display_content(plan, prepared_chunks)

        spoken_count = 0
        full_text_parts: list[str] = []

        display_shown = False
        voice_lead_start = self._should_use_voice_lead_start(prepared_chunks)

        for index, chunk in enumerate(prepared_chunks):
            text = clean_response_text(chunk.text)
            if not text:
                continue

            if not display_shown:
                if voice_lead_start and index == 0:
                    # Let a short ACK reach the user immediately before touching the display.
                    pass
                elif display_title and display_lines:
                    self.display.show_block(
                        display_title,
                        display_lines,
                        duration=self.default_display_seconds,
                    )
                    display_shown = True

            self.voice_output.speak(text, language=chunk.language)
            full_text_parts.append(text)
            spoken_count += 1

            if voice_lead_start and index == 0 and not display_shown:
                if display_title and display_lines:
                    self.display.show_block(
                        display_title,
                        display_lines,
                        duration=self.default_display_seconds,
                    )
                display_shown = True

            pause_seconds = self._pause_after_chunk(
                previous_chunk=chunk,
                next_chunk=prepared_chunks[index + 1] if index + 1 < len(prepared_chunks) else None,
                is_last=index == len(prepared_chunks) - 1,
            )
            if pause_seconds > 0:
                time.sleep(pause_seconds)

        if not display_shown and display_title and display_lines:
            self.display.show_block(
                display_title,
                display_lines,
                duration=self.default_display_seconds,
            )

        full_text = " ".join(full_text_parts).strip()

        append_log(
            f"Response plan executed: turn_id={plan.turn_id}, route_kind={plan.route_kind.value}, "
            f"stream_mode={plan.stream_mode.value}, spoken_chunks={spoken_count}, "
            f"chunk_kinds={[chunk.kind.value for chunk in prepared_chunks]}, "
            f"voice_lead_start={voice_lead_start}"
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
        chunks = [chunk for chunk in plan.speakable_chunks() if clean_response_text(chunk.text)]

        if not chunks:
            return []

        if plan.stream_mode == StreamMode.WHOLE_RESPONSE:
            merged_text = " ".join(clean_response_text(chunk.text) for chunk in chunks).strip()
            if not merged_text:
                return []

            return [
                AssistantChunk(
                    text=merged_text,
                    language=plan.language,
                    kind=chunks[0].kind,
                    speak_now=True,
                    flush=True,
                    sequence_index=0,
                    metadata={"merged_for_whole_response": True},
                )
            ]

        normalized_chunks = self._normalize_sequence_indexes(chunks)
        normalized_chunks = self._merge_tiny_leading_chunks(normalized_chunks)
        normalized_chunks = self._merge_short_tail_follow_up(normalized_chunks)
        return normalized_chunks

    def _normalize_sequence_indexes(self, chunks: list[AssistantChunk]) -> list[AssistantChunk]:
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

    def _merge_tiny_leading_chunks(self, chunks: list[AssistantChunk]) -> list[AssistantChunk]:
        """
        Merge only when doing so improves flow.

        Important rule:
        - preserve short ACK chunks as separate quick reactions
        - only merge tiny first chunk when both chunks are content-like
        """

        if len(chunks) < 2:
            return chunks

        first = chunks[0]
        second = chunks[1]

        first_text = clean_response_text(first.text)
        second_text = clean_response_text(second.text)

        if not first_text or not second_text:
            return chunks

        if not self._should_merge_leading_chunks(first, second, first_text):
            return chunks

        merged_first = AssistantChunk(
            text=f"{first_text} {second_text}".strip(),
            language=first.language,
            kind=second.kind,
            speak_now=True,
            flush=True,
            sequence_index=0,
            metadata={
                "merged_leading_chunks": True,
                "original_first_kind": first.kind.value,
                "original_second_kind": second.kind.value,
            },
        )

        remainder = chunks[2:]
        normalized_remainder: list[AssistantChunk] = [merged_first]

        for index, chunk in enumerate(remainder, start=1):
            normalized_remainder.append(
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

        return normalized_remainder

    def _should_merge_leading_chunks(
        self,
        first: AssistantChunk,
        second: AssistantChunk,
        first_text: str,
    ) -> bool:
        if first.language != second.language:
            return False

        if len(first_text) > 18:
            return False

        if first.kind != second.kind:
            return False

        if first.kind in {ChunkKind.ACK, ChunkKind.FOLLOW_UP, ChunkKind.ERROR, ChunkKind.TOOL_STATUS}:
            return False

        return True

    def _merge_short_tail_follow_up(self, chunks: list[AssistantChunk]) -> list[AssistantChunk]:
        """
        Reduce extra TTS round-trips when a very short follow-up is attached
        after the main content and clearly belongs to the same reply.
        """

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

                if self._should_merge_tail_follow_up(current, nxt, current_text, next_text):
                    merged.append(
                        AssistantChunk(
                            text=f"{current_text} {next_text}".strip(),
                            language=current.language,
                            kind=current.kind,
                            speak_now=True,
                            flush=True,
                            sequence_index=len(merged),
                            metadata={
                                "merged_tail_follow_up": True,
                                "original_current_kind": current.kind.value,
                                "original_next_kind": nxt.kind.value,
                            },
                        )
                    )
                    index += 2
                    continue

            merged.append(
                AssistantChunk(
                    text=current.text,
                    language=current.language,
                    kind=current.kind,
                    speak_now=current.speak_now,
                    flush=current.flush,
                    sequence_index=len(merged),
                    metadata=dict(current.metadata),
                )
            )
            index += 1

        return merged

    def _should_merge_tail_follow_up(
        self,
        current: AssistantChunk,
        nxt: AssistantChunk,
        current_text: str,
        next_text: str,
    ) -> bool:
        if not current_text or not next_text:
            return False

        if current.language != nxt.language:
            return False

        if current.kind not in {ChunkKind.CONTENT, ChunkKind.TOOL_STATUS}:
            return False

        if nxt.kind != ChunkKind.FOLLOW_UP:
            return False

        if len(next_text) > self.short_tail_follow_up_max_chars:
            return False

        if len(current_text) < 18:
            return False

        return True

    def _should_use_voice_lead_start(self, chunks: list[AssistantChunk]) -> bool:
        """
        Start with voice before display only for short ACK-first replies.
        This improves perceived responsiveness on Raspberry Pi without changing content.
        """

        if len(chunks) < 2:
            return False

        first = chunks[0]
        first_text = clean_response_text(first.text)

        if first.kind != ChunkKind.ACK:
            return False

        if len(first_text) > self.fast_ack_max_chars:
            return False

        return True

    def _pause_after_chunk(
        self,
        *,
        previous_chunk: AssistantChunk,
        next_chunk: AssistantChunk | None,
        is_last: bool,
    ) -> float:
        if is_last:
            return 0.0

        base_pause = min(self.inter_chunk_pause_seconds, 0.04)

        if previous_chunk.kind == ChunkKind.ACK:
            if next_chunk and next_chunk.kind in {ChunkKind.CONTENT, ChunkKind.TOOL_STATUS, ChunkKind.FOLLOW_UP}:
                return 0.02
            return 0.05

        if previous_chunk.kind == ChunkKind.FOLLOW_UP:
            return 0.01

        if previous_chunk.kind == ChunkKind.ERROR:
            return 0.03

        if previous_chunk.kind == ChunkKind.TOOL_STATUS:
            return 0.02

        return base_pause

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
        route_kind = plan.route_kind.value

        if route_kind == "mixed":
            return "SUPPORT"
        if route_kind == "action":
            return "ACTION"
        if route_kind == "unclear":
            return "CLARIFY"
        return "CHAT"

    def _build_display_lines_from_chunks(self, chunks: list[AssistantChunk]) -> list[str]:
        if not chunks:
            return []

        preferred_chunks = self._display_preferred_chunks(chunks)
        collected: list[str] = []

        for chunk in preferred_chunks:
            text = clean_response_text(chunk.text)
            if not text:
                continue

            sentence_parts = self._split_for_display(text)

            for part in sentence_parts:
                shortened = self._shorten_for_display(part)
                if shortened:
                    collected.append(shortened)

                if len(collected) >= self.max_display_lines:
                    return collected

        return collected[: self.max_display_lines]

    def _display_preferred_chunks(self, chunks: list[AssistantChunk]) -> list[AssistantChunk]:
        content_like = [
            chunk
            for chunk in chunks
            if chunk.kind in {ChunkKind.CONTENT, ChunkKind.FOLLOW_UP, ChunkKind.TOOL_STATUS}
        ]
        if content_like:
            return content_like
        return chunks

    @staticmethod
    def _split_for_display(text: str) -> list[str]:
        separators = [". ", "! ", "? ", ", ", "; ", ": "]
        parts = [text]

        for separator in separators:
            updated: list[str] = []
            for part in parts:
                updated.extend(segment.strip() for segment in part.split(separator) if segment.strip())
            parts = updated

        return [part.strip() for part in parts if part.strip()]

    def _shorten_for_display(self, text: str) -> str:
        cleaned = clean_response_text(text)
        if not cleaned:
            return ""

        if len(cleaned) <= self.max_display_chars_per_line:
            return cleaned

        shortened = cleaned[: self.max_display_chars_per_line].rstrip()
        if shortened.endswith((" ", ".", ",", ";", ":")):
            shortened = shortened.rstrip(" .,:;")

        return f"{shortened}..."