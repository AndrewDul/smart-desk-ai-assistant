from __future__ import annotations

from typing import Any

from modules.understanding.parsing.normalization import (
    CANCEL_PHRASES,
    MICRO_REPLY_PHRASES,
    contains_any_phrase,
    exact_phrase_match,
    is_cancel_request,
    normalize_text,
    tokenize,
)

from .helpers import LOGGER, CommandFlowHelpers


class CommandFlowLanguage(CommandFlowHelpers):
    """Language selection and cancel detection helpers."""

    assistant: Any

    _POLISH_MARKERS = {
        "jest",
        "czy",
        "pokaz",
        "pokaż",
        "godzina",
        "czas",
        "data",
        "dzien",
        "dzień",
        "miesiac",
        "miesiąc",
        "rok",
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
        "jaka",
        "jakie",
        "ktora",
        "która",
        "pomoc",
        "stan",
        "tak",
        "nie",
        "jasne",
        "okej",
        "dobrze",
        "spij",
        "śpij",
        "czuwanie",
        "pa",
    }

    _ENGLISH_MARKERS = {
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
        "yes",
        "no",
        "sure",
        "okay",
        "ok",
        "sleep",
        "standby",
        "bye",
    }

    _POLISH_SHORT_PHRASES = {
        "tak",
        "nie",
        "jasne",
        "okej",
        "dobrze",
        "anuluj",
        "zostaw to",
        "nieważne",
        "niewazne",
        "śpij",
        "spij",
        "wróć do czuwania",
        "wroc do czuwania",
        "do widzenia",
        "pa",
    }

    _ENGLISH_SHORT_PHRASES = {
        "yes",
        "no",
        "sure",
        "ok",
        "okay",
        "cancel",
        "never mind",
        "sleep",
        "standby",
        "go to sleep",
        "stop listening",
        "goodbye",
        "bye",
    }

    def _detect_language(self, text: str, *, fallback_language: str) -> str:
        detector = getattr(self.assistant, "_detect_language", None)
        if callable(detector):
            try:
                detected = self._normalize_language(detector(text) or fallback_language)
                if detected in {"pl", "en"}:
                    return detected
            except Exception as error:
                LOGGER.warning("Language detection failed: %s", error)

        raw_text = str(text or "")
        lowered = normalize_text(raw_text)
        tokens = set(tokenize(lowered))

        if not lowered:
            return self._normalize_language(fallback_language)

        polish_hits = 0
        english_hits = 0

        polish_hits += len(tokens & self._POLISH_MARKERS)
        english_hits += len(tokens & self._ENGLISH_MARKERS)

        if any(ch in raw_text for ch in "ąćęłńóśźżĄĆĘŁŃÓŚŹŻ"):
            polish_hits += 2

        if exact_phrase_match(lowered, self._POLISH_SHORT_PHRASES):
            polish_hits += 3
        if exact_phrase_match(lowered, self._ENGLISH_SHORT_PHRASES):
            english_hits += 3

        if contains_any_phrase(lowered, {"która godzina", "jaka data", "jaki dzień"}):
            polish_hits += 2
        if contains_any_phrase(lowered, {"what time", "what day", "what date"}):
            english_hits += 2

        if lowered in {normalize_text(item) for item in MICRO_REPLY_PHRASES}:
            if lowered in {normalize_text(item) for item in self._POLISH_SHORT_PHRASES}:
                polish_hits += 2
            elif lowered in {normalize_text(item) for item in self._ENGLISH_SHORT_PHRASES}:
                english_hits += 2

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
                normalized = self._normalize_language(chosen or fallback_language)
                if normalized in {"pl", "en"}:
                    return normalized
            except Exception as error:
                LOGGER.warning("Preferred command language selection failed: %s", error)

        normalized_text = normalize_text(routing_text)

        if normalized_text in {normalize_text(item) for item in self._POLISH_SHORT_PHRASES}:
            return "pl"
        if normalized_text in {normalize_text(item) for item in self._ENGLISH_SHORT_PHRASES}:
            return "en"

        if normalizer_language_hint in {"pl", "en"} and normalizer_language_hint != detected_language:
            if exact_phrase_match(normalized_text, MICRO_REPLY_PHRASES):
                return self._normalize_language(fallback_language)
            return normalizer_language_hint

        if detected_language in {"pl", "en"}:
            return detected_language

        return self._normalize_language(fallback_language)

    def _looks_like_cancel_request(self, text: str) -> bool:
        if self._pending_duration_unknown_answer(text):
            return False

        helper = getattr(self.assistant, "_looks_like_cancel_request", None)
        if callable(helper):
            try:
                return bool(helper(text))
            except Exception:
                pass

        normalized = normalize_text(text)
        if not normalized:
            return False

        if is_cancel_request(normalized):
            return True

        if exact_phrase_match(normalized, CANCEL_PHRASES):
            return True

        return contains_any_phrase(normalized, CANCEL_PHRASES)

    def _pending_duration_unknown_answer(self, text: str) -> bool:
        pending = getattr(self.assistant, "pending_follow_up", None)
        if not isinstance(pending, dict):
            return False

        follow_type = str(pending.get("type", "") or "").strip()
        if follow_type not in {"timer_duration", "focus_duration", "break_duration"}:
            return False

        normalized = normalize_text(text)
        compact = normalized.replace(" ", "")

        unknown_answers = {
            "i dont know",
            "i don t know",
            "i do not know",
            "dont know",
            "don t know",
            "do not know",
            "not sure",
            "no idea",
            "nie wiem",
            "nie mam pojecia",
            "nie mam pojęcia",
            "trudno powiedziec",
            "trudno powiedzieć",
        }

        normalized_answers = {normalize_text(item) for item in unknown_answers}
        compact_answers = {item.replace(" ", "") for item in normalized_answers}

        return normalized in normalized_answers or compact in compact_answers


__all__ = ["CommandFlowLanguage"]