from __future__ import annotations

import time
from collections.abc import Iterable, Iterator
from typing import Any

from modules.runtime.contracts import AssistantChunk, ChunkKind, ResponsePlan, clean_response_text

from .helpers import LOGGER, ResponseStreamerHelpers
from .models import StreamExecutionReport


class ResponseStreamerLiveStream(ResponseStreamerHelpers):
    interrupt_requested: Any | None

    def _has_live_chunk_source(self, plan: ResponsePlan) -> bool:
        metadata = dict(getattr(plan, "metadata", {}) or {})
        return callable(metadata.get("live_chunk_factory"))

    @staticmethod
    def _is_sentence_chunk_kind(kind: ChunkKind | Any) -> bool:
        return kind in {ChunkKind.CONTENT, ChunkKind.FOLLOW_UP}

    @staticmethod
    def _chunk_first_latency_ms(chunk: AssistantChunk) -> float:
        metadata = dict(getattr(chunk, "metadata", {}) or {})
        try:
            return max(0.0, float(metadata.get("first_chunk_latency_ms", 0.0) or 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _execute_live_stream(self, plan: ResponsePlan) -> StreamExecutionReport:
        prepared_chunks = self._prepare_chunks(plan)
        display_title, display_lines = self._resolve_display_content(plan, prepared_chunks)
        live_chunks = self._iter_live_chunks(plan)

        response_started_at = time.monotonic()
        first_audio_latency_s: float | None = None
        first_sentence_latency_s: float | None = None
        first_chunk_latency_ms = 0.0
        first_chunk_started_at_monotonic = 0.0

        spoken_count = 0
        full_text_parts: list[str] = []
        dynamic_display_pool: list[str] = list(display_lines)
        display_shown = False
        chunk_kinds: list[str] = []

        def _track_spoken_chunk(chunk: AssistantChunk) -> None:
            nonlocal first_audio_latency_s
            nonlocal first_sentence_latency_s
            nonlocal first_chunk_latency_ms
            nonlocal first_chunk_started_at_monotonic

            spoken_at = time.monotonic()

            if first_audio_latency_s is None:
                first_audio_latency_s = spoken_at - response_started_at

            chunk_first_latency_ms = self._chunk_first_latency_ms(chunk)
            if first_chunk_latency_ms <= 0.0 and chunk_first_latency_ms > 0.0:
                first_chunk_latency_ms = chunk_first_latency_ms
                first_chunk_started_at_monotonic = (
                    response_started_at + (chunk_first_latency_ms / 1000.0)
                )

            if first_sentence_latency_s is None and self._is_sentence_chunk_kind(chunk.kind):
                first_sentence_latency_s = spoken_at - response_started_at

        for chunk in prepared_chunks:
            spoken_ok = self._speak_live_chunk(chunk)
            if not spoken_ok:
                if self._interrupted():
                    break
                continue

            spoken_count += 1
            chunk_kinds.append(chunk.kind.value)
            cleaned = clean_response_text(chunk.text)
            if cleaned:
                full_text_parts.append(cleaned)
                self._extend_dynamic_display_pool(dynamic_display_pool, cleaned)

            _track_spoken_chunk(chunk)

            if not display_shown:
                display_shown = self._show_display_block(
                    display_title,
                    self._resolve_live_display_lines(dynamic_display_pool),
                )

        for chunk in live_chunks:
            if self._interrupted():
                break

            spoken_ok = self._speak_live_chunk(chunk)
            if not spoken_ok:
                if self._interrupted():
                    break
                continue

            spoken_count += 1
            chunk_kinds.append(chunk.kind.value)
            cleaned = clean_response_text(chunk.text)
            if cleaned:
                full_text_parts.append(cleaned)
                self._extend_dynamic_display_pool(dynamic_display_pool, cleaned)

            _track_spoken_chunk(chunk)

            if not display_shown:
                display_shown = self._show_display_block(
                    display_title,
                    self._resolve_live_display_lines(dynamic_display_pool),
                )

        if not display_shown:
            self._show_display_block(
                display_title,
                self._resolve_live_display_lines(dynamic_display_pool),
            )

        if first_sentence_latency_s is None and first_audio_latency_s is not None:
            first_sentence_latency_s = first_audio_latency_s

        full_text = " ".join(part.strip() for part in full_text_parts if part.strip()).strip()
        total_elapsed = time.monotonic() - response_started_at

        LOGGER.info(
            "Live response plan executed: turn_id=%s, route_kind=%s, stream_mode=%s, "
            "spoken_chunks=%s, first_audio_latency=%.3fs, first_chunk_ms=%.1f, "
            "first_sentence_latency=%.3fs, total_elapsed=%.3fs",
            plan.turn_id,
            self._route_kind_value(plan),
            self._stream_mode_value(plan),
            spoken_count,
            first_audio_latency_s if first_audio_latency_s is not None else -1.0,
            first_chunk_latency_ms,
            first_sentence_latency_s if first_sentence_latency_s is not None else -1.0,
            total_elapsed,
        )

        finished_at = time.monotonic()
        return StreamExecutionReport(
            chunks_spoken=spoken_count,
            full_text=full_text,
            display_title=display_title,
            display_lines=self._resolve_live_display_lines(dynamic_display_pool),
            first_audio_latency_ms=(first_audio_latency_s or 0.0) * 1000.0,
            first_chunk_latency_ms=first_chunk_latency_ms,
            first_sentence_latency_ms=(first_sentence_latency_s or 0.0) * 1000.0,
            total_elapsed_ms=total_elapsed * 1000.0,
            started_at_monotonic=response_started_at,
            first_audio_started_at_monotonic=(
                response_started_at + first_audio_latency_s
                if first_audio_latency_s is not None
                else 0.0
            ),
            first_chunk_started_at_monotonic=first_chunk_started_at_monotonic,
            first_sentence_started_at_monotonic=(
                response_started_at + first_sentence_latency_s
                if first_sentence_latency_s is not None
                else 0.0
            ),
            finished_at_monotonic=finished_at,
            chunk_kinds=chunk_kinds,
            live_streaming=True,
        )

    def _iter_live_chunks(self, plan: ResponsePlan) -> Iterator[AssistantChunk]:
        metadata = dict(getattr(plan, "metadata", {}) or {})
        factory = metadata.get("live_chunk_factory")
        if not callable(factory):
            return iter(())

        try:
            produced = factory()
        except Exception as error:
            LOGGER.warning("Live chunk factory failed: %s", error)
            return iter(())

        return self._coerce_live_chunk_iterable(produced, plan)

    def _coerce_live_chunk_iterable(
        self,
        produced: Any,
        plan: ResponsePlan,
    ) -> Iterator[AssistantChunk]:
        if produced is None:
            return iter(())

        if isinstance(produced, AssistantChunk):
            return iter((produced,))

        if not isinstance(produced, Iterable):
            return iter(())

        def _generator() -> Iterator[AssistantChunk]:
            next_sequence_index = len(getattr(plan, "chunks", []) or [])
            try:
                for item in produced:
                    chunk = self._coerce_single_live_chunk(
                        item,
                        plan=plan,
                        sequence_index=next_sequence_index,
                    )
                    if chunk is None:
                        continue
                    next_sequence_index += 1
                    yield chunk
            except Exception as error:
                LOGGER.exception("Live chunk iterable failed while streaming: %s", error)
                return

        return _generator()

    def _coerce_single_live_chunk(
        self,
        item: Any,
        *,
        plan: ResponsePlan,
        sequence_index: int,
    ) -> AssistantChunk | None:
        if isinstance(item, AssistantChunk):
            return AssistantChunk(
                text=item.text,
                language=item.language or plan.language,
                kind=item.kind,
                speak_now=item.speak_now,
                flush=item.flush,
                sequence_index=sequence_index,
                metadata=dict(item.metadata),
            )

        text = clean_response_text(str(getattr(item, "text", "") or ""))
        if not text:
            return None

        language = str(getattr(item, "language", plan.language) or plan.language)
        metadata = dict(getattr(item, "metadata", {}) or {})
        metadata["live"] = True

        fallback_kind = getattr(item, "kind", None) or metadata.get("kind") or ChunkKind.CONTENT

        return AssistantChunk(
            text=text,
            language=language,
            kind=fallback_kind,
            speak_now=bool(getattr(item, "speak_now", True)),
            flush=bool(getattr(item, "flush", True)),
            sequence_index=sequence_index,
            metadata=metadata,
        )

    def _speak_live_chunk(self, chunk: AssistantChunk) -> bool:
        text = clean_response_text(chunk.text)
        if not text:
            return False
        return self._speak_chunk(chunk, text, next_hint=None)

    def _extend_dynamic_display_pool(self, pool: list[str], text: str) -> None:
        cleaned = clean_response_text(text)
        if not cleaned:
            return

        if not pool:
            pool.extend(self._sentence_units(cleaned))
            return

        pool.extend(self._sentence_units(cleaned))
        del pool[self.max_display_lines * 2 :]

    def _resolve_live_display_lines(self, pool: list[str]) -> list[str]:
        if not pool:
            return []
        return self._build_display_lines_from_chunks(
            [AssistantChunk(text=text, sequence_index=index) for index, text in enumerate(pool)]
        )


__all__ = ["ResponseStreamerLiveStream"]