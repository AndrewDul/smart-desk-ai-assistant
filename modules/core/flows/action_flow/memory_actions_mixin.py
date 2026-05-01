from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision, RouteKind

from .models import ResolvedAction, SkillRequest


class ActionMemoryActionsMixin:
    def _handle_memory_store(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route, resolved

        guided = bool(payload.get("guided", False))
        memory_text = self._first_present(payload, "memory_text", "message", "content", "text")
        key, value = self._resolve_memory_store_fields(payload)

        if guided or (not str(memory_text or "").strip() and (not key or not value)):
            self.assistant.pending_follow_up = {
                "type": "memory_message",
                "language": language,
            }
            return self.assistant.deliver_text_response(
                self.assistant._localized(
                    language,
                    "Jasne. Co mam zapamiętać?",
                    "Sure. What should I remember?",
                ),
                language=language,
                route_kind=RouteKind.CONVERSATION,
                source="action_memory_guided_message_prompt",
                metadata={
                    "follow_up_type": "memory_message",
                    "action": "memory_store",
                },
            )

        if str(memory_text or "").strip():
            outcome = self._get_memory_skill_executor().store_text(
                text=memory_text,
                language=language,
                source="memory_service.store_text",
            )
        else:
            outcome = self._get_memory_skill_executor().store(
                key=key,
                value=value,
                language=language,
            )

        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="memory_store")

        spec = self._get_memory_response_builder().build_store_response(
            language=language,
            action=request.action if request is not None else "memory_store",
            outcome_status=outcome.status,
            resolved_source="action_memory_store",
            key=str(outcome.data.get("key", key or "")).strip(),
            value=str(outcome.data.get("value", value or "")).strip(),
            metadata=dict(outcome.metadata or {}),
        )
        return self._deliver_action_response_spec(language=language, spec=spec)

    def _handle_memory_recall(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route
        key = self._first_present(payload, "key", "subject", "item", "name", "query")
        outcome = self._get_memory_skill_executor().recall(key=key, language=language)

        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="memory_recall")

        found_key = str(outcome.data.get("key", key or "")).strip()
        found_value = str(outcome.data.get("value", "")).strip()
        spec = self._get_memory_response_builder().build_recall_response(
            language=language,
            action=request.action if request is not None else "memory_recall",
            outcome_status=outcome.status,
            resolved_source=resolved.source,
            key=found_key,
            value=found_value,
            metadata=dict(outcome.metadata or {}),
        )
        return self._deliver_action_response_spec(language=language, spec=spec)

    def _handle_memory_forget(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route
        key = self._first_present(payload, "key", "subject", "item", "name", "query")
        outcome = self._get_memory_skill_executor().forget(key=key, language=language)

        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="memory_forget")

        removed_key = str(outcome.data.get("key", key or "")).strip()
        spec = self._get_memory_response_builder().build_forget_response(
            language=language,
            action=request.action if request is not None else "memory_forget",
            outcome_status=outcome.status,
            resolved_source=resolved.source,
            key=removed_key,
            metadata=dict(outcome.metadata or {}),
        )
        return self._deliver_action_response_spec(language=language, spec=spec)

    def _handle_memory_list(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route, payload
        outcome = self._get_memory_skill_executor().list_items(language=language)
        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="memory_list")

        items = dict(outcome.data.get("items", {}) or {})
        count = int(outcome.data.get("count", len(items)) or 0)
        spec = self._get_memory_response_builder().build_list_response(
            language=language,
            action=request.action if request is not None else "memory_list",
            resolved_source=resolved.source,
            items=items,
            count=count,
            metadata=dict(outcome.metadata or {}),
        )
        return self._deliver_action_response_spec(language=language, spec=spec)

    def _handle_memory_clear(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route, payload
        self.assistant.pending_follow_up = {
            "type": "confirm_memory_clear",
            "language": language,
        }
        spec = self._get_memory_response_builder().build_clear_confirmation(
            language=language,
            action=request.action if request is not None else "memory_clear",
            resolved_source=resolved.source,
        )
        return self._deliver_action_follow_up_prompt_spec(language=language, spec=spec)

    @staticmethod
    def _route_kind_conversation():
        from modules.runtime.contracts import RouteKind

        return RouteKind.CONVERSATION