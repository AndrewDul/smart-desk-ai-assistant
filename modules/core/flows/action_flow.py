from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from modules.runtime.contracts import (
    AssistantChunk,
    ChunkKind,
    EntityValue,
    IntentMatch,
    ResponsePlan,
    RouteDecision,
    RouteKind,
    StreamMode,
    ToolInvocation,
    create_turn_id,
)
from modules.shared.logging.logger import get_logger

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class ResolvedAction:
    name: str
    payload: dict[str, Any]
    source: str
    confidence: float = 0.0


class ActionFlowOrchestrator:
    """
    Final action execution flow for NeXa.

    Responsibilities:
    - resolve an executable action from the routed decision
    - execute feature/service operations directly
    - prepare premium spoken/display response plans
    - arm confirmation follow-ups for sensitive actions
    - bridge pending-flow and dialogue-flow into the same action contract
    """

    TOOL_TO_ACTION: dict[str, str] = {
        "system.help": "help",
        "system.status": "status",
        "assistant.introduce": "introduce_self",
        "clock.time": "ask_time",
        "clock.date": "ask_date",
        "clock.day": "ask_day",
        "clock.month": "ask_month",
        "clock.year": "ask_year",
        "memory.list": "memory_list",
        "memory.clear": "memory_clear",
        "memory.store": "memory_store",
        "memory.recall": "memory_recall",
        "memory.forget": "memory_forget",
        "reminders.list": "reminders_list",
        "reminders.clear": "reminders_clear",
        "reminders.create": "reminder_create",
        "reminders.delete": "reminder_delete",
        "timer.start": "timer_start",
        "timer.stop": "timer_stop",
        "focus.start": "focus_start",
        "break.start": "break_start",
        "system.exit": "exit",
        "system.shutdown": "shutdown",
        "system.sleep": "exit",
    }

    SUPPORTED_ACTIONS = {
        "help",
        "status",
        "introduce_self",
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
        "memory_list",
        "memory_clear",
        "memory_store",
        "memory_recall",
        "memory_forget",
        "reminders_list",
        "reminders_clear",
        "reminder_create",
        "reminder_delete",
        "timer_start",
        "timer_stop",
        "focus_start",
        "break_start",
        "exit",
        "shutdown",
        "confirm_yes",
        "confirm_no",
    }

    ACTION_LABELS = {
        "help": ("pomoc", "help"),
        "status": ("status", "status"),
        "introduce_self": ("przedstawienie się", "introduce yourself"),
        "ask_time": ("podanie czasu", "tell the time"),
        "show_time": ("podanie czasu", "tell the time"),
        "ask_date": ("podanie daty", "tell the date"),
        "show_date": ("podanie daty", "tell the date"),
        "ask_day": ("podanie dnia", "tell the day"),
        "show_day": ("podanie dnia", "tell the day"),
        "ask_month": ("podanie miesiąca", "tell the month"),
        "show_month": ("podanie miesiąca", "tell the month"),
        "ask_year": ("podanie roku", "tell the year"),
        "show_year": ("podanie roku", "tell the year"),
        "memory_list": ("pokazanie pamięci", "show memory"),
        "memory_clear": ("wyczyszczenie pamięci", "clear memory"),
        "memory_store": ("zapisanie w pamięci", "save to memory"),
        "memory_recall": ("odczyt z pamięci", "recall memory"),
        "memory_forget": ("usunięcie z pamięci", "forget from memory"),
        "reminders_list": ("pokazanie przypomnień", "show reminders"),
        "reminders_clear": ("usunięcie wszystkich przypomnień", "clear reminders"),
        "reminder_create": ("utworzenie przypomnienia", "create a reminder"),
        "reminder_delete": ("usunięcie przypomnienia", "delete a reminder"),
        "timer_start": ("uruchomienie timera", "start a timer"),
        "timer_stop": ("zatrzymanie timera", "stop the timer"),
        "focus_start": ("uruchomienie focus mode", "start focus mode"),
        "break_start": ("uruchomienie break mode", "start break mode"),
        "exit": ("zamknięcie asystenta", "close the assistant"),
        "shutdown": ("wyłączenie systemu", "shut down the system"),
    }

    def __init__(self, assistant: Any) -> None:
        self.assistant = assistant
        self._display_chars_per_line = int(
            assistant.settings.get("streaming", {}).get("max_display_chars_per_line", 20)
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        *,
        route: RouteDecision | None = None,
        payload: Any | None = None,
        language: str,
    ) -> bool:
        if route is None and payload is not None:
            return self.execute_intent(payload, language)

        if route is None:
            return self._deliver_simple_action_response(
                language=self.assistant._normalize_lang(language),
                action="unknown",
                spoken_text=self._localized(
                    language,
                    "Brakuje danych potrzebnych do wykonania akcji.",
                    "The action request is missing required data.",
                ),
                display_title="ACTION",
                display_lines=self._localized_lines(
                    language,
                    ["brak danych akcji"],
                    ["missing action data"],
                ),
                extra_metadata={"phase": "missing_route"},
            )

        lang = self.assistant._normalize_lang(language)
        resolved = self._resolve_action(route)

        LOGGER.info(
            "Action flow executing: action=%s source=%s confidence=%.3f payload_keys=%s",
            resolved.name,
            resolved.source,
            resolved.confidence,
            sorted(resolved.payload.keys()),
        )

        handler = getattr(self, f"_handle_{resolved.name}", None)
        if not callable(handler):
            return self._handle_unknown(route=route, language=lang, resolved=resolved)

        try:
            return bool(
                handler(
                    route=route,
                    language=lang,
                    payload=resolved.payload,
                    resolved=resolved,
                )
            )
        except Exception as error:
            LOGGER.exception("Action flow handler failed: action=%s error=%s", resolved.name, error)
            return self._deliver_simple_action_response(
                language=lang,
                action=resolved.name,
                spoken_text=self._localized(
                    lang,
                    "Wystąpił problem podczas wykonania tej akcji.",
                    "There was a problem while executing that action.",
                ),
                display_title="ACTION ERROR",
                display_lines=self._display_lines(
                    self._localized(lang, "problem z akcją", "action error")
                ),
                extra_metadata={
                    "resolved_source": resolved.source,
                    "error": str(error),
                },
            )

    def execute_route_action(self, route: RouteDecision, language: str) -> bool:
        return self.execute(route=route, language=language)

    def execute_intent(self, intent: Any, language: str) -> bool:
        action = str(getattr(intent, "action", "") or "").strip().lower()
        if not action:
            return self._deliver_simple_action_response(
                language=self.assistant._normalize_lang(language),
                action="unknown",
                spoken_text=self._localized(
                    language,
                    "Nie rozumiem jeszcze, jaką akcję mam wykonać.",
                    "I do not understand which action I should execute yet.",
                ),
                display_title="ACTION",
                display_lines=self._localized_lines(
                    language,
                    ["nieznana akcja"],
                    ["unknown action"],
                ),
                extra_metadata={"phase": "intent_missing_action"},
            )

        payload = dict(getattr(intent, "data", {}) or {})
        normalized_text = str(getattr(intent, "normalized_text", "") or "").strip()
        confidence = float(getattr(intent, "confidence", 1.0) or 1.0)

        route = RouteDecision(
            turn_id=create_turn_id("intent"),
            raw_text=normalized_text or action,
            normalized_text=normalized_text or action,
            language=self.assistant._normalize_lang(language),
            kind=RouteKind.ACTION,
            confidence=confidence,
            primary_intent=action,
            intents=[
                IntentMatch(
                    name=action,
                    confidence=confidence,
                    entities=[
                        EntityValue(name=str(key), value=value)
                        for key, value in payload.items()
                    ],
                    requires_clarification=False,
                    metadata={"source": "execute_intent"},
                )
            ],
            conversation_topics=[],
            tool_invocations=[],
            notes=["execute_intent_bridge"],
            metadata={
                "action": action,
                "payload": dict(payload),
                "source": "execute_intent",
            },
        )
        return self.execute(route=route, language=language)

    def _ask_for_confirmation(
        self,
        *,
        suggestions: list[dict[str, Any]],
        language: str,
        original_text: str = "",
    ) -> bool:
        lang = self.assistant._normalize_lang(language)
        safe_suggestions = self._coerce_suggestions(suggestions)
        if not safe_suggestions:
            return self._deliver_simple_action_response(
                language=lang,
                action="confirm_no",
                spoken_text=self._localized(
                    lang,
                    "Nie mam jeszcze wystarczających sugestii, żeby poprosić o potwierdzenie.",
                    "I do not have enough suggestions yet to ask for confirmation.",
                ),
                display_title="CONFIRMATION",
                display_lines=self._localized_lines(
                    lang,
                    ["brak sugestii"],
                    ["no suggestions"],
                ),
                extra_metadata={"phase": "missing_suggestions"},
            )

        self.assistant.pending_confirmation = {
            "language": lang,
            "suggestions": safe_suggestions,
            "original_text": str(original_text or "").strip(),
        }

        first = self._action_label(
            str(safe_suggestions[0].get("action", "")),
            lang,
            explicit_label=safe_suggestions[0].get("label"),
        )
        second = None
        if len(safe_suggestions) > 1:
            second = self._action_label(
                str(safe_suggestions[1].get("action", "")),
                lang,
                explicit_label=safe_suggestions[1].get("label"),
            )

        if lang == "pl":
            spoken = f"Czy chodziło Ci o {first}"
            lines = [f"1: {first}"]
            if second:
                spoken += f" czy o {second}"
                lines.append(f"2: {second}")
            spoken += "? Powiedz tak albo nie."
            lines.append("powiedz tak lub nie")
            title = "POTWIERDŹ"
        else:
            spoken = f"Did you mean {first}"
            lines = [f"1: {first}"]
            if second:
                spoken += f" or {second}"
                lines.append(f"2: {second}")
            spoken += "? Say yes or no."
            lines.append("say yes or no")
            title = "CONFIRM"

        return self.assistant.deliver_text_response(
            spoken,
            language=lang,
            route_kind=RouteKind.CONVERSATION,
            source="action_confirmation_prompt",
            metadata={
                "pending_type": "confirmation",
                "suggestions": [item["action"] for item in safe_suggestions],
            },
        )

    # ------------------------------------------------------------------
    # Action resolution
    # ------------------------------------------------------------------

    def _resolve_action(self, route: RouteDecision) -> ResolvedAction:
        tool_match = self._resolve_from_tools(route.tool_invocations)
        if tool_match is not None:
            return tool_match

        primary_match = self._resolve_from_primary_intent(route)
        if primary_match is not None:
            return primary_match

        intent_match = self._resolve_from_intents(route.intents)
        if intent_match is not None:
            return intent_match

        metadata_action = str(route.metadata.get("action", "")).strip().lower()
        if metadata_action in self.SUPPORTED_ACTIONS:
            return ResolvedAction(
                name=metadata_action,
                payload=dict(route.metadata.get("payload", {}) or {}),
                source="route.metadata.action",
                confidence=float(route.confidence),
            )

        return ResolvedAction(
            name="unknown",
            payload={},
            source="fallback",
            confidence=float(route.confidence),
        )

    def _resolve_from_tools(self, tools: list[ToolInvocation]) -> ResolvedAction | None:
        for tool in tools:
            action_name = self.TOOL_TO_ACTION.get(str(tool.tool_name or "").strip().lower())
            if not action_name:
                continue
            return ResolvedAction(
                name=action_name,
                payload=dict(tool.payload or {}),
                source=f"tool:{tool.tool_name}",
                confidence=float(tool.confidence),
            )
        return None

    def _resolve_from_primary_intent(self, route: RouteDecision) -> ResolvedAction | None:
        primary = str(route.primary_intent or "").strip().lower()
        if primary not in self.SUPPORTED_ACTIONS:
            return None

        payload = self._payload_from_matching_intent(route.intents, primary)
        if not payload:
            payload = dict(route.metadata.get("payload", {}) or {})

        return ResolvedAction(
            name=primary,
            payload=payload,
            source="route.primary_intent",
            confidence=float(route.confidence),
        )

    def _resolve_from_intents(self, intents: list[IntentMatch]) -> ResolvedAction | None:
        for item in intents:
            intent_name = str(item.name or "").strip().lower()
            if intent_name not in self.SUPPORTED_ACTIONS:
                continue
            return ResolvedAction(
                name=intent_name,
                payload=self._payload_from_entities(item.entities),
                source=f"intent:{intent_name}",
                confidence=float(item.confidence),
            )
        return None

    def _payload_from_matching_intent(
        self,
        intents: list[IntentMatch],
        intent_name: str,
    ) -> dict[str, Any]:
        target = str(intent_name or "").strip().lower()
        for item in intents:
            if str(item.name or "").strip().lower() == target:
                return self._payload_from_entities(item.entities)
        return {}

    @staticmethod
    def _payload_from_entities(entities: list[EntityValue]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for entity in entities:
            if entity.name:
                payload[str(entity.name)] = entity.value
        return payload

    # ------------------------------------------------------------------
    # Information / system actions
    # ------------------------------------------------------------------

    def _handle_help(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        spoken = self._localized(
            language,
            "Mogę rozmawiać z Tobą, zapamiętywać informacje, ustawiać przypomnienia, uruchamiać timery, focus mode i break mode oraz podawać czas i datę.",
            "I can talk with you, remember information, set reminders, start timers, focus mode and break mode, and tell you the time and date.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="help",
            spoken_text=spoken,
            display_title=self._localized(language, "JAK MOGĘ POMÓC", "HOW I CAN HELP"),
            display_lines=self._localized_lines(
                language,
                ["rozmowa", "pamiec", "przypomnienia", "timery i focus"],
                ["conversation", "memory", "reminders", "timers and focus"],
            ),
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_status(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload

        timer_status = self._timer_status()
        memory_count = len(self._memory_items())
        reminder_count = len(self._reminder_items())
        current_timer = self.assistant.state.get("current_timer") or self._localized(language, "brak", "none")
        focus_on = bool(self.assistant.state.get("focus_mode"))
        break_on = bool(self.assistant.state.get("break_mode"))
        timer_running = bool(timer_status.get("running"))

        if language == "pl":
            spoken = (
                f"Focus jest {'włączony' if focus_on else 'wyłączony'}, "
                f"przerwa jest {'włączona' if break_on else 'wyłączona'}, "
                f"aktywny timer to {current_timer}, "
                f"w pamięci mam {memory_count} wpisów, "
                f"a przypomnień jest {reminder_count}."
            )
            lines = [
                f"focus: {'ON' if focus_on else 'OFF'}",
                f"przerwa: {'ON' if break_on else 'OFF'}",
                f"timer: {current_timer}",
                f"pamiec: {memory_count}",
                f"przyp: {reminder_count}",
                f"dziala: {'TAK' if timer_running else 'NIE'}",
            ]
        else:
            spoken = (
                f"Focus is {'on' if focus_on else 'off'}, "
                f"break is {'on' if break_on else 'off'}, "
                f"the current timer is {current_timer}, "
                f"I have {memory_count} memory items, "
                f"and there are {reminder_count} reminders."
            )
            lines = [
                f"focus: {'ON' if focus_on else 'OFF'}",
                f"break: {'ON' if break_on else 'OFF'}",
                f"timer: {current_timer}",
                f"memory: {memory_count}",
                f"remind: {reminder_count}",
                f"running: {'YES' if timer_running else 'NO'}",
            ]

        return self._deliver_simple_action_response(
            language=language,
            action="status",
            spoken_text=spoken,
            display_title="STATUS",
            display_lines=lines,
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_introduce_self(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload

        spoken = self._localized(
            language,
            "Nazywam się NeXa. Jestem lokalnym asystentem biurkowym działającym na Raspberry Pi.",
            "My name is NeXa. I am a local desk assistant running on Raspberry Pi.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="introduce_self",
            spoken_text=spoken,
            display_title="NeXa",
            display_lines=self._localized_lines(
                language,
                ["lokalny", "desk assistant", "raspberry pi"],
                ["local", "desk assistant", "raspberry pi"],
            ),
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_ask_time(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        spoken = self._localized(language, f"Jest {now.strftime('%H:%M')}.", f"It is {now.strftime('%H:%M')}.")
        return self._deliver_simple_action_response(
            language=language,
            action="ask_time",
            spoken_text=spoken,
            display_title="TIME",
            display_lines=[now.strftime("%H:%M")],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_time(self, **kwargs: Any) -> bool:
        return self._handle_ask_time(**kwargs)

    def _handle_ask_date(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        spoken = self._localized(language, f"Dzisiaj jest {now.strftime('%d.%m.%Y')}.", f"Today is {now.strftime('%d.%m.%Y')}.")
        return self._deliver_simple_action_response(
            language=language,
            action="ask_date",
            spoken_text=spoken,
            display_title="DATE",
            display_lines=[now.strftime("%d.%m.%Y")],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_date(self, **kwargs: Any) -> bool:
        return self._handle_ask_date(**kwargs)

    def _handle_ask_day(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        day_name = self._localized_day_name(now.weekday(), language)
        spoken = self._localized(language, f"Dzisiaj jest {day_name}.", f"Today is {day_name}.")
        return self._deliver_simple_action_response(
            language=language,
            action="ask_day",
            spoken_text=spoken,
            display_title="DAY",
            display_lines=[day_name],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_day(self, **kwargs: Any) -> bool:
        return self._handle_ask_day(**kwargs)

    def _handle_ask_month(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        month_name = self._localized_month_name(now.month, language)
        spoken = self._localized(language, f"Jest miesiąc {month_name}.", f"It is {month_name}.")
        return self._deliver_simple_action_response(
            language=language,
            action="ask_month",
            spoken_text=spoken,
            display_title="MONTH",
            display_lines=[month_name],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_month(self, **kwargs: Any) -> bool:
        return self._handle_ask_month(**kwargs)

    def _handle_ask_year(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        now = self._now_london()
        spoken = self._localized(language, f"Mamy rok {now.year}.", f"The year is {now.year}.")
        return self._deliver_simple_action_response(
            language=language,
            action="ask_year",
            spoken_text=spoken,
            display_title="YEAR",
            display_lines=[str(now.year)],
            extra_metadata={"resolved_source": resolved.source},
        )

    def _handle_show_year(self, **kwargs: Any) -> bool:
        return self._handle_ask_year(**kwargs)

    # ------------------------------------------------------------------
    # Memory actions
    # ------------------------------------------------------------------

    def _handle_memory_store(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route
        key, value = self._resolve_memory_store_fields(payload)

        if not key or not value:
            return self._deliver_simple_action_response(
                language=language,
                action="memory_store",
                spoken_text=self._localized(
                    language,
                    "Brakuje mi tego, co mam zapamiętać albo pod jaką nazwą mam to zapisać.",
                    "I am missing either what I should remember or what key I should save it under.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(
                    language,
                    ["brak danych", "do zapisu"],
                    ["missing data", "for memory"],
                ),
                extra_metadata={"resolved_source": resolved.source, "phase": "missing_fields"},
            )

        remember_method = self._first_callable(self.assistant.memory, "remember", "store", "save", "add")
        if remember_method is None:
            return self._deliver_feature_unavailable(language=language, action="memory_store")

        remember_method(str(key), str(value))

        spoken = self._localized(
            language,
            f"Dobrze. Zapamiętałam: {key}.",
            f"Okay. I remembered: {key}.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="memory_store",
            spoken_text=spoken,
            display_title="MEMORY SAVED",
            display_lines=self._display_lines(str(value)),
            extra_metadata={"resolved_source": resolved.source, "key": str(key)},
        )

    def _handle_memory_recall(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route
        key = self._first_present(payload, "key", "subject", "item", "name", "query")
        if not key:
            return self._deliver_simple_action_response(
                language=language,
                action="memory_recall",
                spoken_text=self._localized(
                    language,
                    "Powiedz proszę, czego mam szukać w pamięci.",
                    "Please tell me what I should look up in memory.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(
                    language,
                    ["podaj klucz", "lub temat"],
                    ["say the key", "or topic"],
                ),
                extra_metadata={"resolved_source": resolved.source, "phase": "missing_key"},
            )

        recall_method = self._first_callable(self.assistant.memory, "recall", "get", "find", "lookup")
        if recall_method is None:
            return self._deliver_feature_unavailable(language=language, action="memory_recall")

        value = recall_method(str(key))
        if not value:
            return self._deliver_simple_action_response(
                language=language,
                action="memory_recall",
                spoken_text=self._localized(
                    language,
                    f"Nie znalazłam niczego dla: {key}.",
                    f"I could not find anything for: {key}.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(
                    language,
                    ["brak wyniku"],
                    ["not found"],
                ),
                extra_metadata={"resolved_source": resolved.source, "key": str(key), "phase": "not_found"},
            )

        spoken = self._localized(
            language,
            f"Dla {key} mam zapisane: {value}.",
            f"For {key}, I have: {value}.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="memory_recall",
            spoken_text=spoken,
            display_title="MEMORY",
            display_lines=self._display_lines(str(value)),
            extra_metadata={"resolved_source": resolved.source, "key": str(key)},
        )

    def _handle_memory_forget(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route
        key = self._first_present(payload, "key", "subject", "item", "name", "query")
        if not key:
            return self._deliver_simple_action_response(
                language=language,
                action="memory_forget",
                spoken_text=self._localized(
                    language,
                    "Powiedz proszę, który wpis mam usunąć z pamięci.",
                    "Please tell me which memory entry I should remove.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(
                    language,
                    ["podaj wpis", "do usuniecia"],
                    ["say entry", "to remove"],
                ),
                extra_metadata={"resolved_source": resolved.source, "phase": "missing_key"},
            )

        forget_method = self._first_callable(self.assistant.memory, "forget", "delete", "remove")
        if forget_method is None:
            return self._deliver_feature_unavailable(language=language, action="memory_forget")

        result = forget_method(str(key))
        removed_key = None
        if isinstance(result, tuple):
            removed_key = result[0]
        elif isinstance(result, str):
            removed_key = result
        elif result:
            removed_key = str(key)

        if not removed_key:
            return self._deliver_simple_action_response(
                language=language,
                action="memory_forget",
                spoken_text=self._localized(
                    language,
                    f"Nie znalazłam wpisu do usunięcia dla: {key}.",
                    f"I could not find an entry to remove for: {key}.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(
                    language,
                    ["nic do usuniecia"],
                    ["nothing to remove"],
                ),
                extra_metadata={"resolved_source": resolved.source, "key": str(key), "phase": "not_found"},
            )

        spoken = self._localized(
            language,
            f"Usunęłam z pamięci: {removed_key}.",
            f"I removed {removed_key} from memory.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="memory_forget",
            spoken_text=spoken,
            display_title="MEMORY REMOVED",
            display_lines=self._display_lines(str(removed_key)),
            extra_metadata={"resolved_source": resolved.source, "key": str(removed_key)},
        )

    def _handle_memory_list(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        items = self._memory_items()
        if not items:
            return self._deliver_simple_action_response(
                language=language,
                action="memory_list",
                spoken_text=self._localized(
                    language,
                    "Nie mam jeszcze zapisanych informacji w pamięci.",
                    "I do not have any saved memory items yet.",
                ),
                display_title="MEMORY",
                display_lines=self._localized_lines(language, ["pamiec pusta"], ["memory empty"]),
                extra_metadata={"resolved_source": resolved.source, "count": 0},
            )

        keys = list(items.keys())[:4]
        spoken = self._localized(
            language,
            f"Mam zapisane {len(items)} wpisy w pamięci.",
            f"I have {len(items)} items saved in memory.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="memory_list",
            spoken_text=spoken,
            display_title="MEMORY",
            display_lines=keys,
            extra_metadata={"resolved_source": resolved.source, "count": len(items)},
        )

    def _handle_memory_clear(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        self.assistant.pending_follow_up = {
            "type": "confirm_memory_clear",
            "language": language,
        }
        spoken = self._localized(
            language,
            "Czy na pewno chcesz wyczyścić całą pamięć?",
            "Are you sure you want to clear all memory?",
        )
        return self.assistant.deliver_text_response(
            spoken,
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="action_memory_clear_confirmation",
            metadata={"resolved_source": resolved.source, "follow_up_type": "confirm_memory_clear"},
        )

    # ------------------------------------------------------------------
    # Reminder actions
    # ------------------------------------------------------------------

    def _handle_reminders_list(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        items = self._reminder_items()
        pending_count = len([item for item in items if str(item.get("status", "pending")) == "pending"])

        if not items:
            return self._deliver_simple_action_response(
                language=language,
                action="reminders_list",
                spoken_text=self._localized(
                    language,
                    "Nie mam zapisanych przypomnień.",
                    "I do not have any saved reminders.",
                ),
                display_title="REMINDERS",
                display_lines=self._localized_lines(language, ["brak przypomnien"], ["no reminders"]),
                extra_metadata={"resolved_source": resolved.source, "count": 0},
            )

        lines = [
            self._localized(language, f"razem: {len(items)}", f"total: {len(items)}"),
            self._localized(language, f"oczekuje: {pending_count}", f"pending: {pending_count}"),
        ]
        for reminder in items[:2]:
            lines.append(self._trim_text(str(reminder.get("message", "")), 22))

        spoken = self._localized(
            language,
            f"Mam zapisane {len(items)} przypomnień. Oczekujących jest {pending_count}.",
            f"I have {len(items)} saved reminders. {pending_count} are still pending.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="reminders_list",
            spoken_text=spoken,
            display_title="REMINDERS",
            display_lines=lines[:4],
            extra_metadata={
                "resolved_source": resolved.source,
                "count": len(items),
                "pending_count": pending_count,
            },
        )

    def _handle_reminders_clear(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        self.assistant.pending_follow_up = {
            "type": "confirm_reminders_clear",
            "language": language,
        }
        spoken = self._localized(
            language,
            "Czy na pewno chcesz usunąć wszystkie przypomnienia?",
            "Are you sure you want to delete all reminders?",
        )
        return self.assistant.deliver_text_response(
            spoken,
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="action_reminders_clear_confirmation",
            metadata={"resolved_source": resolved.source, "follow_up_type": "confirm_reminders_clear"},
        )

    def _handle_reminder_create(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route
        seconds = self._resolve_reminder_seconds(payload)
        message = self._first_present(payload, "message", "content", "text", "value")

        if seconds is None or not message:
            return self._deliver_simple_action_response(
                language=language,
                action="reminder_create",
                spoken_text=self._localized(
                    language,
                    "Brakuje mi czasu albo treści przypomnienia.",
                    "I am missing either the reminder time or the reminder message.",
                ),
                display_title="REMINDER",
                display_lines=self._localized_lines(language, ["brak czasu", "lub tresci"], ["missing time", "or message"]),
                extra_metadata={"resolved_source": resolved.source, "phase": "missing_fields"},
            )

        add_method = self._first_callable(
            self.assistant.reminders,
            "add_after_seconds",
            "add_in_seconds",
            "create_after_seconds",
        )
        if add_method is None:
            return self._deliver_feature_unavailable(language=language, action="reminder_create")

        reminder = add_method(seconds=int(seconds), message=str(message), language=language)
        reminder_id = str(reminder.get("id", "")).strip() if isinstance(reminder, dict) else ""

        spoken = self._localized(
            language,
            f"Dobrze. Ustawiłam przypomnienie za {self._duration_text(int(seconds), language)}.",
            f"Okay. I set a reminder for {self._duration_text(int(seconds), language)}.",
        )

        lines = [
            self._trim_text(str(message), 22),
            self._localized(
                language,
                f"za {self._duration_text(int(seconds), language)}",
                f"in {self._duration_text(int(seconds), language)}",
            ),
        ]
        if reminder_id:
            lines.append(reminder_id)

        return self._deliver_simple_action_response(
            language=language,
            action="reminder_create",
            spoken_text=spoken,
            display_title="REMINDER SAVED",
            display_lines=lines[:3],
            extra_metadata={
                "resolved_source": resolved.source,
                "seconds": int(seconds),
                "reminder_id": reminder_id,
            },
        )

    def _handle_reminder_delete(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route

        reminder_id = self._first_present(payload, "id", "reminder_id")
        message = self._first_present(payload, "message", "query", "content", "text")

        target_id = ""
        target_message = ""

        if reminder_id:
            finder = self._first_callable(self.assistant.reminders, "find_by_id")
            if callable(finder):
                found = finder(str(reminder_id))
                if isinstance(found, dict):
                    target_id = str(found.get("id", "")).strip() or str(reminder_id)
                    target_message = str(found.get("message", "")).strip()
            if not target_id:
                target_id = str(reminder_id)

        elif message:
            finder = self._first_callable(self.assistant.reminders, "find_by_message")
            if finder is None:
                finder = self._first_callable(self.assistant.reminders, "match_by_message")
            if finder is not None:
                found = finder(str(message))
                if isinstance(found, dict):
                    target_id = str(found.get("id", "")).strip()
                    target_message = str(found.get("message", "")).strip()
                else:
                    reminder = getattr(found, "reminder", None)
                    if isinstance(reminder, dict):
                        target_id = str(reminder.get("id", "")).strip()
                        target_message = str(reminder.get("message", "")).strip()

        if not target_id and not target_message:
            return self._deliver_simple_action_response(
                language=language,
                action="reminder_delete",
                spoken_text=self._localized(
                    language,
                    "Nie mogę znaleźć takiego przypomnienia.",
                    "I cannot find that reminder.",
                ),
                display_title="REMINDERS",
                display_lines=self._localized_lines(language, ["nie znaleziono"], ["not found"]),
                extra_metadata={"resolved_source": resolved.source, "phase": "not_found"},
            )

        self.assistant.pending_follow_up = {
            "type": "confirm_reminder_delete",
            "language": language,
            "reminder_id": target_id,
            "message": target_message or message or target_id,
        }

        spoken = self._localized(
            language,
            "Czy na pewno chcesz usunąć to przypomnienie?",
            "Are you sure you want to delete this reminder?",
        )
        return self.assistant.deliver_text_response(
            spoken,
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="action_reminder_delete_confirmation",
            metadata={
                "resolved_source": resolved.source,
                "follow_up_type": "confirm_reminder_delete",
                "reminder_id": target_id,
            },
        )

    # ------------------------------------------------------------------
    # Timer / focus / break actions
    # ------------------------------------------------------------------

    def _handle_timer_start(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route
        minutes = self._resolve_minutes(payload, fallback=10.0)
        return self._start_timer_mode(mode="timer", minutes=minutes, language=language, resolved=resolved)

    def _handle_focus_start(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route
        minutes = self._resolve_minutes(
            payload,
            fallback=float(getattr(self.assistant, "default_focus_minutes", 25)),
        )
        return self._start_timer_mode(mode="focus", minutes=minutes, language=language, resolved=resolved)

    def _handle_break_start(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route
        minutes = self._resolve_minutes(
            payload,
            fallback=float(getattr(self.assistant, "default_break_minutes", 5)),
        )
        return self._start_timer_mode(mode="break", minutes=minutes, language=language, resolved=resolved)

    def _handle_timer_stop(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        stop_method = self._first_callable(self.assistant.timer, "stop", "cancel", "stop_timer")
        if stop_method is None:
            return self._deliver_feature_unavailable(language=language, action="timer_stop")

        result = stop_method()
        ok = self._result_ok(result)

        if ok:
            LOGGER.info("Timer stop accepted by timer service.")
            return True

        error_text = self._result_message(result) or self._localized(
            language,
            "Nie ma teraz aktywnego timera.",
            "There is no active timer right now.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="timer_stop",
            spoken_text=error_text,
            display_title="TIMER",
            display_lines=self._display_lines(error_text),
            extra_metadata={"resolved_source": resolved.source, "phase": "stop_failed"},
        )

    def _start_timer_mode(
        self,
        *,
        mode: str,
        minutes: float,
        language: str,
        resolved: ResolvedAction,
    ) -> bool:
        start_method = self._first_callable(self.assistant.timer, "start", "start_timer")
        if start_method is None:
            return self._deliver_feature_unavailable(language=language, action=f"{mode}_start")

        result = start_method(float(minutes), mode)
        ok = self._result_ok(result)

        if ok:
            LOGGER.info("Timer start accepted: mode=%s minutes=%s", mode, minutes)
            return True

        error_text = self._result_message(result) or self._localized(
            language,
            "Nie mogę teraz uruchomić timera.",
            "I cannot start the timer right now.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action=f"{mode}_start",
            spoken_text=error_text,
            display_title="TIMER",
            display_lines=self._display_lines(error_text),
            extra_metadata={
                "resolved_source": resolved.source,
                "phase": "start_failed",
                "minutes": float(minutes),
                "mode": mode,
            },
        )

    # ------------------------------------------------------------------
    # Exit / shutdown / confirmations
    # ------------------------------------------------------------------

    def _handle_exit(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        self.assistant.pending_follow_up = {"type": "confirm_exit", "lang": language}
        spoken = self._localized(
            language,
            "Czy chcesz, żebym zamknęła asystenta?",
            "Do you want me to close the assistant?",
        )
        return self.assistant.deliver_text_response(
            spoken,
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="action_exit_confirmation",
            metadata={"resolved_source": resolved.source, "follow_up_type": "confirm_exit"},
        )

    def _handle_shutdown(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload

        allow_shutdown = bool(self.assistant.settings.get("system", {}).get("allow_shutdown_commands", False))
        if not allow_shutdown:
            return self._deliver_simple_action_response(
                language=language,
                action="shutdown",
                spoken_text=self._localized(
                    language,
                    "Wyłączanie systemu jest teraz wyłączone w ustawieniach.",
                    "System shutdown is currently disabled in settings.",
                ),
                display_title="SHUTDOWN DISABLED",
                display_lines=self._localized_lines(language, ["sprawdz ustawienia"], ["check settings"]),
                extra_metadata={"resolved_source": resolved.source, "phase": "blocked_by_config"},
            )

        self.assistant.pending_follow_up = {"type": "confirm_shutdown", "lang": language}
        spoken = self._localized(
            language,
            "Czy chcesz, żebym wyłączyła system?",
            "Do you want me to shut down the system?",
        )
        return self.assistant.deliver_text_response(
            spoken,
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="action_shutdown_confirmation",
            metadata={"resolved_source": resolved.source, "follow_up_type": "confirm_shutdown"},
        )

    def _handle_confirm_yes(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        return self._deliver_simple_action_response(
            language=language,
            action="confirm_yes",
            spoken_text=self._localized(
                language,
                "Nie ma teraz nic do potwierdzenia.",
                "There is nothing to confirm right now.",
            ),
            display_title="CONFIRMATION",
            display_lines=self._localized_lines(language, ["brak aktywnego", "potwierdzenia"], ["nothing active", "to confirm"]),
            extra_metadata={"resolved_source": resolved.source, "phase": "orphan_confirmation"},
        )

    def _handle_confirm_no(self, **kwargs: Any) -> bool:
        return self._handle_confirm_yes(**kwargs)

    # ------------------------------------------------------------------
    # Fallback
    # ------------------------------------------------------------------

    def _handle_unknown(
        self,
        *,
        route: RouteDecision,
        language: str,
        resolved: ResolvedAction,
    ) -> bool:
        del route
        return self._deliver_simple_action_response(
            language=language,
            action="unknown",
            spoken_text=self._localized(
                language,
                "Nie mam jeszcze tej funkcji w obecnej wersji, ale mogę pomóc z pamięcią, przypomnieniami, timerami, focus mode, break mode oraz czasem i datą.",
                "I do not have that feature in this version yet, but I can help with memory, reminders, timers, focus mode, break mode, and time or date questions.",
            ),
            display_title="ACTION",
            display_lines=self._localized_lines(language, ["funkcja", "jeszcze niedostepna"], ["feature", "not ready yet"]),
            extra_metadata={"resolved_source": resolved.source, "phase": "unsupported_action"},
        )

    # ------------------------------------------------------------------
    # Response helpers
    # ------------------------------------------------------------------

    def _deliver_simple_action_response(
        self,
        *,
        language: str,
        action: str,
        spoken_text: str,
        display_title: str,
        display_lines: list[str],
        extra_metadata: dict[str, Any] | None = None,
        chunk_kind: ChunkKind = ChunkKind.CONTENT,
    ) -> bool:
        plan = ResponsePlan(
            turn_id=create_turn_id(),
            language=language,
            route_kind=RouteKind.ACTION,
            stream_mode=StreamMode.SENTENCE,
            metadata={
                "display_title": display_title,
                "display_lines": display_lines,
            },
        )
        plan.chunks.append(
            AssistantChunk(
                text=spoken_text,
                language=language,
                kind=chunk_kind,
                speak_now=True,
                flush=True,
                sequence_index=0,
                metadata={"action": action},
            )
        )
        return bool(
            self.assistant.deliver_response_plan(
                plan,
                source=f"action_flow:{action}",
                remember=True,
                extra_metadata=extra_metadata or {},
            )
        )

    def _deliver_feature_unavailable(self, *, language: str, action: str) -> bool:
        return self._deliver_simple_action_response(
            language=language,
            action=action,
            spoken_text=self._localized(
                language,
                "Ta funkcja nie jest teraz poprawnie podłączona.",
                "That feature is not wired correctly right now.",
            ),
            display_title="FEATURE",
            display_lines=self._localized_lines(language, ["funkcja", "niedostepna"], ["feature", "unavailable"]),
            extra_metadata={"phase": "feature_unavailable"},
        )

    # ------------------------------------------------------------------
    # Service adapters
    # ------------------------------------------------------------------

    def _memory_items(self) -> dict[str, Any]:
        get_method = self._first_callable(self.assistant.memory, "get_all", "list_all", "items", "export")
        if get_method is None:
            return {}
        try:
            result = get_method()
        except Exception:
            return {}
        return dict(result or {}) if isinstance(result, dict) else {}

    def _reminder_items(self) -> list[dict[str, Any]]:
        list_method = self._first_callable(self.assistant.reminders, "list_all", "all", "items", "list")
        if list_method is None:
            return []
        try:
            result = list_method()
        except Exception:
            return []
        return list(result or []) if isinstance(result, list) else []

    def _timer_status(self) -> dict[str, Any]:
        status_method = self._first_callable(self.assistant.timer, "status", "get_status")
        if status_method is None:
            return {"running": False}
        try:
            result = status_method()
        except Exception:
            return {"running": False}
        return dict(result or {}) if isinstance(result, dict) else {"running": False}

    @staticmethod
    def _first_callable(obj: Any, *names: str):
        for name in names:
            method = getattr(obj, name, None)
            if callable(method):
                return method
        return None

    @staticmethod
    def _result_ok(result: Any) -> bool:
        if isinstance(result, tuple) and result:
            return bool(result[0])
        if isinstance(result, bool):
            return result
        if isinstance(result, dict):
            if "ok" in result:
                return bool(result["ok"])
            if "success" in result:
                return bool(result["success"])
        return bool(result)

    @staticmethod
    def _result_message(result: Any) -> str:
        if isinstance(result, tuple) and len(result) >= 2:
            return str(result[1] or "").strip()
        if isinstance(result, dict):
            for key in ("message", "detail", "error"):
                value = result.get(key)
                if value:
                    return str(value).strip()
        return ""

    # ------------------------------------------------------------------
    # Payload parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _first_present(payload: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    def _resolve_minutes(self, payload: dict[str, Any], *, fallback: float) -> float:
        for key in ("minutes", "duration_minutes", "duration", "value"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                parsed = float(value)
                if parsed > 0:
                    return parsed
            except Exception:
                continue

        seconds = payload.get("seconds")
        if seconds is not None:
            try:
                parsed_seconds = int(seconds)
                if parsed_seconds > 0:
                    return max(1.0 / 60.0, parsed_seconds / 60.0)
            except Exception:
                pass

        return max(float(fallback), 0.1)

    def _resolve_reminder_seconds(self, payload: dict[str, Any]) -> int | None:
        for key in ("seconds", "after_seconds"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                parsed = int(float(value))
                if parsed > 0:
                    return parsed
            except Exception:
                continue

        for key in ("minutes", "after_minutes", "duration_minutes"):
            value = payload.get(key)
            if value is None:
                continue
            try:
                parsed = float(value)
                if parsed > 0:
                    return max(1, int(round(parsed * 60)))
            except Exception:
                continue

        hours = payload.get("hours")
        if hours is not None:
            try:
                parsed = float(hours)
                if parsed > 0:
                    return max(1, int(round(parsed * 3600)))
            except Exception:
                pass

        return None

    def _resolve_memory_store_fields(self, payload: dict[str, Any]) -> tuple[str | None, str | None]:
        key = self._first_present(payload, "key", "subject", "item", "name")
        value = self._first_present(payload, "value", "fact", "content", "location", "message")

        if key and value:
            return key, value

        memory_text = self._first_present(payload, "memory_text", "text")
        if not memory_text:
            return key, value

        for separator in (" is ", " are ", " jest ", " sa "):
            if separator in memory_text:
                left, right = memory_text.split(separator, 1)
                left = left.strip()
                right = right.strip()
                if left and right:
                    return left, right

        location_markers = (" in ", " on ", " at ", " under ", " inside ", " w ", " na ", " pod ", " przy ")
        for marker in location_markers:
            if marker in memory_text:
                left, right = memory_text.split(marker, 1)
                left = left.strip()
                right = f"{marker.strip()} {right.strip()}".strip()
                if left and right:
                    return left, right

        return key, value

    def _coerce_suggestions(self, suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        coerced: list[dict[str, Any]] = []
        for item in suggestions or []:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action", "")).strip().lower()
            if not action:
                continue
            suggestion = {"action": action}
            label = str(item.get("label", "")).strip()
            if label:
                suggestion["label"] = label
            payload = item.get("payload")
            if isinstance(payload, dict) and payload:
                suggestion["payload"] = dict(payload)
            coerced.append(suggestion)
        return coerced

    def _action_label(
        self,
        action: str,
        language: str,
        *,
        explicit_label: Any | None = None,
    ) -> str:
        label_text = str(explicit_label or "").strip()
        if label_text:
            return label_text

        pl_label, en_label = self.ACTION_LABELS.get(
            str(action).strip().lower(),
            (str(action).replace("_", " "), str(action).replace("_", " ")),
        )
        return pl_label if self.assistant._normalize_lang(language) == "pl" else en_label

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _now_london() -> datetime:
        return datetime.now(ZoneInfo("Europe/London"))

    def _localized(self, language: str, polish_text: str, english_text: str) -> str:
        return polish_text if self.assistant._normalize_lang(language) == "pl" else english_text

    def _localized_lines(self, language: str, polish_lines: list[str], english_lines: list[str]) -> list[str]:
        return polish_lines if self.assistant._normalize_lang(language) == "pl" else english_lines

    def _display_lines(self, text: str) -> list[str]:
        cleaned = " ".join(str(text or "").split()).strip()
        if not cleaned:
            return [""]

        max_chars = max(10, self._display_chars_per_line)
        if len(cleaned) <= max_chars:
            return [cleaned]

        words = cleaned.split()
        lines: list[str] = []
        current = ""

        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_chars:
                lines.append(current)
                current = word
                if len(lines) >= 2:
                    break
            else:
                current = candidate

        if current and len(lines) < 2:
            lines.append(current)

        if not lines:
            return [cleaned[:max_chars]]

        if len(lines) == 2 and len(" ".join(words)) > len(" ".join(lines)):
            lines[1] = self._trim_text(lines[1], max_chars)

        return lines[:2]

    @staticmethod
    def _trim_text(text: str, max_len: int) -> str:
        compact = " ".join(str(text or "").split()).strip()
        if len(compact) <= max_len:
            return compact
        return compact[: max_len - 3].rstrip() + "..."

    def _duration_text(self, seconds: int, language: str) -> str:
        safe_seconds = max(int(seconds), 1)
        if safe_seconds < 60:
            return f"{safe_seconds} sekund" if language == "pl" else f"{safe_seconds} seconds"

        minutes = max(1, int(round(safe_seconds / 60)))
        if language == "pl":
            return "1 minutę" if minutes == 1 else f"{minutes} minut"
        return "1 minute" if minutes == 1 else f"{minutes} minutes"

    @staticmethod
    def _localized_day_name(weekday: int, language: str) -> str:
        polish = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
        english = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_index = max(0, min(int(weekday), 6))
        return polish[day_index] if language == "pl" else english[day_index]

    @staticmethod
    def _localized_month_name(month: int, language: str) -> str:
        polish = [
            "",
            "styczeń",
            "luty",
            "marzec",
            "kwiecień",
            "maj",
            "czerwiec",
            "lipiec",
            "sierpień",
            "wrzesień",
            "październik",
            "listopad",
            "grudzień",
        ]
        english = [
            "",
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        month_index = max(1, min(int(month), 12))
        return polish[month_index] if language == "pl" else english[month_index]


__all__ = ["ActionFlowOrchestrator", "ResolvedAction"]