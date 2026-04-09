from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision, ToolInvocation


class DialogueFlowActions:
    """Tool and action helper methods for dialogue flow."""

    def _immediate_tool_invocations(self, route: RouteDecision) -> list[ToolInvocation]:
        return [
            invocation
            for invocation in route.tool_invocations
            if bool(getattr(invocation, "execute_immediately", True))
        ]

    def _suggested_tool_invocations(self, route: RouteDecision) -> list[ToolInvocation]:
        return [
            invocation
            for invocation in route.tool_invocations
            if not bool(getattr(invocation, "execute_immediately", True))
        ]

    def _suggested_action_names(self, route: RouteDecision) -> list[str]:
        actions: list[str] = []
        for invocation in self._suggested_tool_invocations(route):
            action_name = self._action_name_from_tool(invocation.tool_name)
            if action_name and action_name not in actions:
                actions.append(action_name)
        return actions

    def _payload_from_invocation(self, invocation: ToolInvocation, normalized_text: str) -> Any:
        class _Payload:
            def __init__(self, action: str, data: dict[str, Any], normalized_text: str) -> None:
                self.action = action
                self.data = data
                self.normalized_text = normalized_text
                self.confidence = 1.0
                self.needs_confirmation = False
                self.suggestions = []

        return _Payload(
            action=self._action_name_from_tool(invocation.tool_name),
            data=dict(invocation.payload or {}),
            normalized_text=normalized_text,
        )

    @staticmethod
    def _action_name_from_tool(tool_name: str) -> str:
        mapping = {
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
            "clock.month": "ask_month",
            "clock.year": "ask_year",
            "system.sleep": "exit",
            "system.shutdown": "shutdown",
        }
        normalized = str(tool_name or "").strip().lower()
        return mapping.get(normalized, normalized)


__all__ = ["DialogueFlowActions"]