from __future__ import annotations

import re
import unicodedata


class VoiceSessionMatching:
    """Wake phrase and cancel phrase matching helpers for the voice session."""

    _WAKE_RELATED_ALIASES = (
        "nexa",
        "nexta",
        "neksa",
        "nexaah",
        "nex",
    )

    _WAKE_BOUNDARY_FILLER_WORDS = {
        "hey",
        "hi",
        "hello",
        "ok",
        "okay",
        "yo",
        "please",
        "hej",
        "halo",
        "dobra",
        "okej",
        "okey",
        "prosze",
        "proszę",
    }

    _MAX_WAKE_ONLY_TOKENS = 3

    _wake_phrase_aliases: tuple[str, ...]
    _wake_phrase_patterns: tuple[re.Pattern[str], ...]
    _wake_only_patterns: tuple[re.Pattern[str], ...]
    _cancel_patterns: tuple[re.Pattern[str], ...]

    def heard_wake_phrase(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False

        if self._looks_like_wake_only_text(normalized):
            return True

        for pattern in self._wake_phrase_patterns:
            if pattern.search(normalized):
                return True

        compact = self._compact_text(normalized)
        if compact.startswith("nex") and len(compact) <= 8:
            return True

        return False

    def strip_wake_phrase(self, text: str) -> str:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return ""

        normalized = self._normalize_text(cleaned)
        if not normalized:
            return ""

        if self._looks_like_wake_only_text(normalized):
            return ""

        stripped = normalized
        for phrase in self._wake_phrase_aliases:
            pattern = self._build_phrase_pattern(phrase)
            stripped = pattern.sub(" ", stripped)

        stripped = re.sub(r"\s+", " ", stripped).strip(" ,.:;!?-")
        return stripped.strip()

    def looks_like_cancel_request(self, text: str) -> bool:
        normalized = self._normalize_text(text)
        if not normalized:
            return False

        for pattern in self._cancel_patterns:
            if pattern.search(normalized):
                return True
        return False

    @classmethod
    def _build_wake_aliases(cls, wake_phrases: tuple[str, ...]) -> tuple[str, ...]:
        aliases: list[str] = []
        seen: set[str] = set()

        def add(value: str) -> None:
            normalized = cls._normalize_text(value)
            if normalized and normalized not in seen:
                aliases.append(normalized)
                seen.add(normalized)

        for phrase in wake_phrases:
            add(phrase)
            compact = cls._compact_text(phrase)
            if compact == "nexa" or phrase == "nexa":
                for alias in cls._WAKE_RELATED_ALIASES:
                    add(alias)

        return tuple(aliases) if aliases else ("nexa",)

    @classmethod
    def _build_phrase_pattern(cls, phrase: str) -> re.Pattern[str]:
        body = cls._phrase_to_flexible_body(phrase)
        if not body:
            return re.compile(r"$^")
        return re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])")

    @classmethod
    def _build_wake_only_pattern(cls, phrase: str) -> re.Pattern[str]:
        body = cls._phrase_to_flexible_body(phrase)
        if not body:
            return re.compile(r"$^")

        fillers = sorted((re.escape(word) for word in cls._WAKE_BOUNDARY_FILLER_WORDS), key=len, reverse=True)
        filler_group = r"(?:%s)" % "|".join(fillers) if fillers else r"(?:)"
        optional_prefix = rf"(?:{filler_group}\s+)?"
        optional_suffix = rf"(?:\s+{filler_group})?"
        return re.compile(rf"^\s*{optional_prefix}{body}{optional_suffix}\s*$")

    @classmethod
    def _phrase_to_flexible_body(cls, phrase: str) -> str:
        normalized = cls._normalize_text(phrase)
        parts = [re.escape(part) for part in normalized.split() if part]
        if not parts:
            return ""
        return r"[\s'-]*".join(parts)

    @classmethod
    def _looks_like_wake_only_text(cls, normalized_text: str) -> bool:
        tokens = [token for token in normalized_text.split() if token]
        if not tokens:
            return False

        if len(tokens) > cls._MAX_WAKE_ONLY_TOKENS:
            return False

        for pattern in (
            cls._build_wake_only_pattern(alias)
            for alias in cls._WAKE_RELATED_ALIASES
        ):
            if pattern.fullmatch(normalized_text):
                return True

        filtered_tokens = [
            token
            for token in tokens
            if token not in cls._WAKE_BOUNDARY_FILLER_WORDS
        ]
        if not filtered_tokens:
            return False

        return all(cls._is_wake_alias_token(token) for token in filtered_tokens)

    @classmethod
    def _is_wake_alias_token(cls, token: str) -> bool:
        compact = cls._compact_text(token)
        if not compact:
            return False
        if compact in {"nexa", "nexta", "neksa", "nexaah", "nex"}:
            return True
        return compact.startswith("nex") and len(compact) <= 8

    @staticmethod
    def _normalize_phrase_boundaries(text: str) -> str:
        normalized = str(text or "")
        normalized = re.sub(r"[_/\\|]+", " ", normalized)
        normalized = re.sub(r"[,:;!?]+", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

    @staticmethod
    def _compact_text(text: str) -> str:
        normalized = VoiceSessionMatching._normalize_text(text)
        return re.sub(r"[^a-z0-9]", "", normalized)

    @staticmethod
    def _normalize_text(text: str) -> str:
        raw = str(text or "").strip().lower()
        if not raw:
            return ""

        normalized = unicodedata.normalize("NFKD", raw)
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))

        normalized = normalized.replace("ł", "l")
        normalized = normalized.replace("ß", "ss")
        normalized = normalized.replace("’", "'")
        normalized = normalized.replace("`", "'")

        normalized = re.sub(r"[_/\\|]+", " ", normalized)
        normalized = re.sub(r"[.,:;!?()\[\]{}]+", " ", normalized)
        normalized = re.sub(r"[^a-z0-9\s'-]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()

        return normalized


__all__ = ["VoiceSessionMatching"]