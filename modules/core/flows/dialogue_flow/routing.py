from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision, RouteKind, ToolInvocation

from .models import DialogueRouteBridge


class DialogueFlowRouting:
    """Route adaptation helpers for dialogue flow."""

    def _build_dialogue_route_bridge(
        self,
        route: RouteDecision,
        language: str,
    ) -> DialogueRouteBridge:
        suggested_actions = self._suggested_action_names(route)
        action_result = None

        immediate_invocations = self._immediate_tool_invocations(route)
        if immediate_invocations:
            action_result = self._payload_from_invocation(
                immediate_invocations[0],
                route.normalized_text,
            )

        return DialogueRouteBridge(
            kind=route.kind.value,
            reply_mode=self._reply_mode_for_route(route),
            language=language,
            raw_text=route.raw_text,
            normalized_text=route.normalized_text,
            action_result=action_result,
            confidence=float(route.confidence),
            conversation_topics=list(route.conversation_topics),
            suggested_actions=suggested_actions,
            notes=list(route.notes),
        )

    def _reply_mode_for_route(self, route: RouteDecision) -> str:
        if route.kind == RouteKind.ACTION:
            return "execute"
        if route.kind == RouteKind.MIXED:
            return "reply_then_offer"
        if route.kind == RouteKind.CONVERSATION:
            return "reply"
        return "clarify"

    def _route_with_invocations(
        self,
        *,
        route: RouteDecision,
        invocations: list[ToolInvocation],
        force_kind: RouteKind,
    ) -> RouteDecision:
        primary = route.primary_intent
        if invocations:
            primary = self._action_name_from_tool(invocations[0].tool_name)

        return RouteDecision(
            turn_id=route.turn_id,
            raw_text=route.raw_text,
            normalized_text=route.normalized_text,
            language=route.language,
            kind=force_kind,
            confidence=route.confidence,
            primary_intent=primary,
            intents=list(route.intents),
            conversation_topics=list(route.conversation_topics),
            tool_invocations=list(invocations),
            notes=list(route.notes),
            metadata=dict(route.metadata),
        )

    def _route_memory_metadata(
        self,
        route: RouteDecision,
        language: str,
        *,
        source: str,
    ) -> dict[str, Any]:
        route_metadata = dict(route.metadata or {})
        return {
            "source": source,
            "route_kind": route.kind.value,
            "language": language,
            "topics": list(route.conversation_topics),
            "primary_intent": route.primary_intent,
            "suggested_actions": self._suggested_action_names(route),
            "notes": list(route.notes),
            "capture_phase": str(route_metadata.get("capture_phase", "") or ""),
            "capture_mode": str(route_metadata.get("capture_mode", "") or ""),
            "capture_backend": str(route_metadata.get("capture_backend", "") or ""),
            "parser_action": str(route_metadata.get("parser_action", "") or ""),
            "route_metadata": route_metadata,
        }


__all__ = ["DialogueFlowRouting"]