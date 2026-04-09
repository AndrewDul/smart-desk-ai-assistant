from __future__ import annotations

from typing import Any

from modules.runtime.contracts import ToolInvocation

from .patterns import ACTION_TO_TOOL


class CompanionRouterToolInvocationsMixin:
    """
    Build explicit and suggested tool invocations for routing decisions.
    """

    def _build_explicit_tool_invocations(self, parser_result: Any) -> list[ToolInvocation]:
        action = str(getattr(parser_result, "action", "") or "").strip()
        tool_name = ACTION_TO_TOOL.get(action)
        if not tool_name:
            return []

        payload = dict(getattr(parser_result, "data", {}) or {})

        if action == "confirm_yes":
            payload.setdefault("answer", "yes")
        elif action == "confirm_no":
            payload.setdefault("answer", "no")
        elif action.startswith("show_"):
            payload.setdefault("show", True)
            payload.setdefault("display", True)

        return [
            ToolInvocation(
                tool_name=tool_name,
                payload=payload,
                reason=f"explicit_user_request:{action}",
                confidence=max(float(getattr(parser_result, "confidence", 1.0) or 1.0), 0.75),
                execute_immediately=True,
            )
        ]

    def _build_suggested_tool_invocations(self, topics: list[str]) -> list[ToolInvocation]:
        suggestions: list[ToolInvocation] = []

        def add(tool_name: str, reason: str) -> None:
            if any(existing.tool_name == tool_name for existing in suggestions):
                return
            suggestions.append(
                ToolInvocation(
                    tool_name=tool_name,
                    payload={},
                    reason=reason,
                    confidence=0.65,
                    execute_immediately=False,
                )
            )

        topic_set = set(topics)

        if "focus_struggle" in topic_set:
            add("focus.start", "suggested_from_focus_struggle")
            add("break.start", "suggested_from_focus_struggle")

        if "study_help" in topic_set:
            add("focus.start", "suggested_from_study_help")
            add("reminders.create", "suggested_from_study_help")

        if "overwhelmed" in topic_set:
            add("focus.start", "suggested_from_overwhelmed")
            add("break.start", "suggested_from_overwhelmed")
            add("reminders.create", "suggested_from_overwhelmed")

        if "low_energy" in topic_set:
            add("break.start", "suggested_from_low_energy")
            add("focus.start", "suggested_from_low_energy")

        if "encouragement" in topic_set:
            add("focus.start", "suggested_from_encouragement")

        return suggestions


__all__ = ["CompanionRouterToolInvocationsMixin"]