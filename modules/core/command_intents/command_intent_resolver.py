from __future__ import annotations

from modules.core.command_intents.confidence_policy import ConfidencePolicy
from modules.core.command_intents.intent import CommandIntent
from modules.core.command_intents.intent_result import (
    CommandIntentResolutionResult,
)
from modules.core.command_intents.system_intents import (
    get_system_intent_definition,
)
from modules.core.command_intents.visual_shell_intents import (
    get_visual_shell_intent_definition,
)
from modules.devices.audio.command_asr.command_result import (
    CommandRecognitionResult,
    CommandRecognitionStatus,
)


class CommandIntentResolver:
    """Resolve command recognizer output into deterministic command intents."""

    def __init__(self, confidence_policy: ConfidencePolicy | None = None) -> None:
        self._confidence_policy = confidence_policy or ConfidencePolicy()

    @property
    def confidence_policy(self) -> ConfidencePolicy:
        return self._confidence_policy

    def resolve(
        self,
        recognition: CommandRecognitionResult,
    ) -> CommandIntentResolutionResult:
        if recognition.status is CommandRecognitionStatus.AMBIGUOUS:
            return CommandIntentResolutionResult.ambiguous(
                source_text=recognition.transcript,
                normalized_source_text=recognition.normalized_transcript,
                language=recognition.language,
                alternatives=recognition.alternatives,
            )

        rejection_reason = self._confidence_policy.rejection_reason(recognition)
        if rejection_reason == "no_match":
            return CommandIntentResolutionResult.no_intent(
                source_text=recognition.transcript,
                normalized_source_text=recognition.normalized_transcript,
                language=recognition.language,
                reason=rejection_reason,
            )

        if rejection_reason is not None:
            return CommandIntentResolutionResult.rejected_low_confidence(
                source_text=recognition.transcript,
                normalized_source_text=recognition.normalized_transcript,
                language=recognition.language,
                confidence=recognition.confidence,
                reason=rejection_reason,
            )

        if recognition.intent_key is None:
            return CommandIntentResolutionResult.no_intent(
                source_text=recognition.transcript,
                normalized_source_text=recognition.normalized_transcript,
                language=recognition.language,
                reason="missing_intent_key",
            )

        definition = self._find_definition(recognition.intent_key)
        if definition is None:
            return CommandIntentResolutionResult.unknown_intent(
                source_text=recognition.transcript,
                normalized_source_text=recognition.normalized_transcript,
                language=recognition.language,
                confidence=recognition.confidence,
                intent_key=recognition.intent_key,
            )

        intent = CommandIntent.from_definition(
            definition=definition,
            language=recognition.language,
            source_text=recognition.transcript,
            normalized_source_text=recognition.normalized_transcript,
            confidence=recognition.confidence,
        )

        return CommandIntentResolutionResult.resolved(intent)

    @staticmethod
    def _find_definition(intent_key: str):
        return (
            get_visual_shell_intent_definition(intent_key)
            or get_system_intent_definition(intent_key)
        )