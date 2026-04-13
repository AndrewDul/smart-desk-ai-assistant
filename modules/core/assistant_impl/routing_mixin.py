from __future__ import annotations

from typing import Any

from modules.runtime.contracts import InputSource, normalize_text

from .helpers import CommandFlowHelpers
from .language import CommandFlowLanguage
from .memory import CommandFlowMemory
from .models import PreparedCommand
from .normalization import CommandFlowNormalization


class CommandFlowOrchestrator(
    CommandFlowNormalization,
    CommandFlowLanguage,
    CommandFlowMemory,
    CommandFlowHelpers,
):
    """
    Premium command preparation flow for NeXa.

    Responsibilities:
    - sanitize raw user text
    - optionally strip wake phrase
    - normalize utterance through the available normalizer
    - detect effective command language
    - apply semantic override when available
    - pre-parse deterministic actions for the fast lane
    - remember user turns with rich metadata
    - centralize preparation logging
    """

    def __init__(self, assistant: Any) -> None:
        self.assistant = assistant

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(
        self,
        *,
        text: str,
        fallback_language: str = "en",
        source: InputSource = InputSource.VOICE,
        capture_phase: str = "",
        capture_mode: str = "",
        capture_backend: str = "",
        capture_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.prepare(
            text=text,
            fallback_language=fallback_language,
            source=source,
            capture_phase=capture_phase,
            capture_mode=capture_mode,
            capture_backend=capture_backend,
            capture_metadata=capture_metadata,
        ).to_dict()

    def prepare(
        self,
        *,
        text: str,
        fallback_language: str = "en",
        source: InputSource = InputSource.VOICE,
        capture_phase: str = "",
        capture_mode: str = "",
        capture_backend: str = "",
        capture_metadata: dict[str, Any] | None = None,
    ) -> PreparedCommand:
        cleaned = self._compact(text)
        capture_phase_value = str(capture_phase or "").strip()
        capture_mode_value = str(capture_mode or capture_phase_value).strip()
        capture_backend_value = str(capture_backend or "").strip()
        capture_metadata_value = dict(capture_metadata or {})

        capture_notes: list[str] = []
        if capture_phase_value:
            capture_notes.append(f"capture_phase:{capture_phase_value}")
        if capture_mode_value and capture_mode_value != capture_phase_value:
            capture_notes.append(f"capture_mode:{capture_mode_value}")
        if capture_backend_value:
            capture_notes.append(f"capture_backend:{capture_backend_value}")

        if not cleaned:
            prepared = PreparedCommand(
                raw_text="",
                routing_text="",
                normalized_routing_text="",
                detected_language=self._normalize_language(fallback_language),
                normalizer_language_hint=self._normalize_language(fallback_language),
                command_language=self._normalize_language(fallback_language),
                parser_result=None,
                semantic_override_applied=False,
                semantic_override_mode=None,
                semantic_override_source_text=None,
                normalizer_corrections=(),
                source=source,
                ignore=True,
                cancel_requested=False,
                wake_phrase_detected=False,
                capture_phase=capture_phase_value,
                capture_mode=capture_mode_value,
                capture_backend=capture_backend_value,
                capture_metadata=capture_metadata_value,
                notes=["empty_input", *capture_notes],
            )
            self._log_prepared_command(prepared)
            return prepared

        wake_phrase_detected = False
        wake_stripped_text = cleaned
        voice_session = getattr(self.assistant, "voice_session", None)

        heard_wake_phrase = getattr(voice_session, "heard_wake_phrase", None)
        strip_wake_phrase = getattr(voice_session, "strip_wake_phrase", None)

        if source == InputSource.VOICE and callable(heard_wake_phrase) and heard_wake_phrase(cleaned):
            wake_phrase_detected = True
            if callable(strip_wake_phrase):
                candidate = self._compact(strip_wake_phrase(cleaned))
                wake_stripped_text = candidate if candidate else ""

        normalized_utterance = self._normalize_utterance(wake_stripped_text or cleaned)
        routing_text = self._extract_canonical_text(
            normalized_utterance,
            fallback=wake_stripped_text or cleaned,
        )

        detected_lang = self._detect_language(cleaned, fallback_language=fallback_language)
        normalizer_language_hint = self._extract_normalizer_language_hint(
            normalized_utterance,
            fallback_language=detected_lang,
        )

        command_lang = self._prefer_command_language(
            routing_text=routing_text,
            detected_language=detected_lang,
            normalizer_language_hint=normalizer_language_hint,
            fallback_language=fallback_language,
        )

        semantic_override = self._semantic_override(routing_text, command_lang)

        semantic_override_applied = semantic_override is not None
        semantic_override_mode: str | None = None
        semantic_override_source_text: str | None = None

        if semantic_override is not None:
            semantic_override_mode = str(semantic_override.get("mode") or "").strip() or None
            semantic_override_source_text = routing_text
            routing_text = self._compact(str(semantic_override.get("text") or routing_text))
            command_lang = self._normalize_language(
                semantic_override.get("lang") or command_lang
            )

        normalized_routing_text = normalize_text(routing_text)
        ignore = not bool(normalized_routing_text)
        cancel_requested = self._looks_like_cancel_request(routing_text)
        parser_result = None if ignore else self._parse_intent(routing_text)

        prepared = PreparedCommand(
            raw_text=cleaned,
            routing_text=routing_text,
            normalized_routing_text=normalized_routing_text,
            detected_language=detected_lang,
            normalizer_language_hint=normalizer_language_hint,
            command_language=command_lang,
            parser_result=parser_result,
            semantic_override_applied=semantic_override_applied,
            semantic_override_mode=semantic_override_mode,
            semantic_override_source_text=semantic_override_source_text,
            normalizer_corrections=self._extract_normalizer_corrections(normalized_utterance),
            source=source,
            ignore=ignore,
            cancel_requested=cancel_requested,
            wake_phrase_detected=wake_phrase_detected,
            capture_phase=capture_phase_value,
            capture_mode=capture_mode_value,
            capture_backend=capture_backend_value,
            capture_metadata=capture_metadata_value,
            notes=self._build_notes(
                ignore=ignore,
                cancel_requested=cancel_requested,
                wake_phrase_detected=wake_phrase_detected,
                semantic_override_applied=semantic_override_applied,
                parser_result=parser_result,
            )
            + capture_notes,
        )

        setattr(self.assistant, "_last_raw_command_text", prepared.raw_text)
        setattr(self.assistant, "_last_normalized_command_text", prepared.normalized_routing_text)

        self._remember_user_turn(prepared)
        self._log_prepared_command(prepared)

        return prepared

    def prepare_command(self, text: str) -> PreparedCommand:
        return self.prepare(text=text)

    def build_text_command(
        self,
        *,
        text: str,
        fallback_language: str = "en",
    ) -> PreparedCommand:
        return self.prepare(
            text=text,
            fallback_language=fallback_language,
            source=InputSource.TEXT,
        )

    def build_voice_command(
        self,
        *,
        text: str,
        fallback_language: str = "en",
    ) -> PreparedCommand:
        return self.prepare(
            text=text,
            fallback_language=fallback_language,
            source=InputSource.VOICE,
        )

    def extract_pending_override_intent(self, text: str) -> Any | None:
        clean_text = self._compact(text)
        if not clean_text:
            return None

        result = self._parse_intent(clean_text)
        if result is None:
            return None

        action = self._extract_action(result)
        if action in {"", "unknown", "unclear", "confirm_yes", "confirm_no"}:
            return None

        return self._clone_parser_result(result)


__all__ = ["CommandFlowOrchestrator"]