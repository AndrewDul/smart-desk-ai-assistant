from __future__ import annotations

import re
from typing import Any

from .patterns import (
    ALWAYS_EXPLICIT_ACTIONS,
    DIRECT_ACTIONS,
    EXPLICIT_BREAK_PATTERNS,
    EXPLICIT_FOCUS_PATTERNS,
    EXPLICIT_HELP_PATTERNS,
)


class CompanionRouterExplicitActionMixin:
    """
    Decide whether the parser action should be treated as an explicit action.
    """

    def _should_treat_parser_action_as_explicit(
        self,
        *,
        normalized_text: str,
        parser_result: Any,
        conversation_topics: list[str],
    ) -> bool:
        action = str(getattr(parser_result, "action", "") or "").strip()
        if action in {"unknown", "unclear"}:
            return False

        if action in ALWAYS_EXPLICIT_ACTIONS:
            return True

        if action == "help":
            return any(re.search(pattern, normalized_text) for pattern in EXPLICIT_HELP_PATTERNS)

        if action == "focus_start":
            if getattr(parser_result, "data", {}).get("minutes") is not None:
                return True
            if any(re.search(pattern, normalized_text) for pattern in EXPLICIT_FOCUS_PATTERNS):
                return True
            if conversation_topics:
                return False
            return normalized_text in {
                "focus",
                "focus mode",
                "focus session",
                "skupienie",
                "tryb skupienia",
                "sesja focus",
                "sesja nauki",
            }

        if action == "break_start":
            if getattr(parser_result, "data", {}).get("minutes") is not None:
                return True
            if any(re.search(pattern, normalized_text) for pattern in EXPLICIT_BREAK_PATTERNS):
                return True
            if conversation_topics:
                return False
            return normalized_text in {
                "break",
                "break mode",
                "przerwa",
                "tryb przerwy",
            }

        return action in DIRECT_ACTIONS


__all__ = ["CompanionRouterExplicitActionMixin"]