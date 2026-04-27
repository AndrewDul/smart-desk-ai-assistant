from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from modules.devices.audio.command_asr.command_language import CommandLanguage


@dataclass(frozen=True, slots=True)
class FallbackDecision:
    """Decision describing why Voice Engine v2 should use fallback."""

    required: bool
    reason: str = ""
    language: CommandLanguage = CommandLanguage.UNKNOWN

    def __post_init__(self) -> None:
        if self.required and not self.reason.strip():
            raise ValueError("fallback decision requires a reason")


class FallbackPipeline(Protocol):
    """Protocol for later full STT / router / LLM fallback integration."""

    def decide(
        self,
        *,
        transcript: str,
        language: CommandLanguage,
        reason: str,
    ) -> FallbackDecision:
        """Return fallback decision for a non-command turn."""


class NullFallbackPipeline:
    """Safe placeholder fallback pipeline for pre-runtime integration tests."""

    def decide(
        self,
        *,
        transcript: str,
        language: CommandLanguage,
        reason: str,
    ) -> FallbackDecision:
        return FallbackDecision(
            required=True,
            reason=reason,
            language=language,
        )