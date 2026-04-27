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
from modules.runtime.contracts import RouteDecision
from modules.runtime.voice_engine_v2.runtime_candidate_executor import (
    RuntimeCandidateExecutionPlan,
    RuntimeCandidateExecutionPlanBuilder,
)


@dataclass(frozen=True, slots=True)
class VoiceEngineV2RuntimeCandidateRequest:
    """Request for a guarded command-first runtime candidate decision."""

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
class VoiceEngineV2RuntimeCandidateResult:
    """Result for a guarded command-first runtime candidate decision.

    The adapter only prepares a deterministic execution plan. The assistant
    integration owns generic route dispatch, and ActionFlow owns actual action,
    TTS and display behaviour.
    """

    accepted: bool
    reason: str
    legacy_runtime_primary: bool
    request: VoiceEngineV2RuntimeCandidateRequest
    turn_result: VoiceTurnResult | None = None
    execution_plan: RuntimeCandidateExecutionPlan | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("reason must not be empty")
        if self.accepted and self.execution_plan is None:
            raise ValueError("accepted runtime candidate requires execution_plan")

        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )

    @property
    def intent_key(self) -> str:
        if self.turn_result is None or self.turn_result.intent is None:
            return ""
        return self.turn_result.intent.key

    @property
    def route_decision(self) -> RouteDecision | None:
        if self.execution_plan is None:
            return None
        return self.execution_plan.route_decision


class VoiceEngineV2RuntimeCandidateAdapter:
    """Guarded partial runtime adapter for selected command-first candidates.

    This adapter is deliberately narrower than the full Voice Engine v2 runtime
    path. It can only prepare allowlisted deterministic action routes while the
    legacy runtime remains the fallback for every non-match, non-allowlisted or
    unsafe case.
    """

    def __init__(
        self,
        *,
        engine: VoiceEngine,
        settings: VoiceEngineSettings,
        execution_plan_builder: RuntimeCandidateExecutionPlanBuilder | None = None,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._execution_plan_builder = (
            execution_plan_builder or RuntimeCandidateExecutionPlanBuilder()
        )

    @property
    def settings(self) -> VoiceEngineSettings:
        return self._settings

    @property
    def allowlisted_intents(self) -> tuple[str, ...]:
        return self._settings.runtime_candidate_intent_allowlist

    @property
    def supported_intents(self) -> tuple[str, ...]:
        return self._execution_plan_builder.supported_intents

    def process_transcript(
        self,
        *,
        turn_id: str,
        transcript: str,
        language_hint: CommandLanguage = CommandLanguage.UNKNOWN,
        started_monotonic: float = 0.0,
        speech_end_monotonic: float | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> VoiceEngineV2RuntimeCandidateResult:
        request = VoiceEngineV2RuntimeCandidateRequest(
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
        request: VoiceEngineV2RuntimeCandidateRequest,
    ) -> VoiceEngineV2RuntimeCandidateResult:
        if not self._settings.runtime_candidates_enabled:
            return self._rejected(
                request=request,
                reason="runtime_candidates_disabled",
                metadata={"runtime_candidates_enabled": False},
            )

        if not self._settings.runtime_candidates_can_run:
            return self._rejected(
                request=request,
                reason="runtime_candidates_not_safe",
                metadata={
                    "runtime_candidates_enabled": self._settings.runtime_candidates_enabled,
                    "runtime_candidates_can_run": False,
                    "enabled": self._settings.enabled,
                    "mode": self._settings.mode,
                    "command_first_enabled": self._settings.command_first_enabled,
                    "fallback_to_legacy_enabled": self._settings.fallback_to_legacy_enabled,
                },
            )

        turn_result = self._engine.process_shadow_turn(
            VoiceTurnInput(
                turn_id=request.turn_id,
                transcript=request.transcript,
                started_monotonic=request.started_monotonic,
                speech_end_monotonic=request.speech_end_monotonic,
                language_hint=request.language_hint,
                source="voice_engine_v2_runtime_candidate",
            )
        )

        if turn_result.route is not VoiceTurnRoute.COMMAND:
            fallback_reason = ""
            if turn_result.fallback is not None:
                fallback_reason = turn_result.fallback.reason
            return self._rejected(
                request=request,
                reason=f"fallback_required:{fallback_reason or 'unknown'}",
                turn_result=turn_result,
                metadata={
                    "route": turn_result.route.value,
                    "fallback_used": turn_result.metrics.fallback_used,
                    "fallback_reason": turn_result.metrics.fallback_reason,
                },
            )

        if turn_result.intent is None:
            return self._rejected(
                request=request,
                reason="missing_intent",
                turn_result=turn_result,
                metadata={"route": turn_result.route.value},
            )

        intent_key = turn_result.intent.key
        if intent_key not in self._settings.runtime_candidate_intent_allowlist:
            return self._rejected(
                request=request,
                reason=f"intent_not_allowlisted:{intent_key}",
                turn_result=turn_result,
                metadata={
                    "route": turn_result.route.value,
                    "intent_key": intent_key,
                    "allowlist": list(self._settings.runtime_candidate_intent_allowlist),
                },
            )

        execution_plan = self._execution_plan_builder.build_plan(
            turn_result=turn_result,
            transcript=request.transcript,
            metadata=request.metadata,
        )
        if execution_plan is None:
            return self._rejected(
                request=request,
                reason=f"unsupported_candidate_intent:{intent_key}",
                turn_result=turn_result,
                metadata={
                    "route": turn_result.route.value,
                    "intent_key": intent_key,
                    "supported_intents": list(self.supported_intents),
                },
            )

        return VoiceEngineV2RuntimeCandidateResult(
            accepted=True,
            reason="accepted",
            legacy_runtime_primary=True,
            request=request,
            turn_result=turn_result,
            execution_plan=execution_plan,
            metadata={
                **dict(request.metadata),
                "runtime_candidate": True,
                "runtime_candidates_can_run": True,
                "intent_key": intent_key,
                "legacy_action": execution_plan.spec.legacy_action,
                "tool_name": execution_plan.spec.tool_name,
                "route": execution_plan.route_decision.kind.value,
                "language": turn_result.language.value,
            },
        )

    @staticmethod
    def _rejected(
        *,
        request: VoiceEngineV2RuntimeCandidateRequest,
        reason: str,
        turn_result: VoiceTurnResult | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> VoiceEngineV2RuntimeCandidateResult:
        return VoiceEngineV2RuntimeCandidateResult(
            accepted=False,
            reason=reason,
            legacy_runtime_primary=True,
            request=request,
            turn_result=turn_result,
            metadata=metadata or {},
        )