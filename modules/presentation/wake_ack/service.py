from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(slots=True)
class WakeAcknowledgementResult:
    text: str
    language: str
    spoken: bool
    prefetched_phrases: tuple[str, ...]
    strategy: str = "standard"
    output_hold_seconds: float | None = None
    word_count: int = 0


class WakeAcknowledgementService:
    """
    Fast-path wake acknowledgement orchestration.

    Responsibilities:
    - prefetch short wake acknowledgement phrases into the TTS pipeline cache
    - resolve the next acknowledgement phrase through the session phrase builder
    - speak the acknowledgement through the voice output backend

    The service is intentionally narrow. It does not manage session transitions,
    active windows, or main-loop flow control.
    """

    def __init__(
        self,
        *,
        voice_output: Any,
        phrase_builder: Callable[[], str] | None,
        phrase_inventory: Iterable[str] | None = None,
        prefetch_on_boot: bool = True,
        prefer_fast_phrase_on_wake: bool = True,
        fast_phrase_max_words: int = 2,
        fast_output_hold_seconds: float = 0.04,
    ) -> None:
        self.voice_output = voice_output
        self.phrase_builder = phrase_builder
        self.prefetch_on_boot = bool(prefetch_on_boot)
        self.prefer_fast_phrase_on_wake = bool(prefer_fast_phrase_on_wake)
        self.fast_phrase_max_words = max(1, int(fast_phrase_max_words))
        self.fast_output_hold_seconds = max(0.0, float(fast_output_hold_seconds))
        self._phrase_inventory = tuple(
            self._normalize_phrase(item)
            for item in (phrase_inventory or [])
            if self._normalize_phrase(item)
        )

    def prefetch_boot_inventory(self, *, languages: Iterable[str] = ("en",)) -> tuple[str, ...]:
        if not self.prefetch_on_boot:
            return tuple()

        prepare_method = getattr(self.voice_output, "prepare_speech", None)
        if not callable(prepare_method):
            return tuple()

        prefetched: list[str] = []
        for language in self._normalize_languages(languages):
            for phrase in self._phrase_inventory:
                try:
                    prepare_method(phrase, language=language)
                    prefetched.append(f"{language}:{phrase}")
                except Exception:
                    continue
        return tuple(prefetched)

    def speak(
        self,
        *,
        language: str | None = None,
        prefer_fast_phrase: bool | None = None,
    ) -> WakeAcknowledgementResult:
        normalized_language = self._normalize_language(language)
        fast_mode = self.prefer_fast_phrase_on_wake if prefer_fast_phrase is None else bool(prefer_fast_phrase)
        strategy = "fast" if fast_mode else "standard"
        text = self._build_phrase(prefer_fast_phrase=fast_mode)
        if not text:
            text = "I'm listening."
            strategy = "fallback"

        output_hold_seconds = self.fast_output_hold_seconds if strategy == "fast" else None
        speak_method = getattr(self.voice_output, "speak", None)
        spoken = False
        if callable(speak_method):
            try:
                spoken = bool(
                    speak_method(
                        text,
                        language=normalized_language,
                        output_hold_seconds=output_hold_seconds,
                    )
                )
            except TypeError:
                try:
                    spoken = bool(speak_method(text, language=normalized_language))
                except TypeError:
                    spoken = bool(speak_method(text))

        return WakeAcknowledgementResult(
            text=text,
            language=normalized_language,
            spoken=spoken,
            prefetched_phrases=tuple(
                f"{lang}:{phrase}"
                for lang in self._normalize_languages((normalized_language,))
                for phrase in self._phrase_inventory
            ),
            strategy=strategy,
            output_hold_seconds=output_hold_seconds,
            word_count=self._word_count(text),
        )

    def _build_phrase(self, *, prefer_fast_phrase: bool = False) -> str:
        candidate = ""
        if callable(self.phrase_builder):
            try:
                candidate = self._normalize_phrase(self.phrase_builder())
            except Exception:
                candidate = ""

        if not prefer_fast_phrase:
            return candidate

        if self._is_fast_phrase(candidate):
            return candidate

        fast_inventory = self._fast_phrase_inventory()
        if fast_inventory:
            return fast_inventory[0]

        return candidate

    @staticmethod
    def _normalize_phrase(value: object) -> str:
        return " ".join(str(value or "").split()).strip()

    def _fast_phrase_inventory(self) -> tuple[str, ...]:
        phrases = [phrase for phrase in self._phrase_inventory if self._is_fast_phrase(phrase)]
        return tuple(sorted(dict.fromkeys(phrases), key=lambda item: (self._word_count(item), len(item), item)))

    def _is_fast_phrase(self, phrase: str) -> bool:
        return self._word_count(phrase) <= self.fast_phrase_max_words

    @staticmethod
    def _word_count(text: str) -> int:
        return len([part for part in str(text or "").split() if part.strip()])

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "en").strip().lower()
        return normalized if normalized in {"pl", "en"} else "en"

    def _normalize_languages(self, languages: Iterable[str]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(self._normalize_language(item) for item in languages))
        return normalized or ("en",)