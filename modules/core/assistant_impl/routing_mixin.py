from __future__ import annotations

from typing import Any

from modules.runtime.contracts import (
    EntityValue,
    InputSource,
    IntentMatch,
    RouteDecision,
    RouteKind,
    ToolInvocation,
    create_turn_id,
    normalize_text,
)


class CoreAssistantRoutingMixin:
    """
    Stable routing adapter for the premium assistant core.

    Responsibilities:
    - delegate command preparation to CommandFlowOrchestrator
    - delegate pending-state handling to PendingFlowOrchestrator
    - delegate deterministic commands to FastCommandLane
    - delegate semantic routing to the configured router backend
    - normalize legacy route-like payloads into RouteDecision
    - keep assistant interaction code independent from flow internals
    """

    def _prepare_command(
        self,
        text: str,
        *,
        source: InputSource | str = InputSource.VOICE,
        capture_phase: str = "",
        capture_mode: str = "",
        capture_backend: str = "",
        capture_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        prepared = self.command_flow.prepare(
            text=text,
            fallback_language=getattr(self, "last_language", "en"),
            source=self._coerce_input_source(source),
            capture_phase=capture_phase,
            capture_mode=capture_mode,
            capture_backend=capture_backend,
            capture_metadata=dict(capture_metadata or {}),
        ).to_dict()
        prepared["already_remembered"] = True
        return prepared

    def _handle_pending_state(self, prepared: dict[str, Any]) -> bool | None:
        return self.pending_flow.process(
            prepared=dict(prepared or {}),
            language=self._normalize_lang(prepared.get("language")),
        )

    def _handle_fast_lane(self, prepared: dict[str, Any]) -> bool | None:
        return self.fast_command_lane.try_handle(
            prepared=dict(prepared or {}),
            assistant=self,
        )

    def _route_command(
        self,
        text: str,
        *,
        preferred_language: str,
        context: dict[str, Any] | None = None,
    ) -> Any:
        router = getattr(self, "router", None)
        if router is None:
            return None

        for method_name in ("route", "decide", "classify"):
            method = getattr(router, method_name, None)
            if not callable(method):
                continue

            try:
                return method(
                    text,
                    preferred_language=preferred_language,
                    context=context,
                )
            except TypeError:
                try:
                    return method(text, preferred_language)
                except TypeError:
                    return method(text)

        return None

    def _coerce_route_decision(
        self,
        routed: Any,
        *,
        raw_text: str,
        normalized_text: str,
        language: str,
        context: dict[str, Any] | None = None,
    ) -> RouteDecision:
        route_context = self._normalize_route_context(context)
        fallback_raw_text = str(raw_text or "").strip()
        fallback_normalized_text = str(normalized_text or normalize_text(fallback_raw_text)).strip()
        fallback_language = self._normalize_lang(language)

        if isinstance(routed, RouteDecision):
            merged_metadata = {
                **route_context,
                **dict(routed.metadata or {}),
            }
            return RouteDecision(
                turn_id=str(routed.turn_id or create_turn_id()).strip() or create_turn_id(),
                raw_text=str(routed.raw_text or fallback_raw_text),
                normalized_text=str(routed.normalized_text or fallback_normalized_text),
                language=self._normalize_lang(routed.language or fallback_language),
                kind=self._coerce_route_kind(routed.kind),
                confidence=float(routed.confidence or 0.0),
                primary_intent=str(routed.primary_intent or "unknown"),
                intents=list(routed.intents or []),
                conversation_topics=list(routed.conversation_topics or []),
                tool_invocations=list(routed.tool_invocations or []),
                notes=list(routed.notes or []),
                metadata=merged_metadata,
            )

        if routed is None:
            return self._build_unclear_route(
                raw_text=fallback_raw_text,
                normalized_text=fallback_normalized_text,
                language=fallback_language,
                context=route_context,
                notes=["router_returned_none"],
            )

        if isinstance(routed, dict):
            metadata = {
                **route_context,
                **dict(routed.get("metadata", {}) or {}),
            }
            intents = self._coerce_intent_matches(routed.get("intents"))
            tool_invocations = self._coerce_tool_invocations(routed.get("tool_invocations"))
            conversation_topics = self._coerce_topics(routed.get("conversation_topics") or routed.get("topics"))
            return RouteDecision(
                turn_id=str(routed.get("turn_id") or create_turn_id()).strip() or create_turn_id(),
                raw_text=str(routed.get("raw_text") or fallback_raw_text),
                normalized_text=str(routed.get("normalized_text") or fallback_normalized_text),
                language=self._normalize_lang(routed.get("language") or fallback_language),
                kind=self._coerce_route_kind(routed.get("kind") or routed.get("route_kind")),
                confidence=self._safe_float(routed.get("confidence"), default=0.0),
                primary_intent=str(routed.get("primary_intent") or routed.get("intent") or "unknown"),
                intents=intents,
                conversation_topics=conversation_topics,
                tool_invocations=tool_invocations,
                notes=self._coerce_notes(routed.get("notes")),
                metadata=metadata,
            )

        return self._build_unclear_route(
            raw_text=fallback_raw_text,
            normalized_text=fallback_normalized_text,
            language=fallback_language,
            context=route_context,
            notes=[f"unsupported_route_payload:{type(routed).__name__}"],
        )

    def _execute_action_route(self, route: RouteDecision, language: str) -> bool:
        return bool(self.action_flow.execute(route=route, language=language))

    def _handle_conversation_route(self, route: RouteDecision, language: str) -> bool:
        return bool(self.dialogue_flow.handle_conversation_route(route=route, language=language))

    def _handle_mixed_route(self, route: RouteDecision, language: str) -> bool:
        return bool(self.dialogue_flow.handle_mixed_route(route=route, language=language))

    def _handle_unclear_route(self, route: RouteDecision, language: str) -> bool:
        return bool(self.dialogue_flow.handle_unclear_route(route=route, language=language))

    @staticmethod
    def _coerce_input_source(source: InputSource | str) -> InputSource:
        if isinstance(source, InputSource):
            return source

        normalized = str(source or "").strip().lower()
        for item in InputSource:
            if item.value == normalized:
                return item
        return InputSource.VOICE

    @staticmethod
    def _coerce_route_kind(value: RouteKind | str | None) -> RouteKind:
        if isinstance(value, RouteKind):
            return value

        normalized = str(value or "").strip().lower()
        for item in RouteKind:
            if item.value == normalized:
                return item
        return RouteKind.UNCLEAR

    @staticmethod
    def _normalize_route_context(context: dict[str, Any] | None) -> dict[str, str]:
        raw = dict(context or {})
        return {
            "input_source": str(raw.get("input_source", "voice") or "voice").strip().lower() or "voice",
            "capture_phase": str(raw.get("capture_phase", "") or "").strip(),
            "capture_mode": str(raw.get("capture_mode", "") or "").strip(),
            "capture_backend": str(raw.get("capture_backend", "") or "").strip(),
        }

    def _build_unclear_route(
        self,
        *,
        raw_text: str,
        normalized_text: str,
        language: str,
        context: dict[str, str],
        notes: list[str],
    ) -> RouteDecision:
        return RouteDecision(
            turn_id=create_turn_id(),
            raw_text=raw_text,
            normalized_text=normalized_text,
            language=language,
            kind=RouteKind.UNCLEAR,
            confidence=0.0,
            primary_intent="unclear",
            intents=[],
            conversation_topics=[],
            tool_invocations=[],
            notes=list(notes),
            metadata=dict(context),
        )

    @staticmethod
    def _coerce_notes(raw_notes: Any) -> list[str]:
        if raw_notes is None:
            return []
        if isinstance(raw_notes, (list, tuple, set)):
            return [str(item) for item in raw_notes if str(item).strip()]
        note = str(raw_notes).strip()
        return [note] if note else []

    @staticmethod
    def _coerce_topics(raw_topics: Any) -> list[str]:
        if raw_topics is None:
            return []
        if isinstance(raw_topics, (list, tuple, set)):
            return [str(item) for item in raw_topics if str(item).strip()]
        topic = str(raw_topics).strip()
        return [topic] if topic else []

    def _coerce_intent_matches(self, raw_intents: Any) -> list[IntentMatch]:
        items = raw_intents if isinstance(raw_intents, (list, tuple)) else []
        matches: list[IntentMatch] = []

        for item in items:
            if isinstance(item, IntentMatch):
                matches.append(item)
                continue
            if not isinstance(item, dict):
                continue

            matches.append(
                IntentMatch(
                    name=str(item.get("name") or item.get("intent") or "unknown"),
                    confidence=self._safe_float(item.get("confidence"), default=0.0),
                    entities=self._coerce_entities(item.get("entities")),
                    requires_clarification=bool(item.get("requires_clarification", False)),
                    metadata=dict(item.get("metadata", {}) or {}),
                )
            )

        return matches

    def _coerce_entities(self, raw_entities: Any) -> list[EntityValue]:
        items = raw_entities if isinstance(raw_entities, (list, tuple)) else []
        entities: list[EntityValue] = []

        for item in items:
            if isinstance(item, EntityValue):
                entities.append(item)
                continue
            if not isinstance(item, dict):
                continue
            entities.append(
                EntityValue(
                    name=str(item.get("name") or ""),
                    value=item.get("value"),
                    confidence=self._safe_float(item.get("confidence"), default=1.0),
                    source_text=str(item.get("source_text") or ""),
                )
            )

        return entities

    def _coerce_tool_invocations(self, raw_tools: Any) -> list[ToolInvocation]:
        items = raw_tools if isinstance(raw_tools, (list, tuple)) else []
        invocations: list[ToolInvocation] = []

        for item in items:
            if isinstance(item, ToolInvocation):
                invocations.append(item)
                continue
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("tool_name") or item.get("name") or "").strip()
            if not tool_name:
                continue
            invocations.append(
                ToolInvocation(
                    tool_name=tool_name,
                    payload=dict(item.get("payload", {}) or {}),
                    reason=str(item.get("reason") or ""),
                    confidence=self._safe_float(item.get("confidence"), default=1.0),
                    execute_immediately=bool(item.get("execute_immediately", True)),
                )
            )

        return invocations

    @staticmethod
    def _safe_float(value: Any, *, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)


__all__ = ["CoreAssistantRoutingMixin"]