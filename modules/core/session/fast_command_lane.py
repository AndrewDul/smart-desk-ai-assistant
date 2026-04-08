from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.runtime.contracts import (
    EntityValue,
    IntentMatch,
    RouteDecision,
    RouteKind,
    ToolInvocation,
    create_turn_id,
    normalize_text,
)
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class FastCommandDecision:
    action: str
    language: str
    source: str
    confidence: float
    payload: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    normalized_text: str = ""
    interrupts_pending: bool = False


class FastCommandLane:
    """
    Deterministic low-latency command lane.

    Purpose:
    - bypass the heavier semantic router for obvious commands
    - keep temporal / timer / reminder interactions feeling instant
    - allow a new clear command to override stale pending follow-up state
    - hand off execution to the new ActionFlow instead of legacy handlers
    """

    TEMPORAL_ACTIONS = {
        "ask_time",
        "show_time",
        "ask_date",
        "show_date",
        "ask_day",
        "show_day",
        "ask_month",
        "show_month",
        "ask_year",
        "show_year",
    }

    DIRECT_ACTIONS = {
        "timer_start",
        "timer_stop",
        "focus_start",
        "break_start",
        "introduce_self",
        "memory_store",
        "memory_recall",
        "memory_forget",
        "memory_list",
        "memory_clear",
        "reminder_create",
        "reminders_list",
        "reminder_delete",
        "reminders_clear",
        "help",
        "status",
        "exit",
        "shutdown",
    }

    ALL_ACTIONS = TEMPORAL_ACTIONS | DIRECT_ACTIONS

    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = bool(enabled)

    def try_handle(self, *, prepared: dict[str, Any], assistant: Any) -> bool | None:
        decision = self.classify(prepared=prepared, assistant=assistant)
        if decision is None:
            return None
        return self.execute(assistant=assistant, decision=decision)

    def classify(self, *, prepared: dict[str, Any], assistant: Any) -> FastCommandDecision | None:
        if not self.enabled:
            return None

        raw_text = str(prepared.get("routing_text") or prepared.get("raw_text") or "").strip()
        normalized_text = str(prepared.get("normalized_text") or normalize_text(raw_text))
        if not normalized_text:
            return None

        parser_result = prepared.get("parser_result")
        if parser_result is None:
            parser_result = self._parse_fast(assistant=assistant, text=raw_text)
            if parser_result is not None:
                prepared["parser_result"] = parser_result

        action = self._extract_action(parser_result)
        if action in {"", "unknown", "unclear", "confirm_yes", "confirm_no"}:
            return None

        if action not in self.ALL_ACTIONS:
            return None

        language = assistant._normalize_lang(prepared.get("language") or "en")
        payload = self._extract_payload(parser_result)
        confidence = self._extract_confidence(parser_result)
        interrupts_pending = bool(assistant.pending_confirmation or assistant.pending_follow_up)

        return FastCommandDecision(
            action=action,
            language=language,
            source="fast_command_lane",
            confidence=confidence,
            payload=payload,
            raw_text=raw_text,
            normalized_text=normalized_text,
            interrupts_pending=interrupts_pending,
        )

    def execute(self, *, assistant: Any, decision: FastCommandDecision) -> bool:
        self._interrupt_pending_context(assistant=assistant, action=decision.action)

        assistant.voice_session.set_state("routing", detail=f"fast_lane:{decision.action}")
        assistant._commit_language(decision.language)

        LOGGER.info(
            "Fast command lane executing: action=%s, language=%s, interrupts_pending=%s",
            decision.action,
            decision.language,
            decision.interrupts_pending,
        )

        route = self._build_route_decision(decision)
        return bool(assistant.action_flow.execute(route=route, language=decision.language))

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _parse_fast(self, *, assistant: Any, text: str) -> Any | None:
        parser = getattr(assistant, "parser", None)
        if parser is None:
            return None

        for method_name in ("parse", "parse_intent", "match", "classify"):
            method = getattr(parser, method_name, None)
            if not callable(method):
                continue
            try:
                return method(text)
            except TypeError:
                try:
                    return method(text=text)
                except TypeError:
                    continue
            except Exception as error:
                LOGGER.warning("Fast command parser call failed on %s: %s", method_name, error)
                return None

        return None

    def _interrupt_pending_context(self, *, assistant: Any, action: str) -> None:
        clear_context = getattr(assistant, "_clear_interaction_context", None)
        if callable(clear_context):
            try:
                clear_context(close_active_window=False)
                return
            except TypeError:
                clear_context()
                return

        assistant.pending_confirmation = None
        assistant.pending_follow_up = None

    def _build_route_decision(self, decision: FastCommandDecision) -> RouteDecision:
        tool_name = self._tool_name_for_action(decision.action)

        intents: list[IntentMatch] = [
            IntentMatch(
                name=decision.action,
                confidence=decision.confidence or 1.0,
                entities=[
                    EntityValue(name=str(key), value=value)
                    for key, value in decision.payload.items()
                ],
                requires_clarification=False,
                metadata={"lane": "fast_command"},
            )
        ]

        tools: list[ToolInvocation] = []
        if tool_name:
            tools.append(
                ToolInvocation(
                    tool_name=tool_name,
                    payload=dict(decision.payload),
                    reason="deterministic_fast_path",
                    confidence=max(decision.confidence, 0.90),
                    execute_immediately=True,
                )
            )

        return RouteDecision(
            turn_id=create_turn_id("fast"),
            raw_text=decision.raw_text,
            normalized_text=decision.normalized_text,
            language=decision.language,
            kind=RouteKind.ACTION,
            confidence=max(decision.confidence, 0.90),
            primary_intent=decision.action,
            intents=intents,
            conversation_topics=[],
            tool_invocations=tools,
            notes=["deterministic_fast_path"],
            metadata={
                "lane": "fast_command",
                "interrupts_pending": decision.interrupts_pending,
                "action": decision.action,
                "payload": dict(decision.payload),
                "source": decision.source,
            },
        )

    @staticmethod
    def _extract_action(parser_result: Any) -> str:
        if parser_result is None:
            return ""

        if isinstance(parser_result, dict):
            for key in ("action", "primary_intent", "intent", "name"):
                value = parser_result.get(key)
                if value:
                    return str(value).strip().lower()
            return ""

        for attr in ("action", "primary_intent", "intent", "name"):
            value = getattr(parser_result, attr, None)
            if value:
                return str(value).strip().lower()

        return ""

    @staticmethod
    def _extract_confidence(parser_result: Any) -> float:
        if parser_result is None:
            return 0.0

        if isinstance(parser_result, dict):
            for key in ("confidence", "score"):
                value = parser_result.get(key)
                if value is not None:
                    try:
                        return float(value)
                    except Exception:
                        return 0.0
            return 0.0

        for attr in ("confidence", "score"):
            value = getattr(parser_result, attr, None)
            if value is not None:
                try:
                    return float(value)
                except Exception:
                    return 0.0

        return 0.0

    def _extract_payload(self, parser_result: Any) -> dict[str, Any]:
        if parser_result is None:
            return {}

        if isinstance(parser_result, dict):
            if isinstance(parser_result.get("payload"), dict):
                return dict(parser_result["payload"])
            if isinstance(parser_result.get("entities"), dict):
                return dict(parser_result["entities"])
            if isinstance(parser_result.get("slots"), dict):
                return dict(parser_result["slots"])
            return self._dict_payload_from_known_keys(parser_result)

        for attr in ("payload", "entities", "slots"):
            value = getattr(parser_result, attr, None)
            if isinstance(value, dict):
                return dict(value)

        extracted: dict[str, Any] = {}
        for key in (
            "key",
            "value",
            "message",
            "minutes",
            "seconds",
            "hours",
            "query",
            "item",
            "subject",
            "name",
            "id",
            "reminder_id",
        ):
            value = getattr(parser_result, key, None)
            if value not in (None, ""):
                extracted[key] = value
        return extracted

    @staticmethod
    def _dict_payload_from_known_keys(data: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key in (
            "key",
            "value",
            "message",
            "minutes",
            "seconds",
            "hours",
            "query",
            "item",
            "subject",
            "name",
            "id",
            "reminder_id",
        ):
            value = data.get(key)
            if value not in (None, ""):
                payload[key] = value
        return payload

    @staticmethod
    def _tool_name_for_action(action: str) -> str:
        mapping = {
            "help": "system.help",
            "status": "system.status",
            "introduce_self": "assistant.introduce",
            "ask_time": "clock.time",
            "show_time": "clock.time",
            "ask_date": "clock.date",
            "show_date": "clock.date",
            "ask_day": "clock.day",
            "show_day": "clock.day",
            "ask_month": "clock.month",
            "show_month": "clock.month",
            "ask_year": "clock.year",
            "show_year": "clock.year",
            "memory_list": "memory.list",
            "memory_clear": "memory.clear",
            "memory_store": "memory.store",
            "memory_recall": "memory.recall",
            "memory_forget": "memory.forget",
            "reminders_list": "reminders.list",
            "reminders_clear": "reminders.clear",
            "reminder_create": "reminders.create",
            "reminder_delete": "reminders.delete",
            "timer_start": "timer.start",
            "timer_stop": "timer.stop",
            "focus_start": "focus.start",
            "break_start": "break.start",
            "exit": "system.exit",
            "shutdown": "system.shutdown",
        }
        return mapping.get(str(action).strip().lower(), "")


__all__ = ["FastCommandDecision", "FastCommandLane"]