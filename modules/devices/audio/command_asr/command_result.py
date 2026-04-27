from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from modules.devices.audio.command_asr.command_language import CommandLanguage


class CommandRecognitionStatus(str, Enum):
    """Recognition state for command-first ASR."""

    MATCHED = "matched"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True, slots=True)
class CommandRecognitionResult:
    """Result returned by a command-first recognizer."""

    status: CommandRecognitionStatus
    transcript: str
    normalized_transcript: str
    language: CommandLanguage
    confidence: float
    intent_key: str | None = None
    matched_phrase: str | None = None
    alternatives: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if self.status is CommandRecognitionStatus.MATCHED:
            if not self.intent_key:
                raise ValueError("matched result requires intent_key")
            if not self.matched_phrase:
                raise ValueError("matched result requires matched_phrase")

    @property
    def is_match(self) -> bool:
        return self.status is CommandRecognitionStatus.MATCHED

    @classmethod
    def matched(
        cls,
        *,
        transcript: str,
        normalized_transcript: str,
        language: CommandLanguage,
        confidence: float,
        intent_key: str,
        matched_phrase: str,
        alternatives: tuple[str, ...] = (),
    ) -> CommandRecognitionResult:
        return cls(
            status=CommandRecognitionStatus.MATCHED,
            transcript=transcript,
            normalized_transcript=normalized_transcript,
            language=language,
            confidence=confidence,
            intent_key=intent_key,
            matched_phrase=matched_phrase,
            alternatives=alternatives,
        )

    @classmethod
    def no_match(
        cls,
        *,
        transcript: str,
        normalized_transcript: str,
        language: CommandLanguage,
    ) -> CommandRecognitionResult:
        return cls(
            status=CommandRecognitionStatus.NO_MATCH,
            transcript=transcript,
            normalized_transcript=normalized_transcript,
            language=language,
            confidence=0.0,
        )

    @classmethod
    def ambiguous(
        cls,
        *,
        transcript: str,
        normalized_transcript: str,
        language: CommandLanguage,
        alternatives: tuple[str, ...],
    ) -> CommandRecognitionResult:
        return cls(
            status=CommandRecognitionStatus.AMBIGUOUS,
            transcript=transcript,
            normalized_transcript=normalized_transcript,
            language=language,
            confidence=0.0,
            alternatives=alternatives,
        )