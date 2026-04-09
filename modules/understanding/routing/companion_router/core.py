from __future__ import annotations

from typing import Any

from .conversation_heuristics_mixin import CompanionRouterConversationHeuristicsMixin
from .explicit_action_mixin import CompanionRouterExplicitActionMixin
from .intent_projection_mixin import CompanionRouterIntentProjectionMixin
from .language_mixin import CompanionRouterLanguageMixin
from .route_mixin import CompanionRouterRouteMixin
from .tool_invocations_mixin import CompanionRouterToolInvocationsMixin
from .topic_detection_mixin import CompanionRouterTopicDetectionMixin


class SemanticCompanionRouter(
    CompanionRouterLanguageMixin,
    CompanionRouterTopicDetectionMixin,
    CompanionRouterExplicitActionMixin,
    CompanionRouterIntentProjectionMixin,
    CompanionRouterToolInvocationsMixin,
    CompanionRouterConversationHeuristicsMixin,
    CompanionRouterRouteMixin,
):
    """
    Final semantic companion router for NeXa.

    Responsibilities:
    - reuse the deterministic IntentParser for explicit commands
    - detect conversational / supportive / playful requests
    - distinguish between action, conversation, mixed, and unclear
    - emit modern RouteDecision objects for the new assistant core

    Design rule:
    conversational suggestions become non-immediate tool suggestions.
    They must never silently execute on their own.
    """

    def __init__(self, parser: Any) -> None:
        self.parser = parser


__all__ = ["SemanticCompanionRouter"]