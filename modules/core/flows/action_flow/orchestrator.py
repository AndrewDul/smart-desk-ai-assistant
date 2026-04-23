from __future__ import annotations

import inspect
import time
from typing import Any

from modules.runtime.contracts import (
    EntityValue,
    IntentMatch,
    RouteDecision,
    RouteKind,
    create_turn_id,
)
from modules.shared.logging.logger import get_logger

from .executors import MemorySkillExecutor, ReminderSkillExecutor, TimerSkillExecutor
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
        self._timer_skill_executor: TimerSkillExecutor | None = None
        self._memory_skill_executor: MemorySkillExecutor | None = None
        self._reminder_skill_executor: ReminderSkillExecutor | None = None
        self._display_chars_per_line = int(
            assistant.settings.get("streaming", {}).get("max_display_chars_per_line", 20)
        )

    _VISION_PRIORITY_ACTIONS = frozenset({
        "look_direction",
    })
    _VISION_PRIORITY_SOURCE_PREFIXES = (
        "pan_tilt.",
        "vision.",
        "camera.",
    )

    def _should_use_vision_action_mode(self, *, request: SkillRequest) -> bool:
        action = str(getattr(request, "action", "") or "").strip().lower()
        if action in self._VISION_PRIORITY_ACTIONS:
            return True

        source = str(getattr(request, "source", "") or "").strip().lower()
        if source.startswith(self._VISION_PRIORITY_SOURCE_PREFIXES):
            return True

        route = getattr(request, "route", None)
        tool_invocations = list(getattr(route, "tool_invocations", []) or [])
        for tool in tool_invocations:
            tool_name = str(getattr(tool, "tool_name", "") or "").strip().lower()
            if tool_name.startswith(self._VISION_PRIORITY_SOURCE_PREFIXES):
                return True

        return False

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
        vision_action_mode_requested = self._should_use_vision_action_mode(request=request)
        if vision_action_mode_requested:
            self.assistant._enter_ai_broker_vision_action_mode(
                reason=f"action_route_started:{request.action}",
            )

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
        self._note_skill_started(request=request)

        execution_started_at = time.perf_counter()
        try:
            handler = getattr(self, f"_handle_{resolved.name}", None)
            if not callable(handler):
                handler_result = self._handle_unknown(route=route, language=lang, resolved=resolved)
                self._last_skill_result = self._finalize_skill_result(
                    request=request,
                    result=self._coerce_skill_result(
                        request=request,
                        result=handler_result,
                    ),
                    started_at=execution_started_at,
                )
                return bool(self._last_skill_result)
            try:
                handler_result = self._invoke_action_handler(
                    handler=handler,
                    route=route,
                    language=lang,
                    resolved=resolved,
                    request=request,
                )
                self._last_skill_result = self._finalize_skill_result(
                    request=request,
                    result=self._coerce_skill_result(
                        request=request,
                        result=handler_result,
                    ),
                    started_at=execution_started_at,
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
                self._last_skill_result = self._finalize_skill_result(
                    request=request,
                    result=SkillResult(
                        action=request.action,
                        handled=True,
                        response_delivered=bool(delivered),
                        status="error",
                        metadata={
                            "error": str(error),
                            "source": request.source,
                            "capture_phase": request.capture_phase,
                            "capture_backend": request.capture_backend,
                            "response_kind": "direct_response" if bool(delivered) else "accepted_only",
                        },
                    ),
                    started_at=execution_started_at,
                )
                return bool(self._last_skill_result)
        finally:
            if vision_action_mode_requested:
                self.assistant._enter_ai_broker_recovery_window(
                    reason=f"action_route_finished:{request.action}",
                    return_to_mode="idle_baseline",
                )
            self._active_route = None
            self._active_resolved_action = None
            self._active_skill_request = None



    def _get_timer_skill_executor(self) -> TimerSkillExecutor:
        if self._timer_skill_executor is None:
            self._timer_skill_executor = TimerSkillExecutor(assistant=self.assistant)
        return self._timer_skill_executor

    def _get_memory_skill_executor(self) -> MemorySkillExecutor:
        if self._memory_skill_executor is None:
            self._memory_skill_executor = MemorySkillExecutor(assistant=self.assistant)
        return self._memory_skill_executor

    def _get_reminder_skill_executor(self) -> ReminderSkillExecutor:
        if self._reminder_skill_executor is None:
            self._reminder_skill_executor = ReminderSkillExecutor(assistant=self.assistant)
        return self._reminder_skill_executor

    def _invoke_action_handler(
        self,
        *,
        handler: Any,
        route: RouteDecision,
        language: str,
        resolved: ResolvedAction,
        request: SkillRequest,
    ) -> Any:
        kwargs = {
            "route": route,
            "language": language,
            "payload": resolved.payload,
            "resolved": resolved,
        }

        try:
            parameters = inspect.signature(handler).parameters
        except (TypeError, ValueError):
            parameters = {}

        if "request" in parameters:
            kwargs["request"] = request

        return handler(**kwargs)

    def _note_skill_started(self, *, request: SkillRequest) -> None:
        benchmark_service = getattr(self.assistant, "turn_benchmark_service", None)
        method = getattr(benchmark_service, "note_skill_started", None)
        if not callable(method):
            return

        try:
            method(
                action=request.action,
                source=request.source,
            )
        except Exception as error:
            self.LOGGER.debug(
                "Skill benchmark note_skill_started failed: action=%s error=%s",
                request.action,
                error,
            )

    def _note_skill_finished(self, *, request: SkillRequest, result: SkillResult) -> None:
        benchmark_service = getattr(self.assistant, "turn_benchmark_service", None)
        method = getattr(benchmark_service, "note_skill_finished", None)
        if not callable(method):
            return

        metadata = dict(result.metadata or {})
        try:
            method(
                action=result.action or request.action,
                status=result.status,
                source=str(metadata.get("source", request.source) or request.source),
            )
        except Exception as error:
            self.LOGGER.debug(
                "Skill benchmark note_skill_finished failed: action=%s error=%s",
                result.action or request.action,
                error,
            )



    def _finalize_skill_result(
        self,
        *,
        request: SkillRequest,
        result: SkillResult,
        started_at: float,
    ) -> SkillResult:
        metadata = dict(result.metadata or {})
        response_kind = str(metadata.get("response_kind", "") or "").strip()
        if not response_kind:
            if result.response_delivered:
                response_kind = "direct_response"
            elif result.handled:
                response_kind = "accepted_only"
            else:
                response_kind = "not_handled"

        metadata.update(
            {
                "turn_id": request.turn_id,
                "latency_ms": max(0.0, (time.perf_counter() - float(started_at)) * 1000.0),
                "response_kind": response_kind,
            }
        )
        finalized = SkillResult(
            action=result.action,
            handled=result.handled,
            response_delivered=result.response_delivered,
            status=result.status,
            metadata=metadata,
        )
        self._note_skill_finished(request=request, result=finalized)
        return finalized



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