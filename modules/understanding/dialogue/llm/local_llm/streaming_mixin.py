from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any

from modules.runtime.contracts import ChunkKind, clean_response_text

from .models import LocalLLMChunk


class LocalLLMStreamingMixin:
    _STREAM_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")

    def mark_first_chunk_received(self, first_chunk_latency_ms: float) -> None:
        self._last_first_chunk_latency_ms = max(0.0, float(first_chunk_latency_ms or 0.0))

    def stream_companion_reply(
        self,
        text: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> Iterator[LocalLLMChunk]:
        self.mark_generation_started()

        try:
            normalized_language = self._normalize_language(language)
            safe_text = str(text or "").strip()
            llm_context = self._coerce_context(context, user_text=safe_text)
            profile = self._build_generation_profile(
                language=normalized_language,
                context=llm_context,
                user_prompt=safe_text,
            )
            system_prompt = self._build_system_prompt(
                language=normalized_language,
                context=llm_context,
                profile=profile,
            )
            user_prompt = safe_text[: profile.prompt_chars].strip()
        except Exception as error:
            self.mark_generation_finished(ok=False, source="stream_prepare", error=str(error))
            return iter(())

        if self.runner in self._SERVER_RUNNERS:
            return self._stream_server_chunks(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                profile=profile,
                language=normalized_language,
            )

        fallback_reply = self.generate_companion_reply(
            safe_text,
            normalized_language,
            context=context,
        )
        if not fallback_reply.ok or not fallback_reply.text:
            return iter(())

        return self._chunk_full_text_reply(
            text=fallback_reply.text,
            language=normalized_language,
            source=fallback_reply.source or self.runner,
            first_chunk_latency_ms=float(getattr(fallback_reply, "first_chunk_latency_ms", 0.0) or 0.0),
            max_sentences=profile.max_sentences,
            user_prompt=user_prompt,
        )

    def _stream_server_chunks(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        profile,
        language: str,
    ) -> Iterator[LocalLLMChunk]:
        base_url = self._normalized_server_base_url()
        if not base_url:
            self.mark_generation_finished(ok=False, source="stream_server", error="Local LLM server URL is empty.")
            return iter(())

        endpoints = self._server_request_candidates(
            base_url=base_url,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            profile=profile,
            stream=True,
        )

        def _generator() -> Iterator[LocalLLMChunk]:
            last_error: Exception | None = None
            stream_errors: list[str] = []

            for endpoint in endpoints:
                try:
                    yield from self._iter_streaming_endpoint_chunks(
                        url=endpoint["url"],
                        payload=endpoint["payload"],
                        timeout_seconds=profile.timeout_seconds,
                        language=language,
                        source=self.runner,
                        profile=profile,
                        user_prompt=user_prompt,
                    )
                    return
                except Exception as error:
                    last_error = error
                    stream_errors.append(f'{endpoint["url"]}: {error}')
                    self.LOGGER.warning("Local LLM streaming candidate failed: %s", stream_errors[-1])
                    continue

            fallback_error: Exception | None = None
            try:
                fallback_text = self._run_server(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    profile=profile,
                    stream=False,
                )
                cleaned_fallback = self._sanitize_stream_text(
                    fallback_text,
                    language=language,
                    max_sentences=profile.max_sentences,
                    user_prompt=user_prompt,
                    final_chunk=True,
                )
                if cleaned_fallback:
                    first_chunk_latency_ms = (time.perf_counter() - self._last_generation_started_at) * 1000.0
                    self.mark_first_chunk_received(first_chunk_latency_ms)
                    yield from self._chunk_full_text_reply(
                        text=cleaned_fallback,
                        language=language,
                        source=f"{self.runner}_non_stream_fallback",
                        first_chunk_latency_ms=first_chunk_latency_ms,
                        max_sentences=profile.max_sentences,
                        user_prompt=user_prompt,
                    )
                    self.mark_generation_finished(
                        ok=True,
                        source=f"{self.runner}_non_stream_fallback",
                        streamed=False,
                    )
                    return
                fallback_error = RuntimeError("Local LLM non-stream fallback returned no usable text.")
            except Exception as error:
                fallback_error = error
                self.LOGGER.warning("Local LLM non-stream fallback failed: %s", error)

            error_parts = list(stream_errors)
            if fallback_error is not None:
                error_parts.append(f"non-stream fallback: {fallback_error}")

            error_text = " | ".join(part for part in error_parts if str(part).strip())
            if not error_text:
                error_text = (
                    str(last_error)
                    if last_error is not None
                    else "Local LLM server returned no usable streaming response."
                )

            self.mark_generation_finished(
                ok=False,
                source="stream_server",
                error=error_text,
                streamed=True,
            )

        return _generator()

    def _iter_streaming_endpoint_chunks(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        timeout_seconds: float,
        language: str,
        source: str,
        profile=None,
        user_prompt: str = "",
    ) -> Iterator[LocalLLMChunk]:
        request = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._server_headers(json_body=True),
        )

        request_started_at = time.perf_counter()
        first_chunk_latency_ms = 0.0
        pending_buffer = ""
        raw_full_text_parts: list[str] = []
        emitted_count = 0
        max_sentences = max(
            1,
            int(getattr(profile, "max_sentences", 2) or 2),
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                for raw_line in response:
                    decoded_line = raw_line.decode("utf-8", errors="replace").strip()
                    if not decoded_line:
                        continue

                    if decoded_line.startswith("data:"):
                        decoded_line = decoded_line[5:].strip()
                    if not decoded_line or decoded_line == "[DONE]":
                        continue

                    try:
                        payload_obj = json.loads(decoded_line)
                    except Exception:
                        continue

                    text_delta = self._extract_text_from_json_payload(
                        payload_obj,
                        preserve_token_spacing=True,
                    )
                    if text_delta:
                        if first_chunk_latency_ms <= 0.0:
                            first_chunk_latency_ms = (time.perf_counter() - request_started_at) * 1000.0
                            self.mark_first_chunk_received(first_chunk_latency_ms)

                        raw_full_text_parts.append(text_delta)
                        pending_buffer = f"{pending_buffer}{text_delta}"

                        ready_chunks, pending_buffer = self._split_ready_stream_chunks(
                            pending_buffer,
                            language=language,
                            emitted_count=emitted_count,
                        )

                        for ready_text in ready_chunks:
                            cleaned = self._sanitize_stream_text(
                                ready_text,
                                language=language,
                                max_sentences=max_sentences,
                                user_prompt=user_prompt,
                                final_chunk=False,
                            )
                            if not cleaned:
                                continue
                            yield LocalLLMChunk(
                                text=cleaned,
                                language=language,
                                source=source,
                                sequence=emitted_count,
                                finished=False,
                                flush=True,
                                speak_now=True,
                                kind=ChunkKind.CONTENT,
                                metadata={"source": source, "live": True},
                                first_chunk_latency_ms=first_chunk_latency_ms if emitted_count == 0 else 0.0,
                            )
                            emitted_count += 1

                    if self._stream_payload_finished(payload_obj):
                        break
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Local LLM server HTTP {error.code}: {body}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Local LLM server request failed: {error}") from error

        full_text = self._compact_whitespace("".join(raw_full_text_parts))
        if not full_text:
            raise RuntimeError("Local LLM server streaming returned no text.")

        tail_text = self._sanitize_stream_text(
            pending_buffer,
            language=language,
            max_sentences=max_sentences,
            user_prompt=user_prompt,
            final_chunk=True,
        )
        if tail_text:
            yield LocalLLMChunk(
                text=tail_text,
                language=language,
                source=source,
                sequence=emitted_count,
                finished=True,
                flush=True,
                speak_now=True,
                kind=ChunkKind.CONTENT,
                metadata={"source": source, "live": True, "tail": True},
                first_chunk_latency_ms=first_chunk_latency_ms if emitted_count == 0 else 0.0,
            )
            emitted_count += 1

        if emitted_count <= 0:
            raise RuntimeError("Local LLM server streaming returned no usable text after cleanup.")

        self.mark_generation_finished(ok=True, source=source, streamed=True)

    def _chunk_full_text_reply(
        self,
        *,
        text: str,
        language: str,
        source: str,
        first_chunk_latency_ms: float,
        max_sentences: int = 2,
        user_prompt: str = "",
    ) -> Iterator[LocalLLMChunk]:
        cleaned_text = self._sanitize_stream_text(
            text,
            language=language,
            max_sentences=max_sentences,
            user_prompt=user_prompt,
            final_chunk=True,
        )
        if not cleaned_text:
            return iter(())

        ready_chunks, tail = self._split_ready_stream_chunks(
            cleaned_text,
            language=language,
            final_flush=True,
            emitted_count=0,
        )
        final_chunks = [part for part in [*ready_chunks, tail] if str(part or "").strip()]

        def _generator() -> Iterator[LocalLLMChunk]:
            for index, item in enumerate(final_chunks):
                yield LocalLLMChunk(
                    text=item,
                    language=language,
                    source=source,
                    sequence=index,
                    finished=index == len(final_chunks) - 1,
                    flush=True,
                    speak_now=True,
                    kind=ChunkKind.CONTENT,
                    metadata={"source": source, "live": False},
                    first_chunk_latency_ms=first_chunk_latency_ms if index == 0 else 0.0,
                )

        return _generator()

    def _split_ready_stream_chunks(
        self,
        buffer_text: str,
        *,
        language: str,
        final_flush: bool = False,
        emitted_count: int = 0,
    ) -> tuple[list[str], str]:
        del language

        cleaned_buffer = str(buffer_text or "")
        if not cleaned_buffer.strip():
            return [], ""

        ready: list[str] = []
        remainder = cleaned_buffer

        while True:
            boundary = self._find_stream_boundary(remainder)
            if boundary <= 0:
                break

            candidate = remainder[:boundary].strip()
            tail = remainder[boundary:].lstrip()

            if len(clean_response_text(candidate)) < self.stream_sentence_min_chars and not final_flush:
                break

            normalized_candidate = clean_response_text(candidate)
            if normalized_candidate:
                ready.append(normalized_candidate)
            remainder = tail

        normalized_remainder = clean_response_text(remainder)
        if final_flush and normalized_remainder:
            return ready, normalized_remainder

        if not final_flush and not ready and emitted_count == 0:
            fast_first_split = self._split_fast_first_stream_chunk(normalized_remainder)
            if fast_first_split is not None:
                head, tail = fast_first_split
                ready.append(head)
                return ready, tail

        if (
            not final_flush
            and len(normalized_remainder) >= self.stream_sentence_soft_max_chars
            and " " in normalized_remainder
        ):
            split_at = normalized_remainder.rfind(" ", 0, self.stream_sentence_soft_max_chars)
            if split_at >= self.stream_sentence_min_chars:
                head = clean_response_text(normalized_remainder[:split_at])
                tail = clean_response_text(normalized_remainder[split_at:])
                if head:
                    ready.append(head)
                    return ready, tail

        return ready, remainder


    def _split_fast_first_stream_chunk(self, text: str) -> tuple[str, str] | None:
        normalized = clean_response_text(text)
        if not normalized:
            return None

        if len(normalized) < self.stream_first_chunk_soft_max_chars:
            return None

        split_at = -1
        for marker in (",", ";", ":"):
            marker_index = normalized.rfind(
                marker,
                self.stream_first_chunk_min_chars,
                self.stream_first_chunk_soft_max_chars + 1,
            )
            if marker_index >= self.stream_first_chunk_min_chars:
                split_at = max(split_at, marker_index + 1)

        if split_at < self.stream_first_chunk_min_chars:
            split_at = normalized.rfind(
                " ",
                self.stream_first_chunk_min_chars,
                self.stream_first_chunk_soft_max_chars + 1,
            )

        if split_at < self.stream_first_chunk_min_chars:
            return None

        head = clean_response_text(normalized[:split_at])
        tail = clean_response_text(normalized[split_at:])

        if not head or not tail:
            return None

        return head, tail



    def _find_stream_boundary(self, text: str) -> int:
        cleaned = str(text or "")
        if not cleaned:
            return -1

        matches = list(self._STREAM_BOUNDARY_RE.finditer(cleaned))
        if matches:
            return matches[-1].end()

        stripped = cleaned.rstrip()
        if stripped and stripped[-1] in ".!?":
            return len(stripped)

        return -1

    def _sanitize_stream_text(
        self,
        text: str,
        *,
        language: str,
        max_sentences: int,
        user_prompt: str = "",
        final_chunk: bool,
    ) -> str:
        if final_chunk:
            return self._extract_answer(
                raw_output=str(text or ""),
                language=language,
                user_prompt=str(user_prompt or ""),
                max_sentences=max(1, int(max_sentences or 1)),
            )

        cleaned = self._decode_and_clean(str(text or ""))
        if not cleaned:
            return ""

        cleaned = self._strip_runtime_lines(cleaned)
        cleaned = self._remove_echo(str(user_prompt or ""), cleaned)
        cleaned = self._strip_chat_labels(cleaned)
        cleaned = self._strip_code_fences(cleaned)
        cleaned = self._strip_inline_artifacts(cleaned)
        cleaned = self._drop_empty_or_noise_lines(cleaned)
        cleaned = self._compact_whitespace(cleaned)

        if not cleaned or self._looks_like_runtime_noise(cleaned):
            return ""

        cleaned = self._deduplicate_repeated_sentences(cleaned)
        cleaned = self._limit_sentences(cleaned, max_sentences=max(1, int(max_sentences or 1)))

        return cleaned.strip()

    def _stream_payload_finished(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        return bool(payload.get("done", False))


__all__ = ["LocalLLMStreamingMixin"]