from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from modules.core.voice_engine import VoiceTurnResult, VoiceTurnRoute
from modules.runtime.contracts import (
    EntityValue,
    IntentMatch,
    RouteDecision,
    RouteKind,
    ToolInvocation,
)
from modules.core.calculator.simple_arithmetic import evaluate_arithmetic_expression


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
            "system.current_date": RuntimeCandidateActionSpec(
                voice_engine_intent_key="system.current_date",
                legacy_action="show_date",
                tool_name="clock.date",
            ),
            "system.calculate": RuntimeCandidateActionSpec(
                voice_engine_intent_key="system.calculate",
                legacy_action="calculate",
                tool_name="system.calculate",
            ),
            "system.exit": RuntimeCandidateActionSpec(
                voice_engine_intent_key="system.exit",
                legacy_action="exit",
                tool_name="system.exit",
            ),
            "system.status": RuntimeCandidateActionSpec(
                voice_engine_intent_key="system.status",
                legacy_action="status",
                tool_name="system.status",
            ),
            "system.temperature": RuntimeCandidateActionSpec(
                voice_engine_intent_key="system.temperature",
                legacy_action="show_temperature",
                tool_name="system.temperature",
            ),
            "system.battery": RuntimeCandidateActionSpec(
                voice_engine_intent_key="system.battery",
                legacy_action="show_battery",
                tool_name="system.battery",
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
            "focus.start": RuntimeCandidateActionSpec(
                voice_engine_intent_key="focus.start",
                legacy_action="focus_start",
                tool_name="focus.start",
            ),
            "focus.offer": RuntimeCandidateActionSpec(
                voice_engine_intent_key="focus.offer",
                legacy_action="focus_offer",
                tool_name="focus.offer",
            ),
            "focus.stop": RuntimeCandidateActionSpec(
                voice_engine_intent_key="focus.stop",
                legacy_action="timer_stop",
                tool_name="focus.stop",
            ),
            "break.start": RuntimeCandidateActionSpec(
                voice_engine_intent_key="break.start",
                legacy_action="break_start",
                tool_name="break.start",
            ),
            "break.stop": RuntimeCandidateActionSpec(
                voice_engine_intent_key="break.stop",
                legacy_action="timer_stop",
                tool_name="break.stop",
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
            "feedback.on": RuntimeCandidateActionSpec(
                voice_engine_intent_key="feedback.on",
                legacy_action="feedback_on",
                tool_name="feedback.on",
            ),
            "feedback.off": RuntimeCandidateActionSpec(
                voice_engine_intent_key="feedback.off",
                legacy_action="feedback_off",
                tool_name="feedback.off",
            ),
            "assistant.help": RuntimeCandidateActionSpec(
                voice_engine_intent_key="assistant.help",
                legacy_action="help",
                tool_name="system.help",
            ),
            "mobile_base.drive_mode": RuntimeCandidateActionSpec(
                voice_engine_intent_key="mobile_base.drive_mode",
                legacy_action="drive_mode_start",
                tool_name="mobile_base.drive_mode",
            ),
            "mobile_base.stop": RuntimeCandidateActionSpec(
                voice_engine_intent_key="mobile_base.stop",
                legacy_action="drive_mode_stop",
                tool_name="mobile_base.stop",
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
              "memory.recall": RuntimeCandidateActionSpec(
                  voice_engine_intent_key="memory.recall",
                  legacy_action="memory_recall",
                  tool_name="memory.recall",
              ),
              "memory.forget": RuntimeCandidateActionSpec(
                  voice_engine_intent_key="memory.forget",
                  legacy_action="memory_forget",
                  tool_name="memory.forget",
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

        # For guided memory, selected phrases carry a sub-flow, for example
        # "zapamiętaj mnie" starts person enrollment instead of generic text capture.
        action_payload: dict[str, Any] = {}
        if intent_key == "memory.guided_start":
            action_payload = self._memory_guided_action_payload(transcript)

        # For memory.recall the spoken transcript carries the subject
        # ("gdzie jest mój telefon" → "telefon"). Extract it now so that the
        # downstream ActionFlow / MemorySkillExecutor receives the key
        # without having to re-run the parser.
        if intent_key == "memory.recall":
            recall_key = self._extract_recall_key(transcript)
            recall_query = recall_key or str(transcript or "").strip()
            if recall_query:
                action_payload = {"key": recall_query, "query": recall_query}

        if intent_key == "memory.forget":
            action_payload = self._memory_forget_action_payload(transcript)

        if intent_key == "system.calculate":
            calculation = evaluate_arithmetic_expression(transcript)
            if not calculation.ok:
                return None
            action_payload = {
                "expression": calculation.expression,
                "result": calculation.result,
                "source_text": str(transcript or "").strip(),
            }

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
                    entities=[
                        EntityValue(name=str(k), value=v)
                        for k, v in action_payload.items()
                    ],
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
                    payload=dict(action_payload),
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
                "payload": dict(action_payload),
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
        "ile to jest": "system.calculate",
        "policz": "system.calculate",
        "oblicz": "system.calculate",
        "calculate": "system.calculate",
        "what is": "system.calculate",
        "wyłącz nexa": "system.exit",
        "wylacz nexa": "system.exit",
        "zamknij nexa": "system.exit",
        "exit": "system.exit",
        "close nexa": "system.exit",
        "turn off nexa": "system.exit",
        "look at me.": "visual_shell.look_at_user",
        "look at me now.": "visual_shell.look_at_user",
        "start looking at me.": "visual_shell.look_at_user",
        "track my face.": "visual_shell.look_at_user",
        "loock at me": "visual_shell.look_at_user",
        "loock at me.": "visual_shell.look_at_user",
        "lock at me": "visual_shell.look_at_user",
        "lock at me.": "visual_shell.look_at_user",
        "look me": "visual_shell.look_at_user",
        "look me.": "visual_shell.look_at_user",
        "popatrz na mnie.": "visual_shell.look_at_user",
        "patrz na mnie.": "visual_shell.look_at_user",
        "spójrz na mnie.": "visual_shell.look_at_user",
        "spojrz na mnie.": "visual_shell.look_at_user",
        "stop look at me.": "visual_shell.return_to_idle",
        "stop looking at me.": "visual_shell.return_to_idle",
        "stop tracking me.": "visual_shell.return_to_idle",
        "stop loock at me": "visual_shell.return_to_idle",
        "stop loock at me.": "visual_shell.return_to_idle",
        "stop lock at me": "visual_shell.return_to_idle",
        "stop lock at me.": "visual_shell.return_to_idle",
        "przestań na mnie patrzeć.": "visual_shell.return_to_idle",
        "przestan na mnie patrzec.": "visual_shell.return_to_idle",
        "nie patrz na mnie.": "visual_shell.return_to_idle",
        "przestań mnie śledzić.": "visual_shell.return_to_idle",
        "zatrzymaj śledzenie twarzy.": "visual_shell.return_to_idle",
        "look at me now": "visual_shell.look_at_user",
        "start looking at me": "visual_shell.look_at_user",
        "track my face": "visual_shell.look_at_user",
        "popatrz na mnie": "visual_shell.look_at_user",
        "śledź moją twarz": "visual_shell.look_at_user",
        "sledz moja twarz": "visual_shell.look_at_user",
        "stop look at me": "visual_shell.return_to_idle",
        "stop looking at me": "visual_shell.return_to_idle",
        "stop tracking me": "visual_shell.return_to_idle",
        "przestań na mnie patrzeć": "visual_shell.return_to_idle",
        "przestan na mnie patrzec": "visual_shell.return_to_idle",
        "nie patrz na mnie": "visual_shell.return_to_idle",
        "przestań mnie śledzić": "visual_shell.return_to_idle",
        "zatrzymaj śledzenie twarzy": "visual_shell.return_to_idle",
        "show yourself": "visual_shell.show_self",
        "show your self": "visual_shell.show_self",
        "show the time": "visual_shell.show_time",
        "show time": "visual_shell.show_time",
        "battery": "visual_shell.show_battery",
        "baterie": "visual_shell.show_battery",
        "bateria": "visual_shell.show_battery",
        "jaka masz temperaturę": "visual_shell.show_temperature",
        "jaką masz temperaturę": "visual_shell.show_temperature",
        "jako masz temperatura": "visual_shell.show_temperature",
        "jaka jest twoja temperatura": "visual_shell.show_temperature",
        "cpu temperatura": "visual_shell.show_temperature",
        "temperatura cpu": "visual_shell.show_temperature",
        "temperatura procesora": "visual_shell.show_temperature",
        "what is your cpu": "visual_shell.show_temperature",
        "what is your cpu temperature": "visual_shell.show_temperature",
        "what is the cpu temperature": "visual_shell.show_temperature",
        "show cpu temperature": "visual_shell.show_temperature",
        "processor temperature": "visual_shell.show_temperature",
        "raspberry pi temperature": "visual_shell.show_temperature",
        "pokaz baterie": "visual_shell.show_battery",
        "pokaż baterię": "visual_shell.show_battery",
        "show battery status": "visual_shell.show_battery",
        "display battery": "visual_shell.show_battery",
        "show battery": "visual_shell.show_battery",
        "pokaz temperature cpu": "visual_shell.show_temperature",
        "pokaż temperaturę cpu": "visual_shell.show_temperature",
        "pokaz temperature procesora": "visual_shell.show_temperature",
        "pokaż temperaturę procesora": "visual_shell.show_temperature",
        "display cpu temperature": "visual_shell.show_temperature",
        "show current cpu temperature": "visual_shell.show_temperature",
        "pokaz twarz": "visual_shell.show_face",
        "pokaż twarz": "visual_shell.show_face",
        "twarz": "visual_shell.show_face",
        "your face": "visual_shell.show_face",
        "face": "visual_shell.show_face",
            "pokaż oczy": "visual_shell.show_eyes",
        "pokaz oczy": "visual_shell.show_eyes",
        "show eyes": "visual_shell.show_eyes",
        "spójrz na mnie": "visual_shell.look_at_user",
        "spojrz na mnie": "visual_shell.look_at_user",
        "patrz na mnie": "visual_shell.look_at_user",
        "look at me": "visual_shell.look_at_user",
        "luka to mi": "visual_shell.look_at_user",
        "luka to mi.": "visual_shell.look_at_user",
        "luka to me": "visual_shell.look_at_user",
        "luka to me.": "visual_shell.look_at_user",
        "luca to me": "visual_shell.look_at_user",
        "luca to me.": "visual_shell.look_at_user",
        "look at mi": "visual_shell.look_at_user",
        "look at mi.": "visual_shell.look_at_user",
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
          "remember me": "memory.guided_start",
          "save me to memory": "memory.guided_start",
          "remember this object": "memory.guided_start",
          "remember this thing": "memory.guided_start",
          "remember this phone": "memory.guided_start",
          "save this object": "memory.guided_start",
          "save this thing": "memory.guided_start",
          "save this phone": "memory.guided_start",
          "save this": "memory.guided_start",
          "save that": "memory.guided_start",
          "save to memory": "memory.guided_start",
          "remember": "memory.guided_start",
          "zapamiętaj coś": "memory.guided_start",
          "zapamietaj cos": "memory.guided_start",
          "zapamiętaj to": "memory.guided_start",
          "zapamiętaj mnie": "memory.guided_start",
          "zapamietaj to": "memory.guided_start",
          "zapamietaj mnie": "memory.guided_start",
          "zapamiętaj ten obiekt": "memory.guided_start",
          "zapamietaj ten obiekt": "memory.guided_start",
          "zapamiętaj tę rzecz": "memory.guided_start",
          "zapamietaj te rzecz": "memory.guided_start",
          "zapamiętaj ten telefon": "memory.guided_start",
          "zapamietaj ten telefon": "memory.guided_start",
          "zapisz ten obiekt": "memory.guided_start",
          "zapisz ten telefon": "memory.guided_start",
          "zapisz to": "memory.guided_start",
          "zapisz w pamięci": "memory.guided_start",
          "zapisz w pamieci": "memory.guided_start",
          "pamiętaj coś": "memory.guided_start",
          "pamietaj cos": "memory.guided_start",
          "pamiętaj to": "memory.guided_start",
          "pamietaj to": "memory.guided_start",
          "pamiętaj": "memory.guided_start",
          "pamietaj": "memory.guided_start",
          "zapamiętaj": "memory.guided_start",
          "zapamietaj": "memory.guided_start",
          "memory list": "memory.list",
          "show memory": "memory.list",
          "list memory": "memory.list",
          "show remembered things": "memory.list",
          "what did you save": "memory.list",
          "what have you saved": "memory.list",
          "what do you remember": "memory.list",
          "show what you remember": "memory.list",
          "pokaż pamięć": "memory.list",
          "pokaz pamiec": "memory.list",
          "pokaż co pamiętasz": "memory.list",
          "pokaz co pamietasz": "memory.list",
          "pokaż zapamiętane": "memory.list",
          "pokaz zapamietane": "memory.list",
          "co pamiętasz": "memory.list",
          "co pamietasz": "memory.list",
          "co zapamiętałaś": "memory.list",
          "co zapamietalas": "memory.list",
          "kogo znasz": "memory.recall",
          "kogo z nasz": "memory.recall",
          "kogo z nas": "memory.recall",
          "kogo znas": "memory.recall",
          "kogoznasz": "memory.recall",
          "jakie osoby znasz": "memory.recall",
          "pokaż kogo znasz": "memory.recall",
          "pokaz kogo znasz": "memory.recall",
          "who do you know": "memory.recall",
          "show known people": "memory.recall",
          "jakie obiekty znasz": "memory.recall",
          "jakie obiektyznaz": "memory.recall",
          "jakie obiekty znaz": "memory.recall",
          "what object now": "memory.recall",
          "what objects now": "memory.recall",
          "what object know": "memory.recall",
          "jakie obiekty z nasz": "memory.recall",
          "jakie obiekty z nas": "memory.recall",
          "jakie obiekty znas": "memory.recall",
          "jakie rzeczy znasz": "memory.recall",
          "pokaż zapamiętane obiekty": "memory.recall",
          "pokaz zapamietane obiekty": "memory.recall",
          "what objects do you know": "memory.recall",
          "show known objects": "memory.recall",
          "who you know": "memory.recall",
          "who do you remember": "memory.recall",
          "who can you remember": "memory.recall",
          "who is in your memory": "memory.recall",
          "show people you know": "memory.recall",
          "list known people": "memory.recall",
          "list people you know": "memory.recall",
          "tell me who you know": "memory.recall",
          "what people do you know": "memory.recall",
          "which people do you know": "memory.recall",
          "known people": "memory.recall",
          "what object do you know": "memory.recall",
          "what objects do you need": "memory.recall",
          "what object do you need": "memory.recall",
          "what objects you know": "memory.recall",
          "what object you know": "memory.recall",
          "what objects": "memory.recall",
          "what object": "memory.recall",
          "what objects do you remember": "memory.recall",
          "what object do you remember": "memory.recall",
          "what items do you know": "memory.recall",
          "what item do you know": "memory.recall",
          "what items do you remember": "memory.recall",
          "what item do you remember": "memory.recall",
          "what things do you know": "memory.recall",
          "what thing do you know": "memory.recall",
          "what things do you remember": "memory.recall",
          "what thing do you remember": "memory.recall",
          "which objects do you know": "memory.recall",
          "which items do you know": "memory.recall",
          "which things do you know": "memory.recall",
          "show objects you know": "memory.recall",
          "show my objects": "memory.recall",
          "show remembered objects": "memory.recall",
          "show items you know": "memory.recall",
          "show known items": "memory.recall",
          "show things you know": "memory.recall",
          "list objects": "memory.recall",
          "list known objects": "memory.recall",
          "list my objects": "memory.recall",
          "list remembered objects": "memory.recall",
          "list items": "memory.recall",
          "list known items": "memory.recall",
          "list things": "memory.recall",
          "known objects": "memory.recall",
          "known items": "memory.recall",
          "remembered objects": "memory.recall",
          "remembered items": "memory.recall",
          "objects you know": "memory.recall",
          "items you know": "memory.recall",
          "things you know": "memory.recall",
          "jakie osoby pamiętasz": "memory.recall",
          "jakie osoby pamietasz": "memory.recall",
          "kogo pamiętasz": "memory.recall",
          "kogo pamietasz": "memory.recall",
          "pokaż osoby które znasz": "memory.recall",
          "pokaz osoby ktore znasz": "memory.recall",
          "pokaż znane osoby": "memory.recall",
          "pokaz znane osoby": "memory.recall",
          "lista osób": "memory.recall",
          "lista osob": "memory.recall",
          "lista znanych osób": "memory.recall",
          "lista znanych osob": "memory.recall",
          "osoby które znasz": "memory.recall",
          "osoby ktore znasz": "memory.recall",
          "znane osoby": "memory.recall",
          "jakie przedmioty znasz": "memory.recall",
          "jakie obiekty pamiętasz": "memory.recall",
          "jakie obiekty pamietasz": "memory.recall",
          "jakie rzeczy pamiętasz": "memory.recall",
          "jakie rzeczy pamietasz": "memory.recall",
          "jakie przedmioty pamiętasz": "memory.recall",
          "jakie przedmioty pamietasz": "memory.recall",
          "pokaż obiekty": "memory.recall",
          "pokaz obiekty": "memory.recall",
          "pokaż znane obiekty": "memory.recall",
          "pokaz znane obiekty": "memory.recall",
          "pokaż moje obiekty": "memory.recall",
          "pokaz moje obiekty": "memory.recall",
          "pokaż rzeczy które znasz": "memory.recall",
          "pokaz rzeczy ktore znasz": "memory.recall",
          "pokaż przedmioty które znasz": "memory.recall",
          "pokaz przedmioty ktore znasz": "memory.recall",
          "lista obiektów": "memory.recall",
          "lista obiektow": "memory.recall",
          "lista rzeczy": "memory.recall",
          "lista przedmiotów": "memory.recall",
          "lista przedmiotow": "memory.recall",
          "znane obiekty": "memory.recall",
          "znane rzeczy": "memory.recall",
          "znane przedmioty": "memory.recall",
          "obiekty które znasz": "memory.recall",
          "obiekty ktore znasz": "memory.recall",
          "rzeczy które znasz": "memory.recall",
          "rzeczy ktore znasz": "memory.recall",
          "przedmioty które znasz": "memory.recall",
          "przedmioty ktore znasz": "memory.recall",
}

    # Recall is open-ended ("where is my <anything>"), so we cannot enumerate
    # full phrases like for guided_start. Instead we recognise short prefixes
    # and let MemoryService.recall do the token search using the rest of the
    # transcript as the query key. These prefixes use only words that small
    # Vosk vocabularies recognise (no rare conjugations).
    _RECALL_PREFIXES = (
        "where did i put my ",
        "where did i put the ",
        "where did i put ",
        "where did i leave my ",
        "where did i leave the ",
        "where did i leave ",
        "where is my ",
        "where is the ",
        "where is ",
        "where are my ",
        "where are the ",
        "where are ",
        "remind me where my ",
        "remind me where the ",
        "remind me where ",
        "do you remember where my ",
        "do you remember where the ",
        "do you remember where ",
        "do you remember ",
        "what do you remember about ",
        "gdzie położyłem moje ",
        "gdzie polozylem moje ",
        "gdzie położyłem mój ",
        "gdzie polozylem moj ",
        "gdzie położyłem ",
        "gdzie polozylem ",
        "gdzie położyłam moje ",
        "gdzie polozylam moje ",
        "gdzie położyłam mój ",
        "gdzie polozylam moj ",
        "gdzie położyłam ",
        "gdzie polozylam ",
        "gdzie leży mój ",
        "gdzie lezy moj ",
        "gdzie leży moja ",
        "gdzie lezy moja ",
        "gdzie leży moje ",
        "gdzie lezy moje ",
        "gdzie leży ",
        "gdzie lezy ",
        "przypomnij mi gdzie jest mój ",
        "przypomnij mi gdzie jest moj ",
        "przypomnij mi gdzie jest moja ",
        "przypomnij mi gdzie jest moje ",
        "przypomnij mi gdzie jest ",
        "przypomnij gdzie jest ",
        "pamiętasz gdzie jest mój ",
        "pamietasz gdzie jest moj ",
        "pamiętasz gdzie jest moja ",
        "pamietasz gdzie jest moja ",
        "pamiętasz gdzie jest moje ",
        "pamietasz gdzie jest moje ",
        "pamiętasz gdzie jest ",
        "pamietasz gdzie jest ",
        "gdzie jest mój ",
        "gdzie jest moj ",
        "gdzie jest moja ",
        "gdzie jest moje ",
        "gdzie jest ",
        "gdzie są moje ",
        "gdzie sa moje ",
        "gdzie są ",
        "gdzie sa ",
        "czy pamiętasz gdzie jest ",
        "czy pamietasz gdzie jest ",
        "czy pamiętasz ",
        "czy pamietasz ",
        "co pamiętasz o ",
        "co pamietasz o ",
    )

    @classmethod
    def _memory_guided_action_payload(cls, transcript: str) -> dict[str, Any]:
        normalized = cls._normalize_runtime_text(transcript)
        if normalized in {
            "remember me",
            "save me to memory",
            "zapamiętaj mnie",
            "zapamietaj mnie",
            "pamiętaj mnie",
            "pamietaj mnie",
        }:
            return {"guided": True, "person_enrollment": True}

        object_hint = cls._object_enrollment_hint(normalized)
        if object_hint:
            return {"guided": True, "object_enrollment": True, "object_hint": object_hint}

        return {"guided": True}

    @classmethod
    def _object_enrollment_hint(cls, normalized: str) -> str:
        object_phrases = {
            "remember this object": "object",
            "remember this thing": "object",
            "remember this phone": "phone",
            "save this object": "object",
            "save this thing": "object",
            "save this phone": "phone",
            "zapamiętaj ten obiekt": "obiekt",
            "zapamietaj ten obiekt": "obiekt",
            "zapamiętaj tę rzecz": "rzecz",
            "zapamietaj te rzecz": "rzecz",
            "zapamiętaj ten telefon": "telefon",
            "zapamietaj ten telefon": "telefon",
            "zapisz ten obiekt": "obiekt",
            "zapisz ten telefon": "telefon",
        }
        direct = object_phrases.get(normalized)
        if direct:
            return direct

        prefixes = (
            "remember this ",
            "save this ",
            "zapamiętaj ten ",
            "zapamietaj ten ",
            "zapisz ten ",
        )
        for prefix in prefixes:
            if normalized.startswith(prefix):
                hint = normalized[len(prefix):].strip()
                if hint and hint not in {"me", "mnie", "to", "this", "that"}:
                    return hint
        return ""

    @staticmethod
    def _normalize_runtime_text(transcript: str) -> str:
        return " ".join(
            str(transcript or "")
            .strip()
            .lower()
            .replace(".", " ")
            .replace(",", " ")
            .replace("?", " ")
            .replace("!", " ")
            .split()
        )

    @classmethod
    def _resolve_runtime_intent_key(
        cls,
        *,
        intent_key: str,
        transcript: str,
    ) -> str:
        """Resolve short runtime candidate phrases that can collide in grammar."""

        normalized = cls._normalize_runtime_text(transcript)
        override = cls._TRANSCRIPT_INTENT_OVERRIDES.get(normalized)
        if override:
            return str(override)

        # Fast-lane recall: "where is my X", "gdzie jest X", etc.
        # The X part is variable, so we only match the prefix and let
        # MemoryService.recall resolve the actual subject downstream.
        normalized_with_space = normalized + " "
        for prefix in cls._RECALL_PREFIXES:
            if normalized_with_space.startswith(prefix):
                remainder = normalized_with_space[len(prefix):].strip()
                if remainder:
                    return "memory.recall"

        forget_payload = cls._memory_forget_action_payload(transcript)
        if forget_payload.get("key"):
            return "memory.forget"

        return str(intent_key or "").strip()

    @classmethod
    def _extract_recall_key(cls, transcript: str) -> str:
        """Return the subject portion of a recall transcript, or empty."""
        normalized = cls._normalize_runtime_text(transcript)
        normalized_with_space = normalized + " "
        for prefix in cls._RECALL_PREFIXES:
            if normalized_with_space.startswith(prefix):
                return cls._cleanup_recall_key(normalized_with_space[len(prefix):].strip())
        return ""

    @staticmethod
    def _cleanup_recall_key(text: str) -> str:
        """Remove filler words that often remain after recall-prefix extraction."""
        cleaned = " ".join(str(text or "").split()).strip()
        for prefix in (
            "my ",
            "the ",
            "moje ",
            "mój ",
            "moj ",
            "moja ",
            "mnie ",
            "mi ",
        ):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        return cleaned

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

        action_payload: dict[str, Any] = {}
        if resolved_intent_key == "memory.guided_start":
            action_payload = self._memory_guided_action_payload(transcript)

        # For memory.recall the spoken transcript carries the subject.
        if resolved_intent_key == "memory.recall":
            recall_key = self._extract_recall_key(transcript)
            recall_query = recall_key or str(transcript or "").strip()
            if recall_query:
                action_payload = {"key": recall_query, "query": recall_query}

        if resolved_intent_key == "memory.forget":
            action_payload = self._memory_forget_action_payload(transcript)

        if resolved_intent_key == "system.calculate":
            calculation = evaluate_arithmetic_expression(transcript)
            if not calculation.ok:
                return None
            action_payload = {
                "expression": calculation.expression,
                "result": calculation.result,
                "source_text": str(transcript or "").strip(),
            }

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
                    entities=[
                        EntityValue(name=str(k), value=v)
                        for k, v in action_payload.items()
                    ],
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
                    payload=dict(action_payload),
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
                "payload": dict(action_payload),
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

    _FORGET_TYPE_PREFIXES: Mapping[str, str] = MappingProxyType(
        {
            "person": "person",
            "object": "object",
            "osoba": "person",
            "osobe": "person",
            "osobę": "person",
            "obiekt": "object",
        }
    )

    @classmethod
    def _memory_forget_action_payload(cls, transcript: str) -> dict[str, Any]:
        normalized = cls._normalize_runtime_text(transcript)
        if not normalized:
            return {}

        patterns = (
            ("en", "forget ", ""),
            ("en", "remove ", " from memory"),
            ("en", "delete ", " from memory"),
            ("pl", "zapomnij ", ""),
            ("pl", "usun ", " z pamieci"),
            ("pl", "usuń ", " z pamięci"),
            ("pl", "wykasuj ", " z pamieci"),
            ("pl", "wykasuj ", " z pamięci"),
        )

        raw_target = ""
        for _language, prefix, suffix in patterns:
            if not normalized.startswith(prefix):
                continue
            if suffix and not normalized.endswith(suffix):
                continue
            start = len(prefix)
            end = len(normalized) - len(suffix) if suffix else len(normalized)
            raw_target = normalized[start:end].strip()
            break

        if not raw_target:
            return {}

        target, entity_type = cls._cleanup_memory_forget_target(raw_target)
        if not target:
            return {}

        payload: dict[str, Any] = {"key": target, "query": target}
        if entity_type:
            payload["entity_type"] = entity_type
        return payload

    @classmethod
    def _cleanup_memory_forget_target(cls, target: str) -> tuple[str, str]:
        cleaned = " ".join(str(target or "").split()).strip()
        entity_type = ""
        while cleaned:
            parts = cleaned.split(maxsplit=1)
            mapped_type = cls._FORGET_TYPE_PREFIXES.get(parts[0])
            if not mapped_type or len(parts) == 1:
                break
            entity_type = entity_type or mapped_type
            cleaned = parts[1].strip()
        return cleaned, entity_type
