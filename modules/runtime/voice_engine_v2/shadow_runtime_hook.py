from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from modules.devices.audio.command_asr import CommandLanguage
from modules.runtime.voice_engine_v2.shadow_mode import (
    VoiceEngineV2ShadowModeAdapter,
    VoiceEngineV2ShadowResult,
)


@dataclass(frozen=True, slots=True)
class VoiceEngineV2ShadowRuntimeObservation:
    """Legacy-runtime transcript observation for Voice Engine v2 shadow mode."""

    turn_id: str
    transcript: str
    legacy_route: str = ""
    legacy_intent_key: str | None = None
    language_hint: CommandLanguage = CommandLanguage.UNKNOWN
    started_monotonic: float = 0.0
    speech_end_monotonic: float | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.turn_id.strip():
            raise ValueError("turn_id must not be empty")
        if self.started_monotonic < 0:
            raise ValueError("started_monotonic must not be negative")
        if self.speech_end_monotonic is not None and self.speech_end_monotonic < 0:
            raise ValueError("speech_end_monotonic must not be negative")

        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )


class VoiceEngineV2ShadowRuntimeHook:
    """Hardware-safe hook for feeding legacy transcripts into shadow mode.

    This hook is intentionally passive. It observes legacy transcripts and lets
    Voice Engine v2 compare decisions, but it never executes actions and never
    changes the production runtime route.
    """

    def __init__(self, shadow_mode_adapter: VoiceEngineV2ShadowModeAdapter) -> None:
        self._shadow_mode_adapter = shadow_mode_adapter

    @property
    def shadow_mode_adapter(self) -> VoiceEngineV2ShadowModeAdapter:
        return self._shadow_mode_adapter

    @property
    def action_safe(self) -> bool:
        return True

    def observe_legacy_turn(
        self,
        *,
        turn_id: str,
        transcript: str,
        legacy_route: str = "",
        legacy_intent_key: str | None = None,
        language_hint: CommandLanguage = CommandLanguage.UNKNOWN,
        started_monotonic: float = 0.0,
        speech_end_monotonic: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> VoiceEngineV2ShadowResult | None:
        observation = VoiceEngineV2ShadowRuntimeObservation(
            turn_id=turn_id,
            transcript=transcript,
            legacy_route=legacy_route,
            legacy_intent_key=legacy_intent_key,
            language_hint=language_hint,
            started_monotonic=started_monotonic,
            speech_end_monotonic=speech_end_monotonic,
            metadata=metadata or {},
        )
        return self.observe(observation)

    def observe(
        self,
        observation: VoiceEngineV2ShadowRuntimeObservation,
    ) -> VoiceEngineV2ShadowResult | None:
        transcript = observation.transcript.strip()
        if not transcript:
            return None

        return self._shadow_mode_adapter.observe_transcript(
            turn_id=observation.turn_id,
            transcript=transcript,
            legacy_route=observation.legacy_route,
            legacy_intent_key=observation.legacy_intent_key,
            language_hint=observation.language_hint,
            started_monotonic=observation.started_monotonic,
            speech_end_monotonic=observation.speech_end_monotonic,
            metadata={
                **dict(observation.metadata),
                "shadow_runtime_hook": True,
                "action_safe": True,
            },
        )