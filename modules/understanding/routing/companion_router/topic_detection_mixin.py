from __future__ import annotations

import re

from .patterns import CONVERSATION_TOPIC_PATTERNS, TOPIC_PRIORITY


class CompanionRouterTopicDetectionMixin:
    """
    Detect conversational topics from normalized user text.
    """

    def _detect_conversation_topics(self, normalized_text: str) -> list[str]:
        found: list[str] = []

        for topic, patterns in CONVERSATION_TOPIC_PATTERNS.items():
            if any(re.search(pattern, normalized_text) for pattern in patterns):
                found.append(topic)

        if not found:
            return []

        unique = list(dict.fromkeys(found))
        unique.sort(key=lambda item: TOPIC_PRIORITY.get(item, 0), reverse=True)
        return unique


__all__ = ["CompanionRouterTopicDetectionMixin"]