from __future__ import annotations

import queue
import threading
import time
from collections.abc import Iterable, Iterator
from typing import Any

from modules.core.presence import PresenceHeartbeatManager
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

    @staticmethod
    def _chunk_metric_ms(chunk: AssistantChunk, key: str) -> float:
        metadata = dict(getattr(chunk, "metadata", {}) or {})
        try:
            return max(0.0, float(metadata.get(key, 0.0) or 0.0))
        except (TypeError, ValueError):
            return 0.0

    def _start_live_prefetch(
        self,
        live_chunks: Iterator[AssistantChunk],
    ) -> "queue.Queue[AssistantChunk | None]":
        chunk_queue: queue.Queue[AssistantChunk | None] = queue.Queue(maxsize=4)

        def _drain() -> None:
            try:
                for chunk in live_chunks:
                    chunk_queue.put(chunk)
            except Exception as error:
                LOGGER.warning("[tts-stream] event=prefetch_error error=%s", error)
            finally:
                chunk_queue.put(None)

        threading.Thread(
            target=_drain,
            name="nexa-live-prefetch",
            daemon=True,
        ).start()
        LOGGER.info("[tts-stream] event=prefetch_started")
        return chunk_queue

    def _iter_prefetch_queue(
        self,
        chunk_queue: "queue.Queue[AssistantChunk | None]",
        *,
        timeout_seconds: float = 45.0,
    ) -> Iterator[AssistantChunk]:
        while True:
            try:
                chunk = chunk_queue.get(timeout=timeout_seconds)
            except queue.Empty:
                LOGGER.warning(
                    "[tts-stream] event=prefetch_timeout timeout_s=%.0f", timeout_seconds
                )
                return
            if chunk is None:
                return
            yield chunk

    def _execute_live_stream(self, plan: ResponsePlan) -> StreamExecutionReport:
        prepared_chunks = self._prepare_chunks(plan)
        display_title, display_lines = self._resolve_display_content(plan, prepared_chunks)
        live_chunks = self._iter_live_chunks(plan)
        live_chunk_queue = self._start_live_prefetch(live_chunks)

        response_started_at = time.monotonic()
        first_audio_latency_s: float | None = None
        first_sentence_latency_s: float | None = None
        first_chunk_latency_ms = 0.0
        first_chunk_started_at_monotonic = 0.0
        first_token_latency_ms = 0.0
        first_token_started_at_monotonic = 0.0
        first_speakable_chunk_latency_ms = 0.0
        first_speakable_chunk_started_at_monotonic = 0.0
        first_content_chunk_latency_ms = 0.0
        first_real_audio_after_tts_started_ms = 0.0
        first_chunk_chars = 0
        first_chunk_synthesis_ms = 0.0
        prepare_next_ms = 0.0

        spoken_count = 0
        full_text_parts: list[str] = []
        dynamic_display_pool: list[str] = list(display_lines)
        display_shown = False
        last_display_signature: tuple[str, tuple[str, ...]] | None = None
        deferred_fallback_display_lines: list[str] = []
        chunk_kinds: list[str] = []
        first_live_chunk_notified = False
        spoken_gap_ms_values: list[float] = []
        heartbeat = self._start_presence_heartbeat(plan)
        heartbeat_cancelled_for_audio = False

        def _on_real_audio_started() -> None:
            nonlocal heartbeat_cancelled_for_audio
            if heartbeat_cancelled_for_audio:
                return
            heartbeat_cancelled_for_audio = True
            self._cancel_presence_heartbeat(heartbeat, reason="real_audio_started")

        def _notify_first_live_chunk() -> None:
            nonlocal first_live_chunk_notified
            if first_live_chunk_notified:
                return
            first_live_chunk_notified = True
            callback = dict(getattr(plan, "metadata", {}) or {}).get("on_first_live_chunk")
            if not callable(callback):
                return
            try:
                callback()
            except Exception as error:
                LOGGER.warning("Live response first chunk callback failed: %s", error)

        def _show_or_update_dynamic_display(lines: list[str]) -> None:
            nonlocal display_shown
            nonlocal last_display_signature
            nonlocal deferred_fallback_display_lines

            if not lines:
                return

            signature = (display_title, tuple(lines))
            if signature == last_display_signature:
                return

            if not display_shown:
                display_shown = self._show_display_block(display_title, lines)
            elif not self._display_supports_live_update():
                deferred_fallback_display_lines = list(lines)
                return
            else:
                display_shown = bool(
                    self._show_or_update_live_display_block(display_title, lines)
                    or display_shown
                )

            if display_shown:
                last_display_signature = signature

        def _track_spoken_chunk(chunk: AssistantChunk, speak_call_started_at: float) -> None:
            nonlocal first_audio_latency_s
            nonlocal first_sentence_latency_s
            nonlocal first_chunk_latency_ms
            nonlocal first_chunk_started_at_monotonic
            nonlocal first_token_latency_ms
            nonlocal first_token_started_at_monotonic
            nonlocal first_speakable_chunk_latency_ms
            nonlocal first_speakable_chunk_started_at_monotonic
            nonlocal first_content_chunk_latency_ms
            nonlocal first_real_audio_after_tts_started_ms
            nonlocal first_chunk_synthesis_ms
            nonlocal prepare_next_ms

            actual_first_audio_started_at = self._resolve_chunk_first_audio_started_at(
                speak_call_started_at=speak_call_started_at,
            )
            if first_audio_latency_s is None:
                first_audio_latency_s = max(0.0, actual_first_audio_started_at - response_started_at)
                first_real_audio_after_tts_started_ms = max(
                    0.0,
                    (actual_first_audio_started_at - speak_call_started_at) * 1000.0,
                )

                report_method = getattr(self.voice_output, "latest_speak_report", None)
                if callable(report_method):
                    try:
                        speak_report = dict(report_method() or {})
                    except Exception:
                        speak_report = {}
                    try:
                        first_chunk_synthesis_ms = max(
                            0.0,
                            float(speak_report.get("wav_ready_ms", 0.0) or 0.0),
                        )
                    except (TypeError, ValueError):
                        first_chunk_synthesis_ms = 0.0
                    try:
                        prepare_next_ms = max(
                            0.0,
                            float(speak_report.get("prepare_next_ms", 0.0) or 0.0),
                        )
                    except (TypeError, ValueError):
                        prepare_next_ms = 0.0

            chunk_token_latency_ms = self._chunk_metric_ms(chunk, "first_token_latency_ms")
            if first_token_latency_ms <= 0.0 and chunk_token_latency_ms > 0.0:
                first_token_latency_ms = chunk_token_latency_ms
                first_token_started_at_monotonic = (
                    response_started_at + (chunk_token_latency_ms / 1000.0)
                )

            chunk_speakable_latency_ms = self._chunk_metric_ms(
                chunk,
                "first_speakable_chunk_latency_ms",
            )
            if first_speakable_chunk_latency_ms <= 0.0 and chunk_speakable_latency_ms > 0.0:
                first_speakable_chunk_latency_ms = chunk_speakable_latency_ms
                first_speakable_chunk_started_at_monotonic = (
                    response_started_at + (chunk_speakable_latency_ms / 1000.0)
                )

            chunk_first_latency_ms = self._chunk_first_latency_ms(chunk)
            if first_chunk_latency_ms <= 0.0 and chunk_first_latency_ms > 0.0:
                first_chunk_latency_ms = chunk_first_latency_ms
                first_chunk_started_at_monotonic = (
                    response_started_at + (chunk_first_latency_ms / 1000.0)
                )
                if first_speakable_chunk_latency_ms <= 0.0:
                    first_speakable_chunk_latency_ms = chunk_first_latency_ms
                    first_speakable_chunk_started_at_monotonic = first_chunk_started_at_monotonic

            if (
                first_content_chunk_latency_ms <= 0.0
                and self._is_sentence_chunk_kind(chunk.kind)
            ):
                first_content_chunk_latency_ms = (
                    chunk_speakable_latency_ms
                    or chunk_first_latency_ms
                    or max(0.0, (actual_first_audio_started_at - response_started_at) * 1000.0)
                )

            if first_sentence_latency_s is None and self._is_sentence_chunk_kind(chunk.kind):
                first_sentence_latency_s = max(0.0, actual_first_audio_started_at - response_started_at)

        try:
            for chunk in prepared_chunks:
                _notify_first_live_chunk()
                speak_call_started_at = time.monotonic()
                spoken_ok = self._speak_live_chunk(chunk, on_first_audio=_on_real_audio_started)
                if not spoken_ok:
                    if self._interrupted():
                        break
                    continue

                spoken_count += 1
                chunk_kinds.append(chunk.kind.value)
                cleaned = clean_response_text(chunk.text)
                if cleaned:
                    full_text_parts.append(cleaned)
                    if chunk.kind != ChunkKind.ACK:
                        self._extend_dynamic_display_pool(dynamic_display_pool, cleaned)

                _track_spoken_chunk(chunk, speak_call_started_at)

                current_display_lines = self._resolve_live_display_lines(dynamic_display_pool)
                _show_or_update_dynamic_display(current_display_lines)

            live_stream_index = 0
            last_live_speak_ended_at: float | None = None
            live_iterator = self._iter_prefetch_queue(live_chunk_queue)
            current_chunk = self._next_live_chunk(live_iterator)
            while current_chunk is not None:
                next_chunk = self._next_live_chunk(live_iterator)
                if self._interrupted():
                    break

                next_hint = self._live_next_hint(next_chunk)
                _notify_first_live_chunk()
                speak_call_started_at = time.monotonic()
                if first_chunk_chars <= 0:
                    first_chunk_chars = len(clean_response_text(current_chunk.text))

                if last_live_speak_ended_at is not None:
                    gap_ms = (speak_call_started_at - last_live_speak_ended_at) * 1000.0
                    spoken_gap_ms_values.append(gap_ms)
                    LOGGER.info(
                        "[tts-stream] event=gap_between_spoken_chunks chunk_index=%s gap_ms=%.1f",
                        live_stream_index,
                        gap_ms,
                    )
                LOGGER.info(
                    "[tts-stream] event=chunk_speak_started chunk_index=%s chars=%s queue_depth=%s",
                    live_stream_index,
                    len(clean_response_text(current_chunk.text)),
                    live_chunk_queue.qsize(),
                )

                spoken_ok = self._speak_live_chunk(
                    current_chunk,
                    next_hint=next_hint,
                    on_first_audio=_on_real_audio_started,
                )
                speak_ended_at = time.monotonic()

                if not spoken_ok:
                    if self._interrupted():
                        break
                    current_chunk = next_chunk
                    continue

                LOGGER.info(
                    "[tts-stream] event=chunk_speak_finished chunk_index=%s speak_ms=%.1f",
                    live_stream_index,
                    (speak_ended_at - speak_call_started_at) * 1000.0,
                )
                last_live_speak_ended_at = speak_ended_at
                live_stream_index += 1

                spoken_count += 1
                chunk_kinds.append(current_chunk.kind.value)
                cleaned = clean_response_text(current_chunk.text)
                if cleaned:
                    full_text_parts.append(cleaned)
                    self._extend_dynamic_display_pool(dynamic_display_pool, cleaned)

                _track_spoken_chunk(current_chunk, speak_call_started_at)

                current_display_lines = self._resolve_live_display_lines(dynamic_display_pool)
                _show_or_update_dynamic_display(current_display_lines)

                current_chunk = next_chunk
        finally:
            self._cancel_presence_heartbeat(heartbeat, reason="stream_finished")

        if display_shown and deferred_fallback_display_lines:
            final_signature = (display_title, tuple(deferred_fallback_display_lines))
            if final_signature != last_display_signature:
                if self._show_display_block(display_title, deferred_fallback_display_lines):
                    last_display_signature = final_signature

        if not display_shown:
            self._show_display_block(
                display_title,
                self._resolve_live_display_lines(dynamic_display_pool),
            )

        if first_sentence_latency_s is None and first_audio_latency_s is not None:
            first_sentence_latency_s = first_audio_latency_s

        full_text = " ".join(part.strip() for part in full_text_parts if part.strip()).strip()
        total_elapsed = time.monotonic() - response_started_at
        heartbeat_metrics = heartbeat.metrics() if heartbeat is not None else None
        max_gap_ms = max(spoken_gap_ms_values) if spoken_gap_ms_values else 0.0
        avg_gap_ms = (
            sum(spoken_gap_ms_values) / len(spoken_gap_ms_values)
            if spoken_gap_ms_values
            else 0.0
        )

        LOGGER.info(
            "Live response plan executed: turn_id=%s, route_kind=%s, stream_mode=%s, "
            "spoken_chunks=%s, first_audio_ms=%.1f, first_token_latency_ms=%.1f, "
            "first_speakable_chunk_latency_ms=%.1f, first_chunk_latency_ms=%.1f, "
            "first_sentence_latency=%.3fs, total_elapsed=%.3fs",
            plan.turn_id,
            self._route_kind_value(plan),
            self._stream_mode_value(plan),
            spoken_count,
            (first_audio_latency_s * 1000.0) if first_audio_latency_s is not None else -1.0,
            first_token_latency_ms,
            first_speakable_chunk_latency_ms,
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
            chunk_count=spoken_count,
            first_audio_latency_ms=(first_audio_latency_s or 0.0) * 1000.0,
            first_audio_ms=(first_audio_latency_s or 0.0) * 1000.0,
            tts_first_audio_ms=(first_audio_latency_s or 0.0) * 1000.0,
            first_chunk_latency_ms=first_chunk_latency_ms,
            llm_request_started=True,
            llm_first_token_ms=first_token_latency_ms,
            llm_first_content_chunk_ms=first_content_chunk_latency_ms,
            first_token_latency_ms=first_token_latency_ms,
            first_speakable_chunk_latency_ms=first_speakable_chunk_latency_ms,
            first_sentence_latency_ms=(first_sentence_latency_s or 0.0) * 1000.0,
            max_spoken_gap_ms=max_gap_ms,
            average_spoken_gap_ms=avg_gap_ms,
            heartbeat_count=heartbeat_metrics.heartbeat_count if heartbeat_metrics else 0,
            heartbeat_first_ms=heartbeat_metrics.first_heartbeat_ms if heartbeat_metrics else 0.0,
            heartbeat_cancelled=heartbeat_metrics.cancelled if heartbeat_metrics else False,
            heartbeat_cancelled_reason=heartbeat_metrics.cancelled_reason if heartbeat_metrics else "",
            presence_skipped_reason_count=(
                heartbeat_metrics.skipped_reason_count if heartbeat_metrics else 0
            ),
            first_real_audio_after_tts_started_ms=first_real_audio_after_tts_started_ms,
            first_chunk_chars=first_chunk_chars,
            first_chunk_synthesis_ms=first_chunk_synthesis_ms,
            prepare_next_ms=prepare_next_ms,
            total_elapsed_ms=total_elapsed * 1000.0,
            total_response_ms=total_elapsed * 1000.0,
            started_at_monotonic=response_started_at,
            first_audio_started_at_monotonic=(
                response_started_at + first_audio_latency_s
                if first_audio_latency_s is not None
                else 0.0
            ),
            first_chunk_started_at_monotonic=first_chunk_started_at_monotonic,
            first_token_started_at_monotonic=first_token_started_at_monotonic,
            first_speakable_chunk_started_at_monotonic=first_speakable_chunk_started_at_monotonic,
            first_sentence_started_at_monotonic=(
                response_started_at + first_sentence_latency_s
                if first_sentence_latency_s is not None
                else 0.0
            ),
            finished_at_monotonic=finished_at,
            chunk_kinds=chunk_kinds,
            live_streaming=True,
        )

    def _start_presence_heartbeat(
        self,
        plan: ResponsePlan,
    ) -> PresenceHeartbeatManager | None:
        metadata = dict(getattr(plan, "metadata", {}) or {})
        if not bool(metadata.get("presence_heartbeat_enabled", False)):
            return None

        heartbeat = PresenceHeartbeatManager(
            voice_output=self.voice_output,
            language=str(getattr(plan, "language", "") or metadata.get("language", "en")),
            first_delay_s=float(metadata.get("presence_heartbeat_first_delay_s", 1.0) or 1.0),
            repeat_interval_s=float(
                metadata.get("presence_heartbeat_repeat_interval_s", 2.7) or 2.7
            ),
        )
        heartbeat.start()
        return heartbeat

    @staticmethod
    def _cancel_presence_heartbeat(
        heartbeat: PresenceHeartbeatManager | None,
        *,
        reason: str = "cancelled",
    ) -> None:
        if heartbeat is not None:
            heartbeat.cancel(reason=reason)

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
            first_live_content_emitted = False
            try:
                for item in produced:
                    chunk = self._coerce_single_live_chunk(
                        item,
                        plan=plan,
                        sequence_index=next_sequence_index,
                    )
                    if chunk is None:
                        continue
                    if (
                        not first_live_content_emitted
                        and self._is_sentence_chunk_kind(chunk.kind)
                    ):
                        first_live_content_emitted = True
                        head, tail = self._split_first_live_chunk(chunk, plan)
                        yield head
                        next_sequence_index += 1
                        if tail is not None:
                            tail.sequence_index = next_sequence_index
                            yield tail
                            next_sequence_index += 1
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

    def _split_first_live_chunk(
        self,
        chunk: AssistantChunk,
        plan: ResponsePlan,
    ) -> tuple[AssistantChunk, AssistantChunk | None]:
        metadata = dict(getattr(plan, "metadata", {}) or {})
        try:
            max_chars = int(
                metadata.get(
                    "live_first_chunk_max_chars",
                    getattr(self, "live_first_chunk_max_chars", 80),
                )
            )
        except (TypeError, ValueError):
            max_chars = 80
        max_chars = max(40, min(120, max_chars))

        text = clean_response_text(chunk.text)
        if len(text) <= max_chars:
            return chunk, None

        split_at = -1
        for marker in (", ", "; ", ": ", " - "):
            candidate = text.rfind(marker, 24, max_chars + 1)
            if candidate >= 24:
                split_at = candidate + len(marker.rstrip())
                break
        if split_at < 24:
            split_at = text.rfind(" ", 40, max_chars + 1)
        if split_at < 24:
            return chunk, None

        head_text = clean_response_text(text[:split_at])
        tail_text = clean_response_text(text[split_at:])
        if not head_text or not tail_text:
            return chunk, None

        head_metadata = dict(chunk.metadata)
        head_metadata["first_chunk_budget_applied"] = True
        head_metadata["original_first_chunk_chars"] = len(text)

        tail_metadata = dict(chunk.metadata)
        tail_metadata.pop("first_chunk_latency_ms", None)
        tail_metadata.pop("first_token_latency_ms", None)
        tail_metadata.pop("first_speakable_chunk_latency_ms", None)
        tail_metadata["split_from_first_chunk"] = True

        head = AssistantChunk(
            text=head_text,
            language=chunk.language or plan.language,
            kind=chunk.kind,
            speak_now=chunk.speak_now,
            flush=chunk.flush,
            sequence_index=chunk.sequence_index,
            metadata=head_metadata,
        )
        tail = AssistantChunk(
            text=tail_text,
            language=chunk.language or plan.language,
            kind=chunk.kind,
            speak_now=chunk.speak_now,
            flush=chunk.flush,
            sequence_index=chunk.sequence_index + 1,
            metadata=tail_metadata,
        )
        return head, tail

    def _next_live_chunk(self, chunks: Iterator[AssistantChunk]) -> AssistantChunk | None:
        try:
            return next(chunks)
        except StopIteration:
            return None
        except Exception as error:
            LOGGER.exception("Live chunk iterator failed while preparing lookahead: %s", error)
            return None

    def _live_next_hint(self, chunk: AssistantChunk | None) -> tuple[str, str] | None:
        if chunk is None:
            return None
        text = clean_response_text(chunk.text)
        if not text or len(text) > self.prefetch_max_chars:
            return None
        return text, chunk.language

    def _show_or_update_live_display_block(self, title: str, lines: list[str]) -> bool:
        for method_name in ("update_block", "replace_block", "update_overlay"):
            method = getattr(self.display, method_name, None)
            if not callable(method):
                continue
            try:
                method(title, lines, duration=self.default_display_seconds)
                return True
            except TypeError:
                try:
                    method(title, lines)
                    return True
                except Exception as error:
                    LOGGER.warning("Display %s failed: %s", method_name, error)
                    return False
            except Exception as error:
                LOGGER.warning("Display %s failed: %s", method_name, error)
                return False

        return self._show_display_block(title, lines)

    def _display_supports_live_update(self) -> bool:
        return any(
            callable(getattr(self.display, method_name, None))
            for method_name in ("update_block", "replace_block", "update_overlay")
        )

    def _speak_live_chunk(
        self,
        chunk: AssistantChunk,
        *,
        next_hint: tuple[str, str] | None = None,
        on_first_audio: Any | None = None,
    ) -> bool:
        text = clean_response_text(chunk.text)
        if not text:
            return False
        return self._speak_chunk(
            chunk,
            text,
            next_hint=next_hint,
            on_first_audio=on_first_audio,
        )

    def _extend_dynamic_display_pool(self, pool: list[str], text: str) -> None:
        cleaned = clean_response_text(text)
        if not cleaned:
            return

        if not pool:
            pool.extend(self._sentence_units(cleaned))
            return

        for unit in self._sentence_units(cleaned):
            if pool and pool[-1] == unit:
                continue
            pool.append(unit)
        del pool[self.max_display_lines * 2 :]

    def _resolve_live_display_lines(self, pool: list[str]) -> list[str]:
        if not pool:
            return []
        recent_pool = pool[-self.max_display_lines :]
        return self._build_display_lines_from_chunks(
            [AssistantChunk(text=text, sequence_index=index) for index, text in enumerate(recent_pool)]
        )


__all__ = ["ResponseStreamerLiveStream"]
