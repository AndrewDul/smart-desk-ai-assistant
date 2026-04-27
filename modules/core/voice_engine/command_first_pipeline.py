from __future__ import annotations

from collections.abc import Callable

from modules.core.command_intents.command_intent_resolver import (
    CommandIntentResolver,
)
from modules.core.command_intents.intent_result import (
    CommandIntentResolutionStatus,
)
from modules.core.voice_engine.fallback_pipeline import (
    FallbackDecision,
    FallbackPipeline,
    NullFallbackPipeline,
)
from modules.core.voice_engine.language_policy import VoiceLanguagePolicy
from modules.core.voice_engine.voice_engine_metrics import VoiceEngineMetrics
from modules.core.voice_engine.voice_turn import (
    VoiceTurnInput,
    VoiceTurnResult,
    VoiceTurnRoute,
)
from modules.core.voice_engine.voice_turn_state import VoiceTurnState
from modules.devices.audio.command_asr.command_recognizer import (
    CommandRecognizer,
)


MonotonicClock = Callable[[], float]


class CommandFirstPipeline:
    """Command-first Voice Engine v2 pipeline.

    This pipeline is intentionally transcript-based in Stage 5. Audio/VAD
    integration will attach later after the runtime migration gate is enabled.
    """

    def __init__(
        self,
        *,
        command_recognizer: CommandRecognizer,
        intent_resolver: CommandIntentResolver,
        fallback_pipeline: FallbackPipeline | None = None,
        language_policy: VoiceLanguagePolicy | None = None,
        clock: MonotonicClock | None = None,
    ) -> None:
        self._command_recognizer = command_recognizer
        self._intent_resolver = intent_resolver
        self._fallback_pipeline = fallback_pipeline or NullFallbackPipeline()
        self._language_policy = language_policy or VoiceLanguagePolicy()
        self._clock = clock or __import__("time").monotonic

    def process_turn(self, turn_input: VoiceTurnInput) -> VoiceTurnResult:
        metrics = VoiceEngineMetrics(
            turn_started_monotonic=turn_input.started_monotonic,
            speech_end_monotonic=turn_input.speech_end_monotonic,
        )

        transcript = turn_input.transcript.strip()

        metrics.mark_command_started(self._clock())
        recognition = self._command_recognizer.recognize_text(transcript)
        metrics.mark_command_finished(self._clock())

        language = self._language_policy.choose_language(
            transcript=transcript,
            recognition_language=recognition.language,
            hint=turn_input.language_hint,
        )

        metrics.mark_resolver_started(self._clock())
        resolution = self._intent_resolver.resolve(recognition)
        metrics.mark_resolver_finished(self._clock())

        if resolution.status is CommandIntentResolutionStatus.RESOLVED:
            metrics.mark_finished(self._clock())
            return VoiceTurnResult(
                turn_id=turn_input.turn_id,
                state=VoiceTurnState.COMPLETED,
                route=VoiceTurnRoute.COMMAND,
                language=resolution.language,
                source_text=transcript,
                intent=resolution.intent,
                recognition=recognition,
                resolution=resolution,
                metrics=metrics,
            )

        fallback_reason = resolution.reason or resolution.status.value
        fallback = self._fallback_pipeline.decide(
            transcript=transcript,
            language=language,
            reason=fallback_reason,
        )
        metrics.mark_fallback(fallback.reason)
        metrics.mark_finished(self._clock())

        return VoiceTurnResult(
            turn_id=turn_input.turn_id,
            state=VoiceTurnState.FALLBACK_REQUIRED,
            route=VoiceTurnRoute.FALLBACK,
            language=fallback.language,
            source_text=transcript,
            recognition=recognition,
            resolution=resolution,
            fallback=fallback,
            metrics=metrics,
        )

    def reset(self) -> None:
        self._command_recognizer.reset()