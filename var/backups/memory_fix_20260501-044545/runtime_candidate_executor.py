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

    This builder supports only explicitly allowlisted safe candidates.
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
            "visual_shell.show_desktop": RuntimeCandidateActionSpec(
                voice_engine_intent_key="visual_shell.show_desktop",
                legacy_action="show_desktop",
                tool_name="visual_shell.show_desktop",
            ),
            "visual_shell.show_shell": RuntimeCandidateActionSpec(
                voice_engine_intent_key="visual_shell.show_shell",
                legacy_action="show_shell",
                tool_name="visual_shell.show_shell",
            ),
            "visual_shell.show_self": RuntimeCandidateActionSpec(
                voice_engine_intent_key="visual_shell.show_self",
                legacy_action="show_self",
                tool_name="visual_shell.show_self",
            ),
            "visual_shell.show_eyes": RuntimeCandidateActionSpec(
                voice_engine_intent_key="visual_shell.show_eyes",
                legacy_action="show_eyes",
                tool_name="visual_shell.show_eyes",
            ),
            "visual_shell.show_face": RuntimeCandidateActionSpec(
                voice_engine_intent_key="visual_shell.show_face",
                legacy_action="show_face_contour",
                tool_name="visual_shell.show_face",
            ),
            "visual_shell.look_at_user": RuntimeCandidateActionSpec(
                voice_engine_intent_key="visual_shell.look_at_user",
                legacy_action="look_at_user",
                tool_name="visual_shell.look_at_user",
            ),
            "visual_shell.start_scanning": RuntimeCandidateActionSpec(
                voice_engine_intent_key="visual_shell.start_scanning",
                legacy_action="start_scanning",
                tool_name="visual_shell.start_scanning",
            ),
            "visual_shell.return_to_idle": RuntimeCandidateActionSpec(
                voice_engine_intent_key="visual_shell.return_to_idle",
                legacy_action="return_to_idle",
                tool_name="visual_shell.return_to_idle",
            ),
            "visual_shell.show_temperature": RuntimeCandidateActionSpec(
                voice_engine_intent_key="visual_shell.show_temperature",
                legacy_action="show_temperature",
                tool_name="visual_shell.show_temperature",
            ),
            "visual_shell.show_battery": RuntimeCandidateActionSpec(
                voice_engine_intent_key="visual_shell.show_battery",
                legacy_action="show_battery",
                tool_name="visual_shell.show_battery",
            ),
            "visual_shell.show_date": RuntimeCandidateActionSpec(
                voice_engine_intent_key="visual_shell.show_date",
                legacy_action="show_visual_date",
                tool_name="visual_shell.show_date",
            ),
            "visual_shell.show_time": RuntimeCandidateActionSpec(
                voice_engine_intent_key="visual_shell.show_time",
                legacy_action="show_visual_time",
                tool_name="visual_shell.show_time",
            ),
            "reminder.guided_start": RuntimeCandidateActionSpec(
                voice_engine_intent_key="reminder.guided_start",
                legacy_action="reminder_create",
                tool_name="reminder.guided_start",
            ),
            "reminder.time_answer": RuntimeCandidateActionSpec(
                voice_engine_intent_key="reminder.time_answer",
                legacy_action="reminder_time_answer",
                tool_name="reminder.time_answer",
            ),
            "assistant.help": RuntimeCandidateActionSpec(
                voice_engine_intent_key="assistant.help",
                legacy_action="help",
                tool_name="system.help",
            ),
              "memory.guided_start": RuntimeCandidateActionSpec(
                  voice_engine_intent_key="memory.guided_start",
                  legacy_action="memory_store",
                  tool_name="memory.guided_start",
              ),
              "memory.list": RuntimeCandidateActionSpec(
                  voice_engine_intent_key="memory.list",
                  legacy_action="memory_list",
                  tool_name="memory.list",
              ),
        }
    )

    @property
    def supported_intents(self) -> tuple[str, ...]:
        return tuple(sorted(self._SPECS))

    def build_plan_from_intent(
        self,
        *,
        turn_id: str,
        intent_key: str,
        transcript: str,
        language: str,
        metadata: Mapping[str, Any] | None = None,
        confidence: float = 1.0,
        matched_phrase: str = "",
    ) -> RuntimeCandidateExecutionPlan | None:
        """Build a guarded runtime candidate plan from a trusted Vosk intent."""

        spec = self._SPECS.get(intent_key)
        if spec is None:
            return None

        request_metadata = dict(metadata or {})
        normalized_text = str(transcript or "").strip()
        safe_language = language if language in {"pl", "en"} else "unknown"
        safe_confidence = max(float(confidence or 0.0), 0.90)

        route = RouteDecision(
            turn_id=str(turn_id or ""),
            raw_text=str(transcript or "").strip(),
            normalized_text=normalized_text,
            language=safe_language,
            kind=RouteKind.ACTION,
            confidence=safe_confidence,
            primary_intent=spec.legacy_action,
            intents=[
                IntentMatch(
                    name=spec.legacy_action,
                    confidence=safe_confidence,
                    entities=[],
                    requires_clarification=False,
                    metadata={
                        "lane": "voice_engine_v2_runtime_candidate",
                        "voice_engine_intent_key": intent_key,
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
                    confidence=safe_confidence,
                    execute_immediately=True,
                )
            ],
            notes=["voice_engine_v2_runtime_candidate"],
            metadata={
                **request_metadata,
                "lane": "voice_engine_v2_runtime_candidate",
                "voice_engine_intent_key": intent_key,
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
                "intent_key": intent_key,
                "legacy_action": spec.legacy_action,
                "tool_name": spec.tool_name,
                "language": safe_language,
            },
        )

    _TRANSCRIPT_INTENT_OVERRIDES = {
        "show yourself": "visual_shell.show_self",
        "show your self": "visual_shell.show_self",
        "show the time": "visual_shell.show_time",
        "show time": "visual_shell.show_time",
            "pokaż oczy": "visual_shell.show_eyes",
        "pokaz oczy": "visual_shell.show_eyes",
        "show eyes": "visual_shell.show_eyes",
        "spójrz na mnie": "visual_shell.look_at_user",
        "spojrz na mnie": "visual_shell.look_at_user",
        "patrz na mnie": "visual_shell.look_at_user",
        "look at me": "visual_shell.look_at_user",
        "scan room": "visual_shell.start_scanning",
        "scan the room": "visual_shell.start_scanning",
        "look around": "visual_shell.start_scanning",
        "sprawdź pokój": "visual_shell.start_scanning",
        "sprawdz pokoj": "visual_shell.start_scanning",
        "rozejrzyj się": "visual_shell.start_scanning",
        "rozejrzyj sie": "visual_shell.start_scanning",
          "remember something": "memory.guided_start",
          "remember this": "memory.guided_start",
          "remember that": "memory.guided_start",
          "remember it": "memory.guided_start",
          "save this": "memory.guided_start",
          "zapamiętaj coś": "memory.guided_start",
          "zapamietaj cos": "memory.guided_start",
          "zapamiętaj to": "memory.guided_start",
          "zapamietaj to": "memory.guided_start",
          "pamiętaj coś": "memory.guided_start",
          "pamietaj cos": "memory.guided_start",
          "memory list": "memory.list",
          "show memory": "memory.list",
          "list memory": "memory.list",
          "what do you remember": "memory.list",
          "show what you remember": "memory.list",
          "pokaż pamięć": "memory.list",
          "pokaz pamiec": "memory.list",
          "co pamiętasz": "memory.list",
          "co pamietasz": "memory.list",
          "co zapamiętałaś": "memory.list",
          "co zapamietalas": "memory.list",
}

    @classmethod
    def _resolve_runtime_intent_key(
        cls,
        *,
        intent_key: str,
        transcript: str,
    ) -> str:
        """Resolve short runtime candidate phrases that can collide in grammar."""

        normalized = " ".join(
            str(transcript or "")
            .strip()
            .lower()
            .replace(".", " ")
            .replace(",", " ")
            .replace("?", " ")
            .replace("!", " ")
            .split()
        )
        override = cls._TRANSCRIPT_INTENT_OVERRIDES.get(normalized)
        if override:
            return str(override)
        return str(intent_key or "").strip()

    def build_plan(
        self,
        *,
        turn_result,
        transcript: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeCandidateExecutionPlan | None:
        """Build a guarded runtime candidate plan from a Vosk command result."""

        request_metadata = dict(metadata or {})
        raw_intent = getattr(turn_result, "intent", None)
        raw_intent_key = str(getattr(raw_intent, "key", "") or "").strip()

        resolved_intent_key = self._resolve_runtime_intent_key(
            intent_key=raw_intent_key,
            transcript=transcript,
        )
        transcript_override_used = bool(
            resolved_intent_key and resolved_intent_key != raw_intent_key
        )

        if getattr(turn_result, "intent", None) is None and not transcript_override_used:
            return None

        spec = self._SPECS.get(resolved_intent_key)
        if spec is None:
            return None

        raw_language = getattr(turn_result, "language", "")
        language = str(getattr(raw_language, "value", raw_language) or "").strip()
        if language not in {"pl", "en"}:
            language = "unknown"

        try:
            confidence = float(getattr(turn_result, "confidence", 1.0) or 1.0)
        except (TypeError, ValueError):
            confidence = 1.0
        confidence = max(confidence, 0.90)

        matched_phrase = str(getattr(turn_result, "matched_phrase", "") or "").strip()
        normalized_text = str(transcript or "").strip()
        voice_engine_action = str(getattr(raw_intent, "action", "") or "").strip()

        route = RouteDecision(
            turn_id=str(getattr(turn_result, "turn_id", "") or ""),
            raw_text=str(transcript or "").strip(),
            normalized_text=normalized_text,
            language=language,
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
                        "voice_engine_intent_key": resolved_intent_key,
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
                "voice_engine_intent_key": resolved_intent_key,
                "voice_engine_action": voice_engine_action,
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
                "intent_key": resolved_intent_key,
                "legacy_action": spec.legacy_action,
                "tool_name": spec.tool_name,
                "language": language,
            },
        )
