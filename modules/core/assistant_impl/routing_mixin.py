from __future__ import annotations

from typing import Any

from modules.runtime.contracts import (
    InputSource,
    IntentMatch,
    RouteDecision,
    RouteKind,
    ToolInvocation,
    create_turn_id,
    normalize_text,
)


class CoreAssistantRoutingMixin:
    def _execute_action_route(self, route: RouteDecision, language: str) -> bool:
        return bool(self.action_flow.execute(route=route, language=language))

    def _handle_mixed_route(self, route: RouteDecision, language: str) -> bool:
        handle_method = getattr(self.dialogue_flow, "handle_mixed_route", None)
        if callable(handle_method):
            return bool(handle_method(route=route, language=language))
        return bool(self.dialogue_flow.handle_mixed(route=route, language=language))

    def _handle_conversation_route(self, route: RouteDecision, language: str) -> bool:
        handle_method = getattr(self.dialogue_flow, "handle_conversation_route", None)
        if callable(handle_method):
            return bool(handle_method(route=route, language=language))
        return bool(self.dialogue_flow.handle_conversation(route=route, language=language))

    def _handle_unclear_route(self, route: RouteDecision, language: str) -> bool:
        handle_method = getattr(self.dialogue_flow, "handle_unclear_route", None)
        if callable(handle_method):
            return bool(handle_method(route=route, language=language))
        return bool(self.dialogue_flow.handle_unclear(route=route, language=language))

    def _prepare_command(self, text: str) -> dict[str, Any]:
        process_method = getattr(self.command_flow, "process", None)
        if callable(process_method):
            prepared = process_method(text=text, fallback_language=self.last_language)
            if isinstance(prepared, dict):
                prepared.setdefault("cancel_requested", self._looks_like_cancel_request(text))
                prepared.setdefault("normalized_text", normalize_text(text))
                prepared.setdefault("routing_text", text.strip())
                prepared.setdefault("language", self._detect_language(text))
                prepared.setdefault("source", InputSource.VOICE)
                prepared.setdefault("ignore", not bool(prepared["normalized_text"]))
                return prepared

            return {
                "ignore": bool(getattr(prepared, "ignore", False)),
                "language": str(getattr(prepared, "language", self.last_language)),
                "routing_text": str(getattr(prepared, "routing_text", text)),
                "normalized_text": str(getattr(prepared, "normalized_text", normalize_text(text))),
                "cancel_requested": bool(
                    getattr(prepared, "cancel_requested", self._looks_like_cancel_request(text))
                ),
                "source": getattr(prepared, "source", InputSource.VOICE),
                "already_remembered": bool(getattr(prepared, "already_remembered", False)),
            }

        normalized_text = normalize_text(text)
        language = self._detect_language(text)
        return {
            "ignore": not bool(normalized_text),
            "language": language,
            "routing_text": text.strip(),
            "normalized_text": normalized_text,
            "cancel_requested": self._looks_like_cancel_request(text),
            "source": InputSource.VOICE,
            "already_remembered": False,
        }

    def _handle_pending_state(self, prepared: dict[str, Any]) -> bool | None:
        process_method = getattr(self.pending_flow, "process", None)
        if not callable(process_method):
            return None

        return process_method(
            prepared=prepared,
            language=str(prepared.get("language", self.last_language)),
        )

    def _handle_fast_lane(self, prepared: dict[str, Any]) -> bool | None:
        if self.fast_command_lane is None:
            return None

        handle_method = getattr(self.fast_command_lane, "try_handle", None)
        if not callable(handle_method):
            return None

        return handle_method(prepared=prepared, assistant=self)

    def _coerce_route_decision(
        self,
        value: Any,
        *,
        raw_text: str,
        normalized_text: str,
        language: str,
    ) -> RouteDecision:
        if isinstance(value, RouteDecision):
            return value

        if isinstance(value, dict):
            kind_value = str(value.get("kind", RouteKind.UNCLEAR.value)).strip().lower()
            kind = self._coerce_route_kind(kind_value)

            intents: list[IntentMatch] = []
            for item in value.get("intents", []) or []:
                if isinstance(item, IntentMatch):
                    intents.append(item)

            tool_invocations: list[ToolInvocation] = []
            for item in value.get("tool_invocations", []) or []:
                if isinstance(item, ToolInvocation):
                    tool_invocations.append(item)
                elif isinstance(item, dict):
                    tool_invocations.append(
                        ToolInvocation(
                            tool_name=str(item.get("tool_name", item.get("name", ""))),
                            payload=dict(item.get("payload", {})),
                            reason=str(item.get("reason", "")),
                            confidence=float(item.get("confidence", 1.0)),
                            execute_immediately=bool(item.get("execute_immediately", True)),
                        )
                    )

            return RouteDecision(
                turn_id=str(value.get("turn_id", create_turn_id())),
                raw_text=raw_text,
                normalized_text=normalized_text,
                language=self._normalize_lang(value.get("language", language)),
                kind=kind,
                confidence=float(value.get("confidence", 0.0)),
                primary_intent=str(value.get("primary_intent", "unknown")),
                intents=intents,
                conversation_topics=list(value.get("conversation_topics", []) or []),
                tool_invocations=tool_invocations,
                notes=list(value.get("notes", []) or []),
                metadata=dict(value.get("metadata", {})),
            )

        route_kind = RouteKind.UNCLEAR
        primary_intent = "unknown"

        if isinstance(value, str):
            lowered = normalize_text(value)
            if lowered in {"action", "tool", "task"}:
                route_kind = RouteKind.ACTION
            elif lowered in {"conversation", "chat", "dialogue"}:
                route_kind = RouteKind.CONVERSATION
            elif lowered == "mixed":
                route_kind = RouteKind.MIXED
            primary_intent = lowered or "unknown"

        return RouteDecision(
            turn_id=create_turn_id(),
            raw_text=raw_text,
            normalized_text=normalized_text,
            language=self._normalize_lang(language),
            kind=route_kind,
            confidence=0.0,
            primary_intent=primary_intent,
            intents=[],
            conversation_topics=[],
            tool_invocations=[],
            notes=[],
            metadata={},
        )

    def _coerce_route_kind(self, raw_value: str) -> RouteKind:
        normalized = str(raw_value or "").strip().lower()
        for kind in RouteKind:
            if kind.value == normalized:
                return kind
        return RouteKind.UNCLEAR