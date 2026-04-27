from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from modules.core.voice_engine import VoiceTurnResult, VoiceTurnRoute
from modules.runtime.contracts import (
    IntentMatch,
    RouteDecision,
    RouteKind,
    ToolInvocation,
)


@dataclass(frozen=True, slots=True)
class RuntimeCandidateActionSpec:
    """Bridge spec from a Voice Engine v2 intent to an existing legacy action."""

    voice_engine_intent_key: str
    legacy_action: str
    tool_name: str

    def __post_init__(self) -> None:
        if not self.voice_engine_intent_key.strip():
            raise ValueError("voice_engine_intent_key must not be empty")
        if not self.legacy_action.strip():
            raise ValueError("legacy_action must not be empty")
        if not self.tool_name.strip():
            raise ValueError("tool_name must not be empty")


@dataclass(frozen=True, slots=True)
class RuntimeCandidateExecutionPlan:
    """Execution plan for the live candidate orchestrator.

    The plan deliberately contains a legacy RouteDecision instead of direct
    display/TTS/action work. The existing ActionFlow remains responsible for
    actual execution, spoken response and display response.
    """

    route_decision: RouteDecision
    spec: RuntimeCandidateActionSpec
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


class RuntimeCandidateExecutionPlanBuilder:
    """Build safe legacy ActionFlow routes for selected runtime candidates.

    Stage 19 intentionally supports only identity and current-time candidates.
    It does not execute the action directly and it does not contain TTS/display
    logic. This keeps interaction_mixin as an orchestrator and preserves the
    existing ActionFlow execution contract.
    """

    _SPECS: Mapping[str, RuntimeCandidateActionSpec] = MappingProxyType(
        {
            "assistant.identity": RuntimeCandidateActionSpec(
                voice_engine_intent_key="assistant.identity",
                legacy_action="introduce_self",
                tool_name="assistant.introduce",
            ),
            "system.current_time": RuntimeCandidateActionSpec(
                voice_engine_intent_key="system.current_time",
                legacy_action="ask_time",
                tool_name="clock.time",
            ),
        }
    )

    @property
    def supported_intents(self) -> tuple[str, ...]:
        return tuple(sorted(self._SPECS))

    def build_plan(
        self,
        *,
        turn_result: VoiceTurnResult,
        transcript: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeCandidateExecutionPlan | None:
        if turn_result.route is not VoiceTurnRoute.COMMAND:
            return None
        if turn_result.intent is None:
            return None

        spec = self._SPECS.get(turn_result.intent.key)
        if spec is None:
            return None

        request_metadata = dict(metadata or {})
        confidence = max(float(turn_result.intent.confidence or 0.0), 0.90)
        normalized_text = str(
            turn_result.intent.normalized_source_text or transcript
        ).strip()
        matched_phrase = ""
        if turn_result.recognition is not None:
            matched_phrase = str(turn_result.recognition.matched_phrase or "")

        route = RouteDecision(
            turn_id=turn_result.turn_id,
            raw_text=str(transcript or "").strip(),
            normalized_text=normalized_text,
            language=turn_result.language.value,
            kind=RouteKind.ACTION,
            confidence=confidence,
            primary_intent=spec.legacy_action,
            intents=[
                IntentMatch(
                    name=spec.legacy_action,
                    confidence=confidence,
                    entities=[],
                    requires_clarification=False,
                    metadata={
                        "lane": "voice_engine_v2_runtime_candidate",
                        "voice_engine_intent_key": turn_result.intent.key,
                        "matched_phrase": matched_phrase,
                    },
                )
            ],
            conversation_topics=[],
            tool_invocations=[
                ToolInvocation(
                    tool_name=spec.tool_name,
                    payload={},
                    reason="voice_engine_v2_runtime_candidate",
                    confidence=confidence,
                    execute_immediately=True,
                )
            ],
            notes=["voice_engine_v2_runtime_candidate"],
            metadata={
                **request_metadata,
                "lane": "voice_engine_v2_runtime_candidate",
                "voice_engine_intent_key": turn_result.intent.key,
                "voice_engine_action": turn_result.intent.action,
                "legacy_action": spec.legacy_action,
                "tool_name": spec.tool_name,
                "matched_phrase": matched_phrase,
                "llm_prevented": True,
                "fallback_to_legacy_enabled": True,
            },
        )

        return RuntimeCandidateExecutionPlan(
            route_decision=route,
            spec=spec,
            metadata={
                **request_metadata,
                "intent_key": turn_result.intent.key,
                "legacy_action": spec.legacy_action,
                "tool_name": spec.tool_name,
                "language": turn_result.language.value,
            },
        )