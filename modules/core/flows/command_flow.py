from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.runtime.contracts import InputSource, normalize_text
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class PreparedCommand:
    raw_text: str
    routing_text: str
    normalized_routing_text: str
    detected_language: str
    normalizer_language_hint: str
    command_language: str
    parser_result: Any | None
    semantic_override_applied: bool
    semantic_override_mode: str | None
    semantic_override_source_text: str | None
    normalizer_corrections: tuple[str, ...] = ()
    source: InputSource = InputSource.VOICE
    ignore: bool = False
    cancel_requested: bool = False
    wake_phrase_detected: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def normalized_text(self) -> str:
        return self.normalized_routing_text

    @property
    def language(self) -> str:
        return self.command_language

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_text": self.raw_text,
            "routing_text": self.routing_text,
            "normalized_text": self.normalized_routing_text,
            "normalized_routing_text": self.normalized_routing_text,
            "detected_language": self.detected_language,
            "normalizer_language_hint": self.normalizer_language_hint,
            "command_language": self.command_language,
            "language": self.command_language,
            "parser_result": self.parser_result,
            "semantic_override_applied": self.semantic_override_applied,
            "semantic_override_mode": self.semantic_override_mode,
            "semantic_override_source_text": self.semantic_override_source_text,
            "normalizer_corrections": self.normalizer_corrections,
            "source": self.source,
            "ignore": self.ignore,
            "cancel_requested": self.cancel_requested,
            "wake_phrase_detected": self.wake_phrase_detected,
            "notes": list(self.notes),
        }


class CommandFlowOrchestrator:
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
    ) -> dict[str, Any]:
        return self.prepare(
            text=text,
            fallback_language=fallback_language,
            source=source,
        ).to_dict()

    def prepare(
        self,
        *,
        text: str,
        fallback_language: str = "en",
        source: InputSource = InputSource.VOICE,
    ) -> PreparedCommand:
        cleaned = self._compact(text)
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
                notes=["empty_input"],
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
        routing_text = self._extract_canonical_text(normalized_utterance, fallback=wake_stripped_text or cleaned)

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
            notes=self._build_notes(
                ignore=ignore,
                cancel_requested=cancel_requested,
                wake_phrase_detected=wake_phrase_detected,
                semantic_override_applied=semantic_override_applied,
                parser_result=parser_result,
            ),
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

    def log_route_decision(self, route: Any) -> None:
        route_kind = getattr(route, "kind", None)
        confidence = getattr(route, "confidence", 0.0)
        primary_intent = getattr(route, "primary_intent", "")
        topics = getattr(route, "conversation_topics", []) or []
        notes = getattr(route, "notes", []) or []
        LOGGER.info(
            "Route decision: kind=%s, primary_intent=%s, confidence=%.3f, topics=%s, notes=%s",
            getattr(route_kind, "value", route_kind),
            primary_intent,
            float(confidence or 0.0),
            list(topics),
            list(notes),
        )

    # ------------------------------------------------------------------
    # Normalization and parsing
    # ------------------------------------------------------------------

    def _normalize_utterance(self, text: str) -> Any:
        normalizer = getattr(self.assistant, "utterance_normalizer", None)
        if normalizer is None:
            return self._fallback_normalized_utterance(text)

        method = getattr(normalizer, "normalize", None)
        if not callable(method):
            return self._fallback_normalized_utterance(text)

        try:
            result = method(text)
            return result if result is not None else self._fallback_normalized_utterance(text)
        except Exception as error:
            LOGGER.warning("Utterance normalizer failed: %s", error)
            return self._fallback_normalized_utterance(text)

    def _parse_intent(self, text: str) -> Any | None:
        parser = getattr(self.assistant, "parser", None)
        if parser is None:
            return None

        for method_name in ("parse", "parse_intent", "match", "classify"):
            method = getattr(parser, method_name, None)
            if not callable(method):
                continue

            try:
                return method(text)
            except TypeError:
                try:
                    return method(text=text)
                except TypeError:
                    continue
            except Exception as error:
                LOGGER.warning("Command flow parser call failed on %s: %s", method_name, error)
                return None

        return None

    def _semantic_override(self, routing_text: str, command_language: str) -> dict[str, Any] | None:
        override_method = getattr(self.assistant, "_semantic_override", None)
        if not callable(override_method):
            return None

        try:
            value = override_method(routing_text, command_language)
            return value if isinstance(value, dict) else None
        except Exception as error:
            LOGGER.warning("Semantic override failed: %s", error)
            return None

    # ------------------------------------------------------------------
    # Language
    # ------------------------------------------------------------------

    def _detect_language(self, text: str, *, fallback_language: str) -> str:
        detector = getattr(self.assistant, "_detect_language", None)
        if callable(detector):
            try:
                return self._normalize_language(detector(text) or fallback_language)
            except Exception as error:
                LOGGER.warning("Language detection failed: %s", error)

        lowered = normalize_text(text)
        polish_markers = {
            "jest",
            "czy",
            "pokaz",
            "pokaż",
            "godzina",
            "czas",
            "data",
            "dzien",
            "dzień",
            "przerwa",
            "skupienie",
            "skupienia",
            "przypomnienie",
            "przypomnienia",
            "zapamietaj",
            "zapamiętaj",
            "usun",
            "usuń",
            "wyłącz",
            "wylacz",
            "zamknij",
            "jaki",
            "ktora",
            "która",
        }
        english_markers = {
            "time",
            "date",
            "day",
            "month",
            "year",
            "timer",
            "focus",
            "break",
            "reminder",
            "remember",
            "forget",
            "delete",
            "remove",
            "shutdown",
            "close",
            "what",
            "who",
            "help",
            "status",
        }

        tokens = set(lowered.split())
        polish_hits = len(tokens & polish_markers)
        english_hits = len(tokens & english_markers)

        if polish_hits > english_hits:
            return "pl"
        if english_hits > polish_hits:
            return "en"
        return self._normalize_language(fallback_language)

    def _prefer_command_language(
        self,
        *,
        routing_text: str,
        detected_language: str,
        normalizer_language_hint: str,
        fallback_language: str,
    ) -> str:
        prefer_method = getattr(self.assistant, "_prefer_command_language", None)
        if callable(prefer_method):
            try:
                chosen = prefer_method(
                    routing_text,
                    detected_language,
                    normalizer_language_hint,
                )
                return self._normalize_language(chosen or fallback_language)
            except Exception as error:
                LOGGER.warning("Preferred command language selection failed: %s", error)

        if normalizer_language_hint in {"pl", "en"} and normalizer_language_hint != detected_language:
            return normalizer_language_hint
        if detected_language in {"pl", "en"}:
            return detected_language
        return self._normalize_language(fallback_language)

    def _looks_like_cancel_request(self, text: str) -> bool:
        helper = getattr(self.assistant, "_looks_like_cancel_request", None)
        if callable(helper):
            try:
                return bool(helper(text))
            except Exception:
                pass

        normalized = normalize_text(text)
        return normalized in {
            "cancel",
            "stop",
            "never mind",
            "nevermind",
            "forget it",
            "leave it",
            "anuluj",
            "nieważne",
            "niewazne",
            "zostaw to",
            "zapomnij",
        }

    # ------------------------------------------------------------------
    # Memory and logging
    # ------------------------------------------------------------------

    def _remember_user_turn(self, prepared: PreparedCommand) -> None:
        remember_method = getattr(self.assistant, "_remember_user_turn", None)
        if not callable(remember_method):
            return

        metadata = {
            "routing_text": prepared.routing_text,
            "normalized_text": prepared.normalized_routing_text,
            "detected_language": prepared.detected_language,
            "normalizer_language_hint": prepared.normalizer_language_hint,
            "corrections": list(prepared.normalizer_corrections),
            "source": prepared.source.value,
            "wake_phrase_detected": prepared.wake_phrase_detected,
            "cancel_requested": prepared.cancel_requested,
        }

        if prepared.semantic_override_applied:
            metadata.update(
                {
                    "semantic_override_applied": True,
                    "semantic_override_mode": prepared.semantic_override_mode,
                    "semantic_override_source_text": prepared.semantic_override_source_text,
                }
            )

        try:
            remember_method(
                prepared.raw_text,
                language=prepared.command_language,
                metadata=metadata,
            )
        except TypeError:
            remember_method(prepared.raw_text, prepared.command_language)

    def _log_prepared_command(self, prepared: PreparedCommand) -> None:
        LOGGER.info(
            "Prepared command: raw=%s | routing=%s | normalized=%s | detected_lang=%s | "
            "normalizer_hint=%s | command_lang=%s | semantic_override=%s | "
            "semantic_override_mode=%s | corrections=%s | source=%s | wake=%s | cancel=%s | ignore=%s",
            prepared.raw_text,
            prepared.routing_text,
            prepared.normalized_routing_text,
            prepared.detected_language,
            prepared.normalizer_language_hint,
            prepared.command_language,
            prepared.semantic_override_applied,
            prepared.semantic_override_mode or "",
            list(prepared.normalizer_corrections),
            prepared.source.value,
            prepared.wake_phrase_detected,
            prepared.cancel_requested,
            prepared.ignore,
        )

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback_normalized_utterance(text: str) -> dict[str, Any]:
        cleaned = " ".join(str(text or "").split()).strip()
        return {
            "canonical_text": cleaned,
            "detected_language_hint": "",
            "corrections_applied": [],
        }

    @staticmethod
    def _extract_canonical_text(normalized_utterance: Any, *, fallback: str) -> str:
        if isinstance(normalized_utterance, dict):
            value = normalized_utterance.get("canonical_text")
            return " ".join(str(value or fallback).split()).strip()

        value = getattr(normalized_utterance, "canonical_text", None)
        return " ".join(str(value or fallback).split()).strip()

    def _extract_normalizer_language_hint(
        self,
        normalized_utterance: Any,
        *,
        fallback_language: str,
    ) -> str:
        if isinstance(normalized_utterance, dict):
            value = normalized_utterance.get("detected_language_hint", fallback_language)
            return self._normalize_language(value or fallback_language)

        value = getattr(normalized_utterance, "detected_language_hint", fallback_language)
        return self._normalize_language(value or fallback_language)

    @staticmethod
    def _extract_normalizer_corrections(normalized_utterance: Any) -> tuple[str, ...]:
        if isinstance(normalized_utterance, dict):
            raw = normalized_utterance.get("corrections_applied", []) or []
            return tuple(str(item) for item in raw if str(item).strip())

        raw = getattr(normalized_utterance, "corrections_applied", []) or []
        return tuple(str(item) for item in raw if str(item).strip())

    @staticmethod
    def _clone_parser_result(result: Any) -> Any:
        if result is None:
            return None

        if isinstance(result, dict):
            return dict(result)

        try:
            payload = {
                "action": getattr(result, "action", ""),
                "data": getattr(result, "data", {}),
                "confidence": getattr(result, "confidence", 0.0),
                "needs_confirmation": getattr(result, "needs_confirmation", False),
                "suggestions": list(getattr(result, "suggestions", []) or []),
                "normalized_text": getattr(result, "normalized_text", ""),
            }
            result_type = type(result)
            try:
                return result_type(**payload)
            except Exception:
                return payload
        except Exception:
            return result

    @staticmethod
    def _extract_action(parser_result: Any) -> str:
        if parser_result is None:
            return ""

        if isinstance(parser_result, dict):
            for key in ("action", "primary_intent", "intent", "name"):
                value = parser_result.get(key)
                if value:
                    return str(value).strip().lower()
            return ""

        for attr in ("action", "primary_intent", "intent", "name"):
            value = getattr(parser_result, attr, None)
            if value:
                return str(value).strip().lower()

        return ""

    @staticmethod
    def _build_notes(
        *,
        ignore: bool,
        cancel_requested: bool,
        wake_phrase_detected: bool,
        semantic_override_applied: bool,
        parser_result: Any | None,
    ) -> list[str]:
        notes: list[str] = []
        if ignore:
            notes.append("ignore")
        if cancel_requested:
            notes.append("cancel_requested")
        if wake_phrase_detected:
            notes.append("wake_phrase_detected")
        if semantic_override_applied:
            notes.append("semantic_override_applied")
        if parser_result is not None:
            notes.append("parser_result_ready")
        return notes

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "en").strip().lower()
        return "pl" if normalized.startswith("pl") else "en"

    @staticmethod
    def _compact(text: str) -> str:
        return " ".join(str(text or "").split()).strip()


__all__ = ["CommandFlowOrchestrator", "PreparedCommand"]