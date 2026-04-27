from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from modules.core.voice_engine import (
    IntentExecutionAdapter,
    IntentExecutionHandler,
    IntentExecutionResult,
    IntentExecutionStatus,
    VisualActionFirstExecutor,
    VoiceEngine,
    VoiceEngineSettings,
    VoiceTurnInput,
    VoiceTurnResult,
    VoiceTurnRoute,
)
from modules.devices.audio.command_asr import CommandLanguage


@dataclass(frozen=True, slots=True)
class VoiceEngineV2AcceptanceRequest:
    """Controlled runtime acceptance request for Voice Engine v2."""

    turn_id: str
    transcript: str
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
class VoiceEngineV2AcceptanceResult:
    """Acceptance result for controlled Voice Engine v2 runtime checks."""

    accepted: bool
    reason: str
    legacy_runtime_primary: bool
    request: VoiceEngineV2AcceptanceRequest
    turn_result: VoiceTurnResult | None = None
    execution_result: IntentExecutionResult | None = None
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
    def command_executed(self) -> bool:
        return (
            self.turn_result is not None
            and self.turn_result.route is VoiceTurnRoute.COMMAND
            and self.execution_result is not None
            and self.execution_result.status is IntentExecutionStatus.EXECUTED
        )


class VoiceEngineV2AcceptanceAdapter:
    """Controlled runtime acceptance adapter for Voice Engine v2.

    This adapter is intentionally explicit and gated. It allows tests and later
    hardware validation to exercise the command-first path without replacing the
    legacy wake/capture/STT runtime path.
    """

    def __init__(
        self,
        *,
        engine: VoiceEngine,
        settings: VoiceEngineSettings,
        execution_adapter: IntentExecutionAdapter | None = None,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._execution_adapter = execution_adapter or IntentExecutionAdapter()
        self._executor = VisualActionFirstExecutor(self._execution_adapter)

    @property
    def settings(self) -> VoiceEngineSettings:
        return self._settings

    @property
    def registered_actions(self) -> tuple[str, ...]:
        return self._execution_adapter.registered_actions

    def register_action(
        self,
        action: str,
        handler: IntentExecutionHandler,
    ) -> None:
        self._execution_adapter.register_action(action, handler)

    def process_transcript(
        self,
        *,
        turn_id: str,
        transcript: str,
        language_hint: CommandLanguage = CommandLanguage.UNKNOWN,
        started_monotonic: float = 0.0,
        speech_end_monotonic: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> VoiceEngineV2AcceptanceResult:
        request = VoiceEngineV2AcceptanceRequest(
            turn_id=turn_id,
            transcript=transcript,
            language_hint=language_hint,
            started_monotonic=started_monotonic,
            speech_end_monotonic=speech_end_monotonic,
            metadata=metadata or {},
        )
        return self.process_request(request)

    def process_request(
        self,
        request: VoiceEngineV2AcceptanceRequest,
    ) -> VoiceEngineV2AcceptanceResult:
        if not self._settings.command_pipeline_can_run:
            return VoiceEngineV2AcceptanceResult(
                accepted=False,
                reason="voice_engine_v2_disabled",
                legacy_runtime_primary=True,
                request=request,
                metadata={
                    "mode": self._settings.mode,
                    "enabled": self._settings.enabled,
                    "command_pipeline_can_run": False,
                },
            )

        turn_result = self._engine.process_turn(
            VoiceTurnInput(
                turn_id=request.turn_id,
                transcript=request.transcript,
                started_monotonic=request.started_monotonic,
                speech_end_monotonic=request.speech_end_monotonic,
                language_hint=request.language_hint,
                source="voice_engine_v2_acceptance",
            )
        )

        if turn_result.route is not VoiceTurnRoute.COMMAND:
            reason = "fallback_required"
            if turn_result.fallback is not None and turn_result.fallback.reason:
                reason = f"{reason}:{turn_result.fallback.reason}"

            return VoiceEngineV2AcceptanceResult(
                accepted=False,
                reason=reason,
                legacy_runtime_primary=False,
                request=request,
                turn_result=turn_result,
                metadata={
                    "route": turn_result.route.value,
                    "fallback_used": turn_result.metrics.fallback_used,
                    "fallback_reason": turn_result.metrics.fallback_reason,
                },
            )

        execution_result = self._executor.execute_turn(turn_result)
        accepted = execution_result.status is IntentExecutionStatus.EXECUTED

        return VoiceEngineV2AcceptanceResult(
            accepted=accepted,
            reason="accepted" if accepted else execution_result.detail,
            legacy_runtime_primary=False,
            request=request,
            turn_result=turn_result,
            execution_result=execution_result,
            metadata={
                "route": turn_result.route.value,
                "intent_key": (
                    None if turn_result.intent is None else turn_result.intent.key
                ),
                "action": execution_result.action,
                "execution_status": execution_result.status.value,
                "executed_before_tts": execution_result.executed_before_tts,
                "spoken_acknowledgement_allowed": (
                    execution_result.spoken_acknowledgement_allowed
                ),
            },
        )