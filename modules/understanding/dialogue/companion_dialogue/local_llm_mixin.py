from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from typing import Any

from modules.runtime.contracts import AssistantChunk, StreamMode, clean_response_text
from modules.shared.logging.logger import append_log

from .models import DialogueReply


class CompanionDialogueLocalLLMMixin:
    """Optional local LLM integration for richer dialogue replies."""

    def _try_build_local_llm(self) -> Any | None:
        if importlib.util.find_spec("modules.understanding.dialogue.llm.local_llm") is None:
            return None

        try:
            module = __import__(
                "modules.understanding.dialogue.llm.local_llm",
                fromlist=["LocalLLMService"],
            )
            service_class = getattr(module, "LocalLLMService", None)
            if service_class is None:
                append_log("Local LLM service class not found in dialogue layer.")
                return None

            instance = service_class(self.settings)
            append_log("Local LLM service detected and initialized for dialogue layer.")
            return instance
        except Exception as error:
            append_log(f"Local LLM service initialization skipped: {error}")
            return None

    def _try_local_llm_stream_payload(
        self,
        *,
        normalized_text: str,
        language: str,
        topics: list[str],
        user_profile: dict | None,
        route_kind: str,
        stream_mode: StreamMode,
    ) -> dict[str, Any] | None:
        local_llm = getattr(self, "local_llm", None)
        if local_llm is None:
            return None

        stream_reply = getattr(local_llm, "stream_companion_reply", None)
        if not callable(stream_reply):
            return None

        safe_text = " ".join(str(normalized_text or "").split()).strip()
        if not safe_text:
            return None

        is_available = getattr(local_llm, "is_available", None)
        if callable(is_available):
            try:
                if not is_available():
                    return None
            except Exception as error:
                append_log(f"Local LLM availability check failed: {error}")
                return None

        context = self._build_local_llm_context(
            normalized_text=safe_text,
            language=language,
            topics=topics,
            user_profile=user_profile,
            route_kind=route_kind,
        )

        source_name = str(getattr(local_llm, "runner", "local_llm") or "local_llm").strip() or "local_llm"
        primary_kind = self._primary_chunk_kind_for_route(route_kind)

        def _factory() -> Iterator[AssistantChunk]:
            emitted = 0
            try:
                iterator = stream_reply(safe_text, language, context=context)
            except Exception as error:
                append_log(f"Local LLM live stream start failed: {error}")
                return iter(())

            try:
                for raw_chunk in iterator:
                    text = self._sanitize_local_llm_reply(
                        text=str(getattr(raw_chunk, "text", "") or ""),
                        language=language,
                    )
                    if not text:
                        continue

                    metadata = dict(getattr(raw_chunk, "metadata", {}) or {})
                    metadata.update(
                        {
                            "source": source_name,
                            "live": True,
                            "llm_streamed": True,
                        }
                    )
                    first_chunk_latency_ms = float(getattr(raw_chunk, "first_chunk_latency_ms", 0.0) or 0.0)
                    if first_chunk_latency_ms > 0.0:
                        metadata["first_chunk_latency_ms"] = first_chunk_latency_ms

                    yield AssistantChunk(
                        text=text,
                        language=str(getattr(raw_chunk, "language", language) or language),
                        kind=getattr(raw_chunk, "kind", primary_kind) or primary_kind,
                        speak_now=bool(getattr(raw_chunk, "speak_now", True)),
                        flush=bool(getattr(raw_chunk, "flush", True)),
                        sequence_index=emitted,
                        metadata=metadata,
                    )
                    emitted += 1
            except Exception as error:
                append_log(f"Local LLM live stream iteration failed: {error}")
                return

            if emitted == 0:
                append_log(
                    "Local LLM live stream produced zero usable chunks. "
                    f"route_kind={route_kind}, source={source_name}"
                )

        return {
            "factory": _factory,
            "display_title": self._text(language, "ODPOWIEDŹ", "REPLY"),
            "display_lines": [],
            "source": source_name,
            "stream_mode": stream_mode,
            "primary_kind": primary_kind,
        }

    def _try_local_llm(
        self,
        *,
        normalized_text: str,
        language: str,
        topics: list[str],
        user_profile: dict | None,
        route_kind: str,
    ) -> DialogueReply | None:
        local_llm = getattr(self, "local_llm", None)
        if local_llm is None:
            return None

        safe_text = " ".join(str(normalized_text or "").split()).strip()
        if not safe_text:
            return None

        is_available = getattr(local_llm, "is_available", None)
        if callable(is_available):
            try:
                if not is_available():
                    return None
            except Exception as error:
                append_log(f"Local LLM availability check failed: {error}")
                return None

        generate_reply = getattr(local_llm, "generate_companion_reply", None)
        if not callable(generate_reply):
            append_log("Local LLM generate_companion_reply method is missing.")
            return None

        context = self._build_local_llm_context(
            normalized_text=safe_text,
            language=language,
            topics=topics,
            user_profile=user_profile,
            route_kind=route_kind,
        )

        try:
            reply = generate_reply(
                safe_text,
                language,
                context=context,
            )
        except TypeError:
            try:
                reply = generate_reply(safe_text, language)
            except Exception as error:
                append_log(f"Local LLM generation fallback failed: {error}")
                return None
        except Exception as error:
            append_log(f"Local LLM generation failed: {error}")
            return None

        if not reply:
            return None

        ok_value = getattr(reply, "ok", True)
        if ok_value is False:
            error_text = str(getattr(reply, "error", "") or "").strip()
            if error_text:
                append_log(f"Local LLM returned non-ok reply: {error_text}")
            return None

        text = str(
            getattr(reply, "text", "") or getattr(reply, "spoken_text", "") or ""
        ).strip()
        if not text:
            return None

        text = self._sanitize_local_llm_reply(
            text=text,
            language=language,
        )
        if not text:
            return None

        source_name = str(getattr(reply, "source", "") or "local_llm").strip() or "local_llm"

        return self._reply(
            language,
            text,
            display_title=self._text(language, "ODPOWIEDŹ", "REPLY"),
            source=source_name,
        )

    def _build_local_llm_context(
        self,
        *,
        normalized_text: str,
        language: str,
        topics: list[str],
        user_profile: dict | None,
        route_kind: str,
    ) -> dict[str, Any]:
        del normalized_text

        memory = getattr(self, "conversation_memory", None)

        recent_context = ""
        recent_payload: list[dict[str, Any]] = []

        if memory is not None:
            summary_method = getattr(memory, "summary_for_prompt", None)
            if callable(summary_method):
                try:
                    recent_context = str(
                        summary_method(
                            limit=6,
                            preferred_language=language,
                        )
                        or ""
                    ).strip()
                except Exception as error:
                    append_log(f"Conversation memory summary build failed: {error}")

            payload_method = getattr(memory, "build_context_payload", None)
            if callable(payload_method):
                try:
                    payload = payload_method(limit=6)
                    if isinstance(payload, list):
                        recent_payload = [
                            dict(item)
                            for item in payload
                            if isinstance(item, dict)
                        ]
                except Exception as error:
                    append_log(f"Conversation memory payload build failed: {error}")

        safe_profile = dict(user_profile or {})
        if recent_context and not safe_profile.get("recent_conversation_context"):
            safe_profile["recent_conversation_context"] = recent_context

        return {
            "topics": list(topics or []),
            "route_kind": str(route_kind or "conversation").strip().lower() or "conversation",
            "recent_context": recent_context,
            "recent_payload": recent_payload,
            "user_profile": safe_profile,
            "conversation_topics": list(topics or []),
            "suggested_actions": [],
        }

    def _sanitize_local_llm_reply(
        self,
        *,
        text: str,
        language: str,
    ) -> str:
        cleaned = clean_response_text(text)
        if not cleaned:
            return ""

        blocked_prefixes = {
            "assistant:",
            "user:",
            "system:",
            "odpowiedź:",
            "reply:",
        }

        lowered = cleaned.lower()
        for prefix in blocked_prefixes:
            if lowered.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                lowered = cleaned.lower()
                break

        cleaned = cleaned.strip(" \n\t-–—")
        if not cleaned:
            return ""

        max_chars = 420 if str(language).lower().startswith("pl") else 380
        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars].rstrip()

            for marker in (". ", "? ", "! "):
                idx = cleaned.rfind(marker)
                if idx >= 40:
                    cleaned = cleaned[: idx + 1].rstrip()
                    break

        return cleaned


__all__ = ["CompanionDialogueLocalLLMMixin"]