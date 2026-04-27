from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from modules.core.voice_engine import (
    VoiceEngine,
    VoiceEngineSettings,
    VoiceTurnInput,
    VoiceTurnResult,
    VoiceTurnRoute,
)
from modules.devices.audio.command_asr import CommandLanguage
from modules.runtime.voice_engine_v2.shadow_telemetry import (
    VoiceEngineV2ShadowTelemetryWriter,
)


@dataclass(frozen=True, slots=True)
class VoiceEngineV2ShadowRequest:
    """Shadow-mode request for comparing legacy routing with Voice Engine v2."""

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
        if not self.transcript.strip():
            raise ValueError("transcript must not be empty")
        if self.started_monotonic < 0:
            raise ValueError("started_monotonic must not be negative")
        if self.speech_end_monotonic is not None and self.speech_end_monotonic < 0:
            raise ValueError("speech_end_monotonic must not be negative")

        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )


@dataclass(frozen=True, slots=True)
class VoiceEngineV2ShadowResult:
    """Shadow-mode comparison result.

    Shadow mode never executes actions. It only observes and compares decisions.
    """

    enabled: bool
    reason: str
    request: VoiceEngineV2ShadowRequest
    legacy_runtime_primary: bool
    matched_legacy_intent: bool | None = None
    voice_engine_route: VoiceTurnRoute | None = None
    voice_engine_intent_key: str | None = None
    voice_engine_language: CommandLanguage = CommandLanguage.UNKNOWN
    fallback_reason: str = ""
    turn_result: VoiceTurnResult | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("reason must not be empty")

        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )

    @property
    def action_executed(self) -> bool:
        return False

    @property
    def is_command(self) -> bool:
        return self.voice_engine_route is VoiceTurnRoute.COMMAND


class VoiceEngineV2ShadowModeAdapter:
    """Hardware-safe Voice Engine v2 shadow-mode adapter.

    Shadow mode compares decisions but never executes actions. This makes it
    safe for Raspberry Pi hardware validation before replacing the legacy path.
    """

    def __init__(
        self,
        *,
        engine: VoiceEngine,
        settings: VoiceEngineSettings,
        telemetry_writer: VoiceEngineV2ShadowTelemetryWriter | None = None,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._telemetry_writer = telemetry_writer

    @property
    def settings(self) -> VoiceEngineSettings:
        return self._settings

    @property
    def telemetry_writer(self) -> VoiceEngineV2ShadowTelemetryWriter | None:
        return self._telemetry_writer

    def observe_transcript(
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
    ) -> VoiceEngineV2ShadowResult:
        request = VoiceEngineV2ShadowRequest(
            turn_id=turn_id,
            transcript=transcript,
            legacy_route=legacy_route,
            legacy_intent_key=legacy_intent_key,
            language_hint=language_hint,
            started_monotonic=started_monotonic,
            speech_end_monotonic=speech_end_monotonic,
            metadata=metadata or {},
        )
        return self.observe_request(request)

    def observe_request(
        self,
        request: VoiceEngineV2ShadowRequest,
    ) -> VoiceEngineV2ShadowResult:
        if not self._settings.shadow_mode_enabled:
            return self._finalize(
                VoiceEngineV2ShadowResult(
                    enabled=False,
                    reason="shadow_mode_disabled",
                    request=request,
                    legacy_runtime_primary=True,
                    metadata={
                        "shadow_mode_enabled": False,
                        "command_pipeline_can_run": (
                            self._settings.command_pipeline_can_run
                        ),
                    },
                )
            )

        if not self._settings.command_pipeline_can_run:
            return self._finalize(
                VoiceEngineV2ShadowResult(
                    enabled=False,
                    reason="voice_engine_v2_not_runnable",
                    request=request,
                    legacy_runtime_primary=True,
                    metadata={
                        "shadow_mode_enabled": True,
                        "command_pipeline_can_run": False,
                        "mode": self._settings.mode,
                    },
                )
            )

        turn_result = self._engine.process_turn(
            VoiceTurnInput(
                turn_id=request.turn_id,
                transcript=request.transcript,
                started_monotonic=request.started_monotonic,
                speech_end_monotonic=request.speech_end_monotonic,
                language_hint=request.language_hint,
                source="voice_engine_v2_shadow_mode",
            )
        )

        voice_engine_intent_key = (
            None if turn_result.intent is None else turn_result.intent.key
        )
        fallback_reason = (
            "" if turn_result.fallback is None else turn_result.fallback.reason
        )
        matched_legacy_intent = self._compare_legacy_intent(
            legacy_intent_key=request.legacy_intent_key,
            voice_engine_intent_key=voice_engine_intent_key,
        )

        reason = self._reason_for(
            turn_result=turn_result,
            matched_legacy_intent=matched_legacy_intent,
        )

        return self._finalize(
            VoiceEngineV2ShadowResult(
                enabled=True,
                reason=reason,
                request=request,
                legacy_runtime_primary=True,
                matched_legacy_intent=matched_legacy_intent,
                voice_engine_route=turn_result.route,
                voice_engine_intent_key=voice_engine_intent_key,
                voice_engine_language=turn_result.language,
                fallback_reason=fallback_reason,
                turn_result=turn_result,
                metadata={
                    **dict(request.metadata),
                    "legacy_route": request.legacy_route,
                    "legacy_intent_key": request.legacy_intent_key,
                    "voice_engine_route": turn_result.route.value,
                    "voice_engine_intent_key": voice_engine_intent_key,
                    "voice_engine_language": turn_result.language.value,
                    "fallback_used": turn_result.metrics.fallback_used,
                    "fallback_reason": turn_result.metrics.fallback_reason,
                    "action_executed": False,
                },
            )
        )

    def _finalize(
        self,
        result: VoiceEngineV2ShadowResult,
    ) -> VoiceEngineV2ShadowResult:
        if result.enabled and self._telemetry_writer is not None:
            self._telemetry_writer.write_result(result)
        return result

    @staticmethod
    def _compare_legacy_intent(
        *,
        legacy_intent_key: str | None,
        voice_engine_intent_key: str | None,
    ) -> bool | None:
        if not legacy_intent_key:
            return None
        return legacy_intent_key == voice_engine_intent_key

    @staticmethod
    def _reason_for(
        *,
        turn_result: VoiceTurnResult,
        matched_legacy_intent: bool | None,
    ) -> str:
        if turn_result.route is VoiceTurnRoute.FALLBACK:
            if turn_result.fallback is not None and turn_result.fallback.reason:
                return f"fallback:{turn_result.fallback.reason}"
            return "fallback"

        if matched_legacy_intent is True:
            return "matched_legacy_intent"

        if matched_legacy_intent is False:
            return "mismatched_legacy_intent"

        return "observed"