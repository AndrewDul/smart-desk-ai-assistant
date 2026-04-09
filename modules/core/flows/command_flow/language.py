from __future__ import annotations

from typing import Any

from .helpers import LOGGER, CommandFlowHelpers, normalize_text


class CommandFlowLanguage(CommandFlowHelpers):
    """Language selection and cancel detection helpers."""

    assistant: Any

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


__all__ = ["CommandFlowLanguage"]