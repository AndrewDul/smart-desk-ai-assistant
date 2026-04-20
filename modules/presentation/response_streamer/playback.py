from __future__ import annotations

import inspect
import time
from typing import Any

from modules.runtime.contracts import AssistantChunk, ChunkKind, clean_response_text

from .helpers import LOGGER, ResponseStreamerHelpers


class ResponseStreamerPlayback(ResponseStreamerHelpers):
    """Speech playback, prefetch, pause, and interruption helpers."""

    voice_output: Any
    interrupt_requested: Any | None
    inter_chunk_pause_seconds: float
    prefetch_max_chars: int
    short_ack_max_chars: int

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

        # Important:
        # If the voice_output.speak(...) method already accepts prepare_next,
        # we do NOT prefetch here to avoid doing the same work twice.
        if self._voice_output_supports_prepare_next():
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

        started_at = time.monotonic()

        try:
            if self._voice_output_supports_prepare_next():
                result = bool(
                    speak_method(
                        text,
                        language=chunk.language,
                        prepare_next=next_hint,
                    )
                )
            else:
                result = bool(speak_method(text, language=chunk.language))
        except TypeError:
            try:
                result = bool(speak_method(text, language=chunk.language))
            except TypeError:
                result = bool(speak_method(text))
        except Exception as error:
            LOGGER.warning("Response stream speak warning: %s", error)
            return False

        LOGGER.info(
            "Response stream speak call finished: kind=%s, chars=%s, success=%s, elapsed=%.3fs",
            chunk.kind.value,
            len(text),
            result,
            time.monotonic() - started_at,
        )
        return result

    def _resolve_chunk_first_audio_started_at(
        self,
        *,
        speak_call_started_at: float,
    ) -> float:
        report_method = getattr(self.voice_output, "latest_speak_report", None)
        if not callable(report_method):
            return speak_call_started_at

        try:
            report = dict(report_method() or {})
        except Exception:
            return speak_call_started_at

        try:
            value = float(report.get("first_audio_started_at_monotonic", 0.0) or 0.0)
        except (TypeError, ValueError):
            return speak_call_started_at

        if value <= 0.0:
            return speak_call_started_at

        return max(speak_call_started_at, value)






    def _voice_output_supports_prepare_next(self) -> bool:
        speak_method = getattr(self.voice_output, "speak", None)
        if not callable(speak_method):
            return False

        cached = getattr(self, "_supports_prepare_next_cache", None)
        if isinstance(cached, bool):
            return cached

        try:
            signature = inspect.signature(speak_method)
            supports = "prepare_next" in signature.parameters
        except Exception:
            supports = False

        self._supports_prepare_next_cache = supports
        return supports

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


__all__ = ["ResponseStreamerPlayback"]