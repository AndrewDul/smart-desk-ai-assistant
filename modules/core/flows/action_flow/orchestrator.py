from __future__ import annotations

from typing import Any

from modules.runtime.contracts import (
    EntityValue,
    IntentMatch,
    RouteDecision,
    RouteKind,
    create_turn_id,
)
from modules.shared.logging.logger import get_logger

from .memory_actions_mixin import ActionMemoryActionsMixin
from .models import ResolvedAction, SkillRequest, SkillResult
from .pan_tilt_actions_mixin import ActionPanTiltActionsMixin
from .reminder_actions_mixin import ActionReminderActionsMixin
from .resolver_mixin import ActionResolverMixin
from .response_helpers_mixin import ActionResponseHelpersMixin
from .system_actions_mixin import ActionSystemActionsMixin
from .timer_actions_mixin import ActionTimerActionsMixin

LOGGER = get_logger(__name__)


class ActionFlowOrchestrator(
    ActionResolverMixin,
    ActionResponseHelpersMixin,
    ActionSystemActionsMixin,
    ActionMemoryActionsMixin,
    ActionReminderActionsMixin,
    ActionTimerActionsMixin,
    ActionPanTiltActionsMixin,
):
    """
    Final action execution flow for NeXa.

    Responsibilities:
    - resolve an executable action from the routed decision
    - execute feature/service operations directly
    - prepare premium spoken/display response plans
    - arm confirmation follow-ups for sensitive actions
    - bridge pending-flow and dialogue-flow into the same action contract
    """

    LOGGER = LOGGER

    TOOL_TO_ACTION: dict[str, str] = {
        "system.help": "help",
        "system.status": "status",
        "system.debug_status": "debug_status",
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
        "pan_tilt.look": "look_direction",
        "system.exit": "exit",
        "system.shutdown": "shutdown",
        "system.sleep": "exit",
    }

    SUPPORTED_ACTIONS = {
        "help",
        "status",
        "debug_status",
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
        "look_direction",
        "exit",
        "shutdown",
        "confirm_yes",
        "confirm_no",
    }

    ACTION_LABELS = {
        "help": ("pomoc", "help"),
        "status": ("status", "status"),
        "debug_status": ("status debug", "debug status"),
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
        "look_direction": ("ruch głowicy", "move camera head"),
        "exit": ("zamknięcie asystenta", "close the assistant"),
        "shutdown": ("wyłączenie systemu", "shut down the system"),
    }

    def __init__(self, assistant: Any) -> None:
        self.assistant = assistant
        self._active_route: RouteDecision | None = None
        self._active_resolved_action: ResolvedAction | None = None
        self._active_skill_request: SkillRequest | None = None
        self._last_skill_result: SkillResult | None = None
        self._display_chars_per_line = int(
            assistant.settings.get("streaming", {}).get("max_display_chars_per_line", 20)
        )

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
        request = SkillRequest.from_route(
            route=route,
            resolved=resolved,
            language=lang,
        )

        self._last_skill_result = None
        self._active_route = route
        self._active_resolved_action = resolved
        self._active_skill_request = request

        self.LOGGER.info(
            "Action flow executing: action=%s source=%s route_kind=%s capture_phase=%s capture_backend=%s confidence=%.3f payload_keys=%s",
            request.action,
            request.source,
            request.route_kind,
            request.capture_phase,
            request.capture_backend,
            request.confidence,
            sorted(request.payload.keys()),
        )

        try:
            handler = getattr(self, f"_handle_{resolved.name}", None)
            if not callable(handler):
                handler_result = self._handle_unknown(route=route, language=lang, resolved=resolved)
                self._last_skill_result = self._coerce_skill_result(
                    request=request,
                    result=handler_result,
                )
                return bool(self._last_skill_result)

            try:
                handler_result = handler(
                    route=route,
                    language=lang,
                    payload=resolved.payload,
                    resolved=resolved,
                )
                self._last_skill_result = self._coerce_skill_result(
                    request=request,
                    result=handler_result,
                )
                return bool(self._last_skill_result)
            except Exception as error:
                self.LOGGER.exception("Action flow handler failed: action=%s error=%s", resolved.name, error)
                delivered = self._deliver_simple_action_response(
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
                self._last_skill_result = SkillResult(
                    action=request.action,
                    handled=True,
                    response_delivered=bool(delivered),
                    status="error",
                    metadata={
                        "error": str(error),
                        "source": request.source,
                        "capture_phase": request.capture_phase,
                        "capture_backend": request.capture_backend,
                    },
                )
                return bool(self._last_skill_result)
        finally:
            self._active_route = None
            self._active_resolved_action = None
            self._active_skill_request = None

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

    def _coerce_skill_result(
        self,
        *,
        request: SkillRequest,
        result: Any,
    ) -> SkillResult:
        base_metadata = {
            "turn_id": request.turn_id,
            "source": request.source,
            "route_kind": request.route_kind,
            "primary_intent": request.primary_intent,
            "capture_phase": request.capture_phase,
            "capture_mode": request.capture_mode,
            "capture_backend": request.capture_backend,
        }

        if isinstance(result, SkillResult):
            merged_metadata = {
                **base_metadata,
                **dict(result.metadata or {}),
            }
            return SkillResult(
                action=str(result.action or request.action).strip() or request.action,
                handled=bool(result.handled),
                response_delivered=bool(result.response_delivered),
                status=str(result.status or "completed").strip() or "completed",
                metadata=merged_metadata,
            )

        if isinstance(result, dict):
            handled = bool(result.get("handled", bool(result)))
            response_delivered = bool(result.get("response_delivered", handled))
            status = str(result.get("status") or ("completed" if handled else "not_handled")).strip()
            merged_metadata = {
                **base_metadata,
                **dict(result.get("metadata", {}) or {}),
            }
            return SkillResult(
                action=str(result.get("action") or request.action).strip() or request.action,
                handled=handled,
                response_delivered=response_delivered,
                status=status or "completed",
                metadata=merged_metadata,
            )

        handled = bool(result)
        return SkillResult(
            action=request.action,
            handled=handled,
            response_delivered=handled,
            status="completed" if handled else "not_handled",
            metadata=base_metadata,
        )


__all__ = ["ActionFlowOrchestrator", "ResolvedAction", "SkillRequest", "SkillResult"]