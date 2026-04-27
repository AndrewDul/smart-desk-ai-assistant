from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from modules.core.command_intents.intent import CommandIntent
from modules.devices.audio.command_asr.command_language import CommandLanguage


class CommandIntentResolutionStatus(str, Enum):
    """Resolution status for deterministic command intents."""

    RESOLVED = "resolved"
    NO_INTENT = "no_intent"
    REJECTED_LOW_CONFIDENCE = "rejected_low_confidence"
    AMBIGUOUS = "ambiguous"
    UNKNOWN_INTENT = "unknown_intent"


@dataclass(frozen=True, slots=True)
class CommandIntentResolutionResult:
    """Result returned by CommandIntentResolver."""

    status: CommandIntentResolutionStatus
    confidence: float
    language: CommandLanguage
    source_text: str
    normalized_source_text: str
    intent: CommandIntent | None = None
    reason: str = ""
    alternatives: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")

        if self.status is CommandIntentResolutionStatus.RESOLVED:
            if self.intent is None:
                raise ValueError("resolved result requires intent")

        if self.status is CommandIntentResolutionStatus.AMBIGUOUS:
            if not self.alternatives:
                raise ValueError("ambiguous result requires alternatives")

    @property
    def is_resolved(self) -> bool:
        return self.status is CommandIntentResolutionStatus.RESOLVED

    @classmethod
    def resolved(cls, intent: CommandIntent) -> CommandIntentResolutionResult:
        return cls(
            status=CommandIntentResolutionStatus.RESOLVED,
            confidence=intent.confidence,
            language=intent.language,
            source_text=intent.source_text,
            normalized_source_text=intent.normalized_source_text,
            intent=intent,
        )

    @classmethod
    def no_intent(
        cls,
        *,
        source_text: str,
        normalized_source_text: str,
        language: CommandLanguage,
        reason: str = "no_match",
    ) -> CommandIntentResolutionResult:
        return cls(
            status=CommandIntentResolutionStatus.NO_INTENT,
            confidence=0.0,
            language=language,
            source_text=source_text,
            normalized_source_text=normalized_source_text,
            reason=reason,
        )

    @classmethod
    def rejected_low_confidence(
        cls,
        *,
        source_text: str,
        normalized_source_text: str,
        language: CommandLanguage,
        confidence: float,
        reason: str,
    ) -> CommandIntentResolutionResult:
        return cls(
            status=CommandIntentResolutionStatus.REJECTED_LOW_CONFIDENCE,
            confidence=confidence,
            language=language,
            source_text=source_text,
            normalized_source_text=normalized_source_text,
            reason=reason,
        )

    @classmethod
    def ambiguous(
        cls,
        *,
        source_text: str,
        normalized_source_text: str,
        language: CommandLanguage,
        alternatives: tuple[str, ...],
        reason: str = "ambiguous",
    ) -> CommandIntentResolutionResult:
        return cls(
            status=CommandIntentResolutionStatus.AMBIGUOUS,
            confidence=0.0,
            language=language,
            source_text=source_text,
            normalized_source_text=normalized_source_text,
            alternatives=alternatives,
            reason=reason,
        )

    @classmethod
    def unknown_intent(
        cls,
        *,
        source_text: str,
        normalized_source_text: str,
        language: CommandLanguage,
        confidence: float,
        intent_key: str,
    ) -> CommandIntentResolutionResult:
        return cls(
            status=CommandIntentResolutionStatus.UNKNOWN_INTENT,
            confidence=confidence,
            language=language,
            source_text=source_text,
            normalized_source_text=normalized_source_text,
            reason=f"unknown_intent:{intent_key}",
        )