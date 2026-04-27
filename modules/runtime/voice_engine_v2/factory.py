from __future__ import annotations

from typing import Any

from modules.core.command_intents import CommandIntentResolver
from modules.core.voice_engine import (
    CommandFirstPipeline,
    IntentExecutionAdapter,
    VoiceEngine,
    VoiceEngineSettings,
)
from modules.devices.audio.command_asr import (
    GrammarCommandRecognizer,
    build_default_command_grammar,
)
from modules.runtime.contracts import RuntimeBackendStatus
from modules.runtime.voice_engine_v2.acceptance import VoiceEngineV2AcceptanceAdapter
from modules.runtime.voice_engine_v2.models import VoiceEngineV2RuntimeBundle
from modules.runtime.voice_engine_v2.runtime_candidates import (
    VoiceEngineV2RuntimeCandidateAdapter,
)
from modules.runtime.voice_engine_v2.shadow_mode import VoiceEngineV2ShadowModeAdapter
from modules.runtime.voice_engine_v2.shadow_runtime_hook import (
    VoiceEngineV2ShadowRuntimeHook,
)
from modules.runtime.voice_engine_v2.shadow_telemetry import (
    VoiceEngineV2ShadowTelemetryWriter,
)
from modules.runtime.voice_engine_v2.runtime_candidate_telemetry import (
    VoiceEngineV2RuntimeCandidateTelemetryWriter,
)
from modules.runtime.voice_engine_v2.pre_stt_shadow import (
    VoiceEngineV2PreSttShadowAdapter,
    VoiceEngineV2PreSttShadowTelemetryWriter,
)


def build_voice_engine_v2_runtime(
    settings: dict[str, Any],
) -> VoiceEngineV2RuntimeBundle:
    """Build isolated Voice Engine v2 runtime objects from project settings.

    This factory does not replace the production runtime path. It only creates
    a ready-to-test Voice Engine v2 bundle behind the existing config gate.
    """

    voice_engine_settings = VoiceEngineSettings.from_settings(settings)

    grammar = build_default_command_grammar()
    recognizer = GrammarCommandRecognizer(grammar)
    resolver = CommandIntentResolver()
    command_pipeline = CommandFirstPipeline(
        command_recognizer=recognizer,
        intent_resolver=resolver,
    )
    engine = VoiceEngine(
        settings=voice_engine_settings,
        command_first_pipeline=command_pipeline,
    )
    execution_adapter = IntentExecutionAdapter()
    acceptance_adapter = VoiceEngineV2AcceptanceAdapter(
        engine=engine,
        settings=voice_engine_settings,
        execution_adapter=execution_adapter,
    )
    runtime_candidate_telemetry_writer = VoiceEngineV2RuntimeCandidateTelemetryWriter(
        voice_engine_settings.runtime_candidate_log_path,
        enabled=voice_engine_settings.runtime_candidates_enabled,
    )
    runtime_candidate_adapter = VoiceEngineV2RuntimeCandidateAdapter(
        engine=engine,
        settings=voice_engine_settings,
        telemetry_writer=runtime_candidate_telemetry_writer,
    )
    pre_stt_shadow_telemetry_writer = VoiceEngineV2PreSttShadowTelemetryWriter(
        voice_engine_settings.pre_stt_shadow_log_path,
        enabled=voice_engine_settings.pre_stt_shadow_enabled,
    )
    pre_stt_shadow_adapter = VoiceEngineV2PreSttShadowAdapter(
        settings=voice_engine_settings,
        telemetry_writer=pre_stt_shadow_telemetry_writer,
    )    
    shadow_telemetry_writer = VoiceEngineV2ShadowTelemetryWriter(
        voice_engine_settings.shadow_log_path,
        enabled=voice_engine_settings.shadow_mode_enabled,
    )
    shadow_mode_adapter = VoiceEngineV2ShadowModeAdapter(
        engine=engine,
        settings=voice_engine_settings,
        telemetry_writer=shadow_telemetry_writer,
    )
    shadow_runtime_hook = VoiceEngineV2ShadowRuntimeHook(
        shadow_mode_adapter=shadow_mode_adapter,
    )

    status = _build_status(voice_engine_settings)

    return VoiceEngineV2RuntimeBundle(
        engine=engine,
        settings=voice_engine_settings,
        status=status,
        acceptance_adapter=acceptance_adapter,
        runtime_candidate_adapter=runtime_candidate_adapter,
        pre_stt_shadow_adapter=pre_stt_shadow_adapter,
        shadow_mode_adapter=shadow_mode_adapter,
        shadow_runtime_hook=shadow_runtime_hook,

    )


def _build_status(settings: VoiceEngineSettings) -> RuntimeBackendStatus:
    if settings.command_pipeline_can_run:
        return RuntimeBackendStatus(
            component="voice_engine_v2",
            ok=True,
            selected_backend="command_first_pipeline",
            requested_backend="voice_engine_v2",
            detail="Voice Engine v2 command-first pipeline is ready behind the runtime adapter.",
            fallback_used=False,
            runtime_mode="v2",
            capabilities=(
                "command_first",
                "language_policy",
                "intent_resolution",
                "fallback_decision",
                "metrics",
            ),
            metadata={
                "enabled": True,
                "legacy_runtime_primary": False,
                "command_pipeline_can_run": True,
                "realtime_audio_bus_enabled": settings.realtime_audio_bus_enabled,
                "vad_endpointing_enabled": settings.vad_endpointing_enabled,
                "command_first_enabled": settings.command_first_enabled,
                "shadow_mode_enabled": settings.shadow_mode_enabled,
                "shadow_mode_can_run": settings.shadow_mode_can_run,
                "runtime_candidates_enabled": settings.runtime_candidates_enabled,
                "runtime_candidates_can_run": settings.runtime_candidates_can_run,
                "runtime_candidate_intent_allowlist": list(
                    settings.runtime_candidate_intent_allowlist
                ),
                "pre_stt_shadow_enabled": settings.pre_stt_shadow_enabled,
                "pre_stt_shadow_can_run": settings.pre_stt_shadow_can_run,
                "pre_stt_shadow_log_path": settings.pre_stt_shadow_log_path,
            },
        )

    return RuntimeBackendStatus(
        component="voice_engine_v2",
        ok=True,
        selected_backend="disabled",
        requested_backend="voice_engine_v2",
        detail="Voice Engine v2 is disabled by config; legacy voice runtime remains primary.",
        fallback_used=False,
        runtime_mode=settings.mode,
        capabilities=(
            "settings_gate",
            "legacy_fallback",
        ),
        metadata={
            "enabled": settings.enabled,
            "legacy_runtime_primary": True,
            "command_pipeline_can_run": False,
            "shadow_mode_enabled": settings.shadow_mode_enabled,
            "shadow_mode_can_run": settings.shadow_mode_can_run,
            "realtime_audio_bus_enabled": settings.realtime_audio_bus_enabled,
            "vad_endpointing_enabled": settings.vad_endpointing_enabled,
            "command_first_enabled": settings.command_first_enabled,
        },
    )