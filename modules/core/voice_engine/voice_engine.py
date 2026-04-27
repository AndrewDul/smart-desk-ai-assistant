from __future__ import annotations

from modules.core.voice_engine.command_first_pipeline import CommandFirstPipeline
from modules.core.voice_engine.fallback_pipeline import (
    FallbackDecision,
    NullFallbackPipeline,
)
from modules.core.voice_engine.voice_engine_metrics import VoiceEngineMetrics
from modules.core.voice_engine.voice_engine_settings import VoiceEngineSettings
from modules.core.voice_engine.voice_turn import (
    VoiceTurnInput,
    VoiceTurnResult,
    VoiceTurnRoute,
)
from modules.core.voice_engine.voice_turn_state import VoiceTurnState


class VoiceEngine:
    """Top-level Voice Engine v2 facade.

    Stage 5 keeps this facade isolated from production runtime. If the config
    gate is not enabled, it returns a fallback decision instead of replacing
    the legacy voice path.
    """

    def __init__(
        self,
        *,
        settings: VoiceEngineSettings,
        command_first_pipeline: CommandFirstPipeline,
        legacy_fallback: NullFallbackPipeline | None = None,
    ) -> None:
        self._settings = settings
        self._command_first_pipeline = command_first_pipeline
        self._legacy_fallback = legacy_fallback or NullFallbackPipeline()

    @property
    def settings(self) -> VoiceEngineSettings:
        return self._settings

    def process_turn(self, turn_input: VoiceTurnInput) -> VoiceTurnResult:
        if not self._settings.command_pipeline_can_run:
            metrics = VoiceEngineMetrics(
                turn_started_monotonic=turn_input.started_monotonic,
                speech_end_monotonic=turn_input.speech_end_monotonic,
            )
            fallback = self._legacy_fallback.decide(
                transcript=turn_input.transcript,
                language=turn_input.language_hint,
                reason="voice_engine_v2_disabled",
            )
            metrics.mark_fallback(fallback.reason)
            metrics.mark_finished(turn_input.started_monotonic)

            return VoiceTurnResult(
                turn_id=turn_input.turn_id,
                state=VoiceTurnState.FALLBACK_REQUIRED,
                route=VoiceTurnRoute.FALLBACK,
                language=fallback.language,
                source_text=turn_input.transcript,
                fallback=fallback,
                metrics=metrics,
            )

        return self._command_first_pipeline.process_turn(turn_input)

    def reset(self) -> None:
        self._command_first_pipeline.reset()