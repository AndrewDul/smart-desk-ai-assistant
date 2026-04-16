from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable


@dataclass(slots=True)
class WakeAcknowledgementResult:
    text: str
    language: str
    spoken: bool
    prefetched_phrases: tuple[str, ...]


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
    ) -> None:
        self.voice_output = voice_output
        self.phrase_builder = phrase_builder
        self.prefetch_on_boot = bool(prefetch_on_boot)
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

    def speak(self, *, language: str | None = None) -> WakeAcknowledgementResult:
        normalized_language = self._normalize_language(language)
        text = self._build_phrase()
        if not text:
            text = "I'm listening."

        speak_method = getattr(self.voice_output, "speak", None)
        spoken = False
        if callable(speak_method):
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
        )

    def _build_phrase(self) -> str:
        if not callable(self.phrase_builder):
            return ""
        try:
            return self._normalize_phrase(self.phrase_builder())
        except Exception:
            return ""

    @staticmethod
    def _normalize_phrase(value: object) -> str:
        return " ".join(str(value or "").split()).strip()

    @staticmethod
    def _normalize_language(language: str | None) -> str:
        normalized = str(language or "en").strip().lower()
        return normalized if normalized in {"pl", "en"} else "en"

    def _normalize_languages(self, languages: Iterable[str]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(self._normalize_language(item) for item in languages))
        return normalized or ("en",)