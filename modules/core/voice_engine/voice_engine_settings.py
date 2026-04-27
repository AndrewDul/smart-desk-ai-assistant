from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VoiceEngineSettings:
    """Voice Engine v2 feature-gate settings."""

    enabled: bool = False
    version: str = "v2"
    mode: str = "legacy"
    realtime_audio_bus_enabled: bool = False
    vad_endpointing_enabled: bool = False
    command_first_enabled: bool = False
    fallback_to_legacy_enabled: bool = True
    metrics_enabled: bool = True
    shadow_mode_enabled: bool = False
    shadow_log_path: str = "var/data/voice_engine_v2_shadow.jsonl"
    legacy_removal_stage: str = "after_voice_engine_v2_runtime_acceptance"

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version must not be empty")
        if self.version != "v2":
            raise ValueError("only Voice Engine v2 settings are supported")
        if not self.mode.strip():
            raise ValueError("mode must not be empty")
        if not self.shadow_log_path.strip():
            raise ValueError("shadow_log_path must not be empty")
        if not self.legacy_removal_stage.strip():
            raise ValueError("legacy_removal_stage must not be empty")

    @property
    def command_pipeline_can_run(self) -> bool:
        """Return whether Voice Engine v2 may be used as the live command path."""

        return (
            self.enabled
            and self.mode == "v2"
            and self.command_first_enabled
        )

    @property
    def shadow_mode_can_run(self) -> bool:
        """Return whether shadow comparison may observe legacy transcripts.

        Shadow observation is intentionally independent from the production
        command-pipeline gate. During hardware validation, legacy runtime must
        remain primary while Voice Engine v2 only compares deterministic command
        intent decisions from already accepted legacy transcripts.
        """

        return self.shadow_mode_enabled and self.fallback_to_legacy_enabled

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> VoiceEngineSettings:
        raw = settings.get("voice_engine", settings)
        return cls(
            enabled=bool(raw.get("enabled", False)),
            version=str(raw.get("version", "v2")),
            mode=str(raw.get("mode", "legacy")),
            realtime_audio_bus_enabled=bool(
                raw.get("realtime_audio_bus_enabled", False)
            ),
            vad_endpointing_enabled=bool(raw.get("vad_endpointing_enabled", False)),
            command_first_enabled=bool(raw.get("command_first_enabled", False)),
            fallback_to_legacy_enabled=bool(
                raw.get("fallback_to_legacy_enabled", True)
            ),
            metrics_enabled=bool(raw.get("metrics_enabled", True)),
            shadow_mode_enabled=bool(raw.get("shadow_mode_enabled", False)),
            shadow_log_path=str(
                raw.get(
                    "shadow_log_path",
                    "var/data/voice_engine_v2_shadow.jsonl",
                )
            ),
            legacy_removal_stage=str(
                raw.get(
                    "legacy_removal_stage",
                    "after_voice_engine_v2_runtime_acceptance",
                )
            ),
        )