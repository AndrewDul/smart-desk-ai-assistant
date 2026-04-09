from __future__ import annotations

import random


class VoiceSessionAcknowledgements:
    """Acknowledgement phrase helpers for the voice session."""

    wake_acknowledgements: tuple[str, ...]
    thinking_acknowledgements_en: tuple[str, ...]
    thinking_acknowledgements_pl: tuple[str, ...]
    _lock: object
    _rng: random.Random
    _last_wake_acknowledgement: str | None
    _last_thinking_acknowledgement_by_language: dict[str, str | None]

    def build_wake_acknowledgement(self) -> str:
        with self._lock:
            chosen = self._choose_non_repeating_phrase(
                self.wake_acknowledgements,
                self._last_wake_acknowledgement,
                rng=self._rng,
            )
            self._last_wake_acknowledgement = chosen
            return chosen

    def build_thinking_acknowledgement(self, language: str) -> str:
        normalized_language = self._normalize_language(language)
        phrase_pool = (
            self.thinking_acknowledgements_pl
            if normalized_language == "pl"
            else self.thinking_acknowledgements_en
        )

        with self._lock:
            previous = self._last_thinking_acknowledgement_by_language.get(normalized_language)
            chosen = self._choose_non_repeating_phrase(
                phrase_pool,
                previous,
                rng=self._rng,
            )
            self._last_thinking_acknowledgement_by_language[normalized_language] = chosen
            return chosen

    @staticmethod
    def _normalize_phrase_for_output(text: str) -> str:
        return " ".join(str(text or "").split()).strip()

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "").strip().lower()
        if normalized in {"pl", "en"}:
            return normalized
        return "en"

    @staticmethod
    def _choose_non_repeating_phrase(
        phrases: tuple[str, ...] | list[str],
        previous: str | None,
        *,
        rng: random.Random | None = None,
    ) -> str:
        safe_rng = rng or random
        pool = [phrase for phrase in phrases if phrase and phrase != previous]
        if not pool:
            pool = [phrase for phrase in phrases if phrase]

        if not pool:
            return ""

        return safe_rng.choice(pool)


__all__ = ["VoiceSessionAcknowledgements"]