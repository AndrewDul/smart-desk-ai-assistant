from __future__ import annotations

from typing import Any

from modules.runtime.contracts import EntityValue, IntentMatch


class CompanionRouterIntentProjectionMixin:
    """
    Project parser output and conversation topics into intent matches.
    """

    def _build_intent_matches(
        self,
        parser_result: Any,
        conversation_topics: list[str],
    ) -> list[IntentMatch]:
        matches: list[IntentMatch] = []

        action = str(getattr(parser_result, "action", "") or "").strip()
        if action and action not in {"unknown", "unclear"}:
            matches.append(
                IntentMatch(
                    name=action,
                    confidence=float(getattr(parser_result, "confidence", 1.0) or 1.0),
                    entities=self._entities_from_parser_data(
                        getattr(parser_result, "data", {}) or {}
                    ),
                    requires_clarification=bool(
                        getattr(parser_result, "needs_confirmation", False)
                    ),
                    metadata={
                        "source": "intent_parser",
                        "normalized_text": str(
                            getattr(parser_result, "normalized_text", "") or ""
                        ),
                        "suggestions": list(
                            getattr(parser_result, "suggestions", []) or []
                        ),
                    },
                )
            )

        for topic in conversation_topics:
            matches.append(
                IntentMatch(
                    name=topic,
                    confidence=0.72,
                    entities=[],
                    requires_clarification=False,
                    metadata={"source": "semantic_topic_match"},
                )
            )

        return matches

    @staticmethod
    def _entities_from_parser_data(data: dict[str, Any]) -> list[EntityValue]:
        entities: list[EntityValue] = []
        for key, value in (data or {}).items():
            if value in ("", None):
                continue
            entities.append(
                EntityValue(
                    name=str(key),
                    value=value,
                    confidence=1.0,
                    source_text=str(value),
                )
            )
        return entities


__all__ = ["CompanionRouterIntentProjectionMixin"]