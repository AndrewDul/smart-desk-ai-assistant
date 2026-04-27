from __future__ import annotations

from dataclasses import dataclass

from modules.core.voice_engine import VoiceEngine, VoiceEngineSettings
from modules.runtime.contracts import RuntimeBackendStatus
from modules.runtime.voice_engine_v2.acceptance import (
    VoiceEngineV2AcceptanceAdapter,
)
from modules.runtime.voice_engine_v2.runtime_candidates import (
    VoiceEngineV2RuntimeCandidateAdapter,
)
from modules.runtime.voice_engine_v2.shadow_mode import (
    VoiceEngineV2ShadowModeAdapter,
)
from modules.runtime.voice_engine_v2.shadow_runtime_hook import (
    VoiceEngineV2ShadowRuntimeHook,
)


@dataclass(frozen=True, slots=True)
class VoiceEngineV2RuntimeBundle:
    """Runtime bundle for the isolated Voice Engine v2 adapter."""

    engine: VoiceEngine
    settings: VoiceEngineSettings
    status: RuntimeBackendStatus
    acceptance_adapter: VoiceEngineV2AcceptanceAdapter
    runtime_candidate_adapter: VoiceEngineV2RuntimeCandidateAdapter
    shadow_mode_adapter: VoiceEngineV2ShadowModeAdapter
    shadow_runtime_hook: VoiceEngineV2ShadowRuntimeHook

    @property
    def enabled(self) -> bool:
        return self.settings.enabled

    @property
    def command_pipeline_can_run(self) -> bool:
        return self.settings.command_pipeline_can_run

    def to_metadata(self) -> dict[str, object]:
        return {
            "enabled": self.settings.enabled,
            "version": self.settings.version,
            "mode": self.settings.mode,
            "command_pipeline_can_run": self.settings.command_pipeline_can_run,
            "runtime_candidates_enabled": self.settings.runtime_candidates_enabled,
            "runtime_candidates_can_run": self.settings.runtime_candidates_can_run,
            "runtime_candidate_intent_allowlist": list(
                self.settings.runtime_candidate_intent_allowlist
            ),
            "runtime_candidate_supported_intents": list(
                self.runtime_candidate_adapter.supported_intents
            ),
            "runtime_candidate_log_path": self.settings.runtime_candidate_log_path,
            "runtime_candidate_telemetry_path": (
                self.runtime_candidate_adapter.telemetry_path
            ),
            "shadow_mode_enabled": self.settings.shadow_mode_enabled,
            "shadow_mode_can_run": self.settings.shadow_mode_can_run,
            "shadow_log_path": self.settings.shadow_log_path,
            "realtime_audio_bus_enabled": self.settings.realtime_audio_bus_enabled,
            "vad_endpointing_enabled": self.settings.vad_endpointing_enabled,
            "command_first_enabled": self.settings.command_first_enabled,
            "fallback_to_legacy_enabled": self.settings.fallback_to_legacy_enabled,
            "metrics_enabled": self.settings.metrics_enabled,
            "legacy_removal_stage": self.settings.legacy_removal_stage,
            "acceptance_adapter_available": True,
            "runtime_candidate_adapter_available": True,
            "shadow_mode_adapter_available": True,
            "shadow_runtime_hook_available": True,
            "shadow_runtime_hook_action_safe": self.shadow_runtime_hook.action_safe,
            "registered_acceptance_actions": list(
                self.acceptance_adapter.registered_actions
            ),
            "status": self.status.to_snapshot(),
        }