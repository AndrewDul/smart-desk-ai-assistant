from __future__ import annotations

from dataclasses import dataclass

from modules.core.voice_engine import VoiceEngine, VoiceEngineSettings
from modules.runtime.contracts import RuntimeBackendStatus
from modules.runtime.voice_engine_v2.acceptance import (
    VoiceEngineV2AcceptanceAdapter,
)


@dataclass(frozen=True, slots=True)
class VoiceEngineV2RuntimeBundle:
    """Runtime bundle for the isolated Voice Engine v2 adapter."""

    engine: VoiceEngine
    settings: VoiceEngineSettings
    status: RuntimeBackendStatus
    acceptance_adapter: VoiceEngineV2AcceptanceAdapter

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
            "realtime_audio_bus_enabled": self.settings.realtime_audio_bus_enabled,
            "vad_endpointing_enabled": self.settings.vad_endpointing_enabled,
            "command_first_enabled": self.settings.command_first_enabled,
            "fallback_to_legacy_enabled": self.settings.fallback_to_legacy_enabled,
            "metrics_enabled": self.settings.metrics_enabled,
            "legacy_removal_stage": self.settings.legacy_removal_stage,
            "acceptance_adapter_available": True,
            "registered_acceptance_actions": list(
                self.acceptance_adapter.registered_actions
            ),
            "status": self.status.to_snapshot(),
        }