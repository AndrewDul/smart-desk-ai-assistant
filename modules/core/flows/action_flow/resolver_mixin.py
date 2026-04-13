from __future__ import annotations

from typing import Any

from modules.runtime.contracts import EntityValue, IntentMatch, RouteDecision, ToolInvocation

from .models import ResolvedAction


class ActionResolverMixin:
    def _build_resolved_action(
        self,
        *,
        route: RouteDecision,
        name: str,
        payload: dict[str, Any],
        source: str,
        confidence: float,
    ) -> ResolvedAction:
        return ResolvedAction(
            name=name,
            payload=dict(payload or {}),
            source=source,
            confidence=float(confidence),
            route_kind=getattr(route.kind, "value", str(route.kind)),
            primary_intent=str(route.primary_intent or "").strip(),
            route_notes=tuple(route.notes or ()),
            route_metadata=dict(route.metadata or {}),
        )

    def _resolve_action(self, route: RouteDecision) -> ResolvedAction:
        tool_match = self._resolve_from_tools(route, route.tool_invocations)
        if tool_match is not None:
            return tool_match

        primary_match = self._resolve_from_primary_intent(route)
        if primary_match is not None:
            return primary_match

        intent_match = self._resolve_from_intents(route, route.intents)
        if intent_match is not None:
            return intent_match

        metadata_action = str(route.metadata.get("action", "")).strip().lower()
        if metadata_action in self.SUPPORTED_ACTIONS:
            return self._build_resolved_action(
                route=route,
                name=metadata_action,
                payload=dict(route.metadata.get("payload", {}) or {}),
                source="route.metadata.action",
                confidence=float(route.confidence),
            )

        return self._build_resolved_action(
            route=route,
            name="unknown",
            payload={},
            source="fallback",
            confidence=float(route.confidence),
        )

    def _resolve_from_tools(
        self,
        route: RouteDecision,
        tools: list[ToolInvocation],
    ) -> ResolvedAction | None:
        for tool in tools:
            action_name = self.TOOL_TO_ACTION.get(str(tool.tool_name or "").strip().lower())
            if not action_name:
                continue
            return self._build_resolved_action(
                route=route,
                name=action_name,
                payload=dict(tool.payload or {}),
                source=f"tool:{tool.tool_name}",
                confidence=float(tool.confidence),
            )
        return None

    def _resolve_from_primary_intent(self, route: RouteDecision) -> ResolvedAction | None:
        primary = str(route.primary_intent or "").strip().lower()
        if primary not in self.SUPPORTED_ACTIONS:
            return None

        payload = self._payload_from_matching_intent(route.intents, primary)
        if not payload:
            payload = dict(route.metadata.get("payload", {}) or {})

        return self._build_resolved_action(
            route=route,
            name=primary,
            payload=payload,
            source="route.primary_intent",
            confidence=float(route.confidence),
        )

    def _resolve_from_intents(
        self,
        route: RouteDecision,
        intents: list[IntentMatch],
    ) -> ResolvedAction | None:
        for item in intents:
            intent_name = str(item.name or "").strip().lower()
            if intent_name not in self.SUPPORTED_ACTIONS:
                continue
            return self._build_resolved_action(
                route=route,
                name=intent_name,
                payload=self._payload_from_entities(item.entities),
                source=f"intent:{intent_name}",
                confidence=float(item.confidence),
            )
        return None

    def _payload_from_matching_intent(
        self,
        intents: list[IntentMatch],
        intent_name: str,
    ) -> dict[str, Any]:
        target = str(intent_name or "").strip().lower()
        for item in intents:
            if str(item.name or "").strip().lower() == target:
                return self._payload_from_entities(item.entities)
        return {}

    @staticmethod
    def _payload_from_entities(entities: list[EntityValue]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for entity in entities:
            if entity.name:
                payload[str(entity.name)] = entity.value
        return payload