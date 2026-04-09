from __future__ import annotations

import time
from typing import Any

from modules.runtime.contracts import ResponsePlan, clean_response_text

from .display import ResponseStreamerDisplay
from .helpers import LOGGER
from .models import StreamExecutionReport
from .playback import ResponseStreamerPlayback
from .preparation import ResponseStreamerPreparation


class ResponseStreamer(
    ResponseStreamerPreparation,
    ResponseStreamerDisplay,
    ResponseStreamerPlayback,
):
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


__all__ = ["ResponseStreamer"]