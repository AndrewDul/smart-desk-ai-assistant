from __future__ import annotations

from typing import Any

from modules.runtime.contracts import normalize_text
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__package__ or __name__)


class CommandFlowHelpers:
    """Small shared helpers for command preparation."""

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


__all__ = ["LOGGER", "CommandFlowHelpers", "normalize_text"]