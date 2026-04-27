from __future__ import annotations

from dataclasses import dataclass

from modules.devices.audio.command_asr.command_result import (
    CommandRecognitionResult,
    CommandRecognitionStatus,
)


@dataclass(frozen=True, slots=True)
class ConfidencePolicyConfig:
    """Confidence thresholds for deterministic command intent resolution."""

    min_confidence: float = 0.80

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0.0 and 1.0")


class ConfidencePolicy:
    """Accept/reject policy for command recognition results."""

    def __init__(self, config: ConfidencePolicyConfig | None = None) -> None:
        self._config = config or ConfidencePolicyConfig()

    @property
    def config(self) -> ConfidencePolicyConfig:
        return self._config

    def rejection_reason(self, result: CommandRecognitionResult) -> str | None:
        if result.status is CommandRecognitionStatus.NO_MATCH:
            return "no_match"

        if result.status is CommandRecognitionStatus.AMBIGUOUS:
            return "ambiguous"

        if result.confidence < self._config.min_confidence:
            return "confidence_below_threshold"

        return None