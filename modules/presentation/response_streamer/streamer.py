from __future__ import annotations

import time
from typing import Any

from modules.runtime.contracts import ChunkKind, ResponsePlan, clean_response_text

from .display import ResponseStreamerDisplay
from .helpers import LOGGER
from .live_stream import ResponseStreamerLiveStream
from .models import StreamExecutionReport
from .playback import ResponseStreamerPlayback
from .preparation import ResponseStreamerPreparation


class ResponseStreamer(
    ResponseStreamerPreparation,
    ResponseStreamerDisplay,
    ResponseStreamerPlayback,
    ResponseStreamerLiveStream,
):
    """
    Premium low-pause response streamer for NeXa.
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

        self.short_ack_max_chars = 24
        self.short_follow_up_merge_max_chars = 34
        self.action_merge_target_chars = 132
        self.dialogue_merge_target_chars = 168
        self.dialogue_max_chunk_chars = 210
        self.prefetch_max_chars = 150
        self.fast_lead_min_chars = 8
        self.fast_lead_max_chars = 34

    def execute(self, plan: ResponsePlan) -> StreamExecutionReport:
        if self._has_live_chunk_source(plan):
            return self._execute_live_stream(plan)

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
        first_audio_latency_s: float | None = None
        first_sentence_latency_s: float | None = None

        defer_display_until_after_first = self._should_defer_display_until_after_first(
            plan,
            prepared_chunks,
        )
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
            latency_profile = self._resolve_latency_profile(
                plan=plan,
                chunk=chunk,
                chunk_count=len(prepared_chunks),
            )

            speak_started_at = time.monotonic()
            spoken_ok = self._speak_chunk(
                chunk,
                text,
                next_hint=next_hint,
                latency_profile=latency_profile,
            )
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
            actual_first_audio_started_at = self._resolve_chunk_first_audio_started_at(
                speak_call_started_at=speak_started_at,
            )

            if first_audio_latency_s is None:
                first_audio_latency_s = max(0.0, actual_first_audio_started_at - response_started_at)

            if first_sentence_latency_s is None and chunk.kind in {ChunkKind.CONTENT, ChunkKind.FOLLOW_UP}:
                first_sentence_latency_s = max(0.0, actual_first_audio_started_at - response_started_at)
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

        if first_sentence_latency_s is None and first_audio_latency_s is not None:
            first_sentence_latency_s = first_audio_latency_s

        full_text = " ".join(full_text_parts).strip()
        total_elapsed = time.monotonic() - response_started_at

        LOGGER.info(
            "Response plan executed: turn_id=%s, route_kind=%s, stream_mode=%s, "
            "spoken_chunks=%s, chunk_kinds=%s, display_deferred=%s, "
            "first_audio_latency=%.3fs, first_sentence_latency=%.3fs, total_elapsed=%.3fs",
            plan.turn_id,
            self._route_kind_value(plan),
            self._stream_mode_value(plan),
            spoken_count,
            [chunk.kind.value for chunk in prepared_chunks],
            defer_display_until_after_first,
            first_audio_latency_s if first_audio_latency_s is not None else -1.0,
            first_sentence_latency_s if first_sentence_latency_s is not None else -1.0,
            total_elapsed,
        )

        finished_at = time.monotonic()
        return StreamExecutionReport(
            chunks_spoken=spoken_count,
            full_text=full_text,
            display_title=display_title,
            display_lines=display_lines,
            first_audio_latency_ms=(first_audio_latency_s or 0.0) * 1000.0,
            first_chunk_latency_ms=0.0,
            first_sentence_latency_ms=(first_sentence_latency_s or 0.0) * 1000.0,
            total_elapsed_ms=total_elapsed * 1000.0,
            started_at_monotonic=response_started_at,
            first_audio_started_at_monotonic=(
                response_started_at + first_audio_latency_s
                if first_audio_latency_s is not None
                else 0.0
            ),
            first_chunk_started_at_monotonic=0.0,
            first_sentence_started_at_monotonic=(
                response_started_at + first_sentence_latency_s
                if first_sentence_latency_s is not None
                else 0.0
            ),
            finished_at_monotonic=finished_at,
            chunk_kinds=[chunk.kind.value for chunk in prepared_chunks],
            live_streaming=False,
        )

    def preview_display(self, plan: ResponsePlan) -> tuple[str, list[str]]:
        prepared_chunks = self._prepare_chunks(plan)
        return self._resolve_display_content(plan, prepared_chunks)


__all__ = ["ResponseStreamer"]