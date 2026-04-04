from __future__ import annotations

from modules.nlu.router import CompanionRoute, CompanionRouter
from modules.nlu.semantic_router import SemanticRouter
from modules.parsing.intent_parser import IntentParser, IntentResult
from modules.runtime_contracts import RouteDecision, ToolInvocation, normalize_text
from modules.system.utils import append_log


class SemanticCompanionRouter:
    """
    Compatibility bridge between the new semantic routing contract and the current NeXa runtime.

    Why this exists:
    - CoreAssistant still expects CompanionRoute
    - dispatch_intent still expects IntentResult
    - CompanionDialogueService still expects CompanionRoute

    This adapter lets the project move forward step by step:
    new semantic routing inside, current assistant shell outside.
    """

    _TOOL_TO_ACTION: dict[str, str] = {
        "system.help": "help",
        "system.status": "status",
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
        "assistant.introduce": "introduce_self",
        "clock.time": "ask_time",
        "clock.date": "ask_date",
        "clock.day": "ask_day",
        "clock.year": "ask_year",
        "system.sleep": "exit",
        "system.shutdown": "shutdown",
    }

    _ACTIONABLE_INTENTS = {
        "help",
        "status",
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
        "introduce_self",
        "ask_time",
        "show_time",
        "ask_date",
        "show_date",
        "ask_day",
        "show_day",
        "ask_year",
        "show_year",
        "exit",
        "shutdown",
        "confirm_yes",
        "confirm_no",
    }

    def __init__(self, parser: IntentParser) -> None:
        self.parser = parser
        self.semantic_router = SemanticRouter(parser)
        self.legacy_router = CompanionRouter(parser)

    def route(self, text: str, preferred_language: str | None = None) -> CompanionRoute:
        """
        Return the current runtime's CompanionRoute while internally using the new semantic router.

        Fallback strategy:
        if the semantic layer raises an exception for any reason, the old router is used.
        This keeps the migration safe on Raspberry Pi.
        """

        try:
            parser_result = self.parser.parse(text)
            decision = self.semantic_router.route(text, preferred_language=preferred_language)
            return self._decision_to_companion_route(
                text=text,
                parser_result=parser_result,
                decision=decision,
            )
        except Exception as error:
            append_log(f"SemanticCompanionRouter fallback to legacy router: {error}")
            return self.legacy_router.route(text, preferred_language=preferred_language)

    def _decision_to_companion_route(
        self,
        *,
        text: str,
        parser_result: IntentResult,
        decision: RouteDecision,
    ) -> CompanionRoute:
        reply_mode = self._reply_mode_for_decision(decision)
        suggested_actions = self._extract_suggested_actions(decision)
        action_result = self._select_action_result(
            text=text,
            parser_result=parser_result,
            decision=decision,
            suggested_actions=suggested_actions,
        )

        return CompanionRoute(
            kind=decision.kind.value,
            reply_mode=reply_mode,
            language=decision.language,
            raw_text=text,
            normalized_text=decision.normalized_text or normalize_text(text),
            action_result=action_result,
            confidence=float(decision.confidence),
            conversation_topics=list(decision.conversation_topics),
            suggested_actions=suggested_actions,
            notes=list(decision.notes),
        )

    @staticmethod
    def _reply_mode_for_decision(decision: RouteDecision) -> str:
        if decision.kind.value == "action":
            return "execute"
        if decision.kind.value == "conversation":
            return "reply"
        if decision.kind.value == "mixed":
            return "reply_then_offer"
        return "clarify"

    def _select_action_result(
        self,
        *,
        text: str,
        parser_result: IntentResult,
        decision: RouteDecision,
        suggested_actions: list[str],
    ) -> IntentResult:
        """
        Choose the action result that the existing assistant should execute.

        Strong safety rules:
        - action route: may execute a real action
        - mixed route:
            - execute only if the semantic layer contains an immediate tool invocation
            - otherwise force action=unknown
        - conversation route: always action=unknown
        - unclear route: preserve parser clarification suggestions only
        """

        if parser_result.action == "unclear" and parser_result.suggestions:
            return parser_result

        if decision.kind.value == "conversation":
            return self._unknown_result(text, parser_result, decision)

        if decision.kind.value == "unclear":
            return self._unknown_result(text, parser_result, decision)

        if decision.kind.value == "mixed":
            explicit_action = self._explicit_action_from_decision(decision)
            if explicit_action is not None:
                return explicit_action

            # Hard guard:
            # mixed + only suggestions must never silently execute parser actions.
            return self._unknown_result(text, parser_result, decision)

        if decision.kind.value == "action":
            explicit_action = self._explicit_action_from_decision(decision)
            if explicit_action is not None:
                return explicit_action

            if parser_result.action in self._ACTIONABLE_INTENTS:
                return parser_result

            return self._unknown_result(text, parser_result, decision)

        return self._unknown_result(text, parser_result, decision)

    def _unknown_result(
        self,
        text: str,
        parser_result: IntentResult,
        decision: RouteDecision,
    ) -> IntentResult:
        return IntentResult(
            action="unknown",
            data={},
            confidence=float(decision.confidence),
            needs_confirmation=False,
            suggestions=[],
            normalized_text=parser_result.normalized_text or normalize_text(text),
        )

    def _explicit_action_from_decision(self, decision: RouteDecision) -> IntentResult | None:
        """
        Reconstruct an executable action only when the new decision contains
        an immediate tool invocation that maps cleanly to an existing action.
        """

        explicit_tool = self._first_immediate_tool(decision)
        if explicit_tool is None:
            return None

        mapped_action = self._map_tool_invocation_to_action(explicit_tool)
        if not mapped_action:
            return None

        payload = dict(explicit_tool.payload)

        if mapped_action == "confirm_yes":
            payload.setdefault("answer", "yes")
        elif mapped_action == "confirm_no":
            payload.setdefault("answer", "no")

        return IntentResult(
            action=mapped_action,
            data=payload,
            confidence=float(explicit_tool.confidence),
            needs_confirmation=False,
            suggestions=[],
            normalized_text=decision.normalized_text,
        )

    @staticmethod
    def _first_immediate_tool(decision: RouteDecision) -> ToolInvocation | None:
        for invocation in decision.tool_invocations:
            if invocation.execute_immediately:
                return invocation
        return None

    def _extract_suggested_actions(self, decision: RouteDecision) -> list[str]:
        """
        Convert non-immediate tool suggestions from the new router into the old
        suggestion labels expected by CompanionDialogueService.
        """

        results: list[str] = []

        for invocation in decision.tool_invocations:
            if invocation.execute_immediately:
                continue

            mapped_action = self._map_tool_invocation_to_action(invocation)
            if not mapped_action:
                continue

            if mapped_action not in results:
                results.append(mapped_action)

        return results

    def _map_tool_invocation_to_action(self, invocation: ToolInvocation) -> str | None:
        tool_name = str(invocation.tool_name or "").strip()
        payload = dict(invocation.payload or {})

        if tool_name == "dialogue.confirm":
            answer = str(payload.get("answer", "")).strip().lower()
            if answer == "yes":
                return "confirm_yes"
            if answer == "no":
                return "confirm_no"
            return "confirm_yes"

        if tool_name == "clock.time":
            return "show_time" if self._payload_requests_display(payload) else "ask_time"

        if tool_name == "clock.date":
            return "show_date" if self._payload_requests_display(payload) else "ask_date"

        if tool_name == "clock.day":
            return "show_day" if self._payload_requests_display(payload) else "ask_day"

        if tool_name == "clock.year":
            return "show_year" if self._payload_requests_display(payload) else "ask_year"

        return self._TOOL_TO_ACTION.get(tool_name)

    @staticmethod
    def _payload_requests_display(payload: dict) -> bool:
        for key in ("show", "display", "display_only", "show_on_display"):
            value = payload.get(key)
            if isinstance(value, bool) and value:
                return True

            if isinstance(value, str) and value.strip().lower() in {"true", "yes", "1", "display", "show"}:
                return True

        return False