from __future__ import annotations

import re

from .patterns import (
    DIRECT_CONVERSATION_CUES,
    GENERIC_KNOWLEDGE_PATTERNS,
    MATH_PATTERNS,
    QUESTION_STARTERS,
)


class CompanionRouterConversationHeuristicsMixin:
    """
    Detect whether the input looks like a general question or a direct
    conversation request.
    """

    def _looks_like_general_question(
        self,
        raw_text: str,
        normalized_text: str,
        language: str,
    ) -> bool:
        raw_lower = str(raw_text or "").strip().lower()

        if "?" in raw_text:
            return True

        starters = QUESTION_STARTERS.get(language, ())
        if any(normalized_text.startswith(starter) for starter in starters):
            return True

        if any(re.search(pattern, normalized_text) for pattern in GENERIC_KNOWLEDGE_PATTERNS):
            return True

        if any(re.search(pattern, normalized_text) for pattern in MATH_PATTERNS):
            return True

        if raw_lower.startswith(("explain ", "wyjasnij ", "wyjaśnij ", "wytlumacz ", "wytłumacz ")):
            return True

        return False

    def _looks_like_conversation_request(self, normalized_text: str, language: str) -> bool:
        cues = DIRECT_CONVERSATION_CUES.get(language, set())
        return normalized_text in cues


__all__ = ["CompanionRouterConversationHeuristicsMixin"]