from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision, RouteKind

from .models import ResolvedAction, SkillRequest


class ActionReminderActionsMixin:
    def _handle_reminders_list(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route, payload
        outcome = self._get_reminder_skill_executor().list_items()
        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="reminders_list")

        items = list(outcome.data.get("items", []) or [])
        pending_count = int(outcome.data.get("pending_count", 0) or 0)
        count = int(outcome.data.get("count", len(items)) or 0)
        spec = self._get_reminder_response_builder().build_list_response(
            language=language,
            action=request.action if request is not None else "reminders_list",
            resolved_source=resolved.source,
            items=items,
            count=count,
            pending_count=pending_count,
            metadata=dict(outcome.metadata or {}),
        )
        return self._deliver_action_response_spec(language=language, spec=spec)

    def _handle_reminders_clear(
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
            "type": "confirm_reminders_clear",
            "language": language,
        }
        spec = self._get_reminder_response_builder().build_clear_confirmation(
            language=language,
            action=request.action if request is not None else "reminders_clear",
            resolved_source=resolved.source,
        )
        return self._deliver_action_follow_up_prompt_spec(language=language, spec=spec)

    def _handle_reminder_create(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route
        seconds = self._resolve_reminder_seconds(payload)
        message = self._first_present(payload, "message", "content", "text", "value")
        outcome = self._get_reminder_skill_executor().create(
            seconds=seconds,
            message=message,
            language=language,
        )

        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="reminder_create")

        reminder_id = str(outcome.data.get("reminder_id", "")).strip()
        reminder_message = str(outcome.data.get("message", message or "")).strip()
        reminder_seconds = int(outcome.data.get("seconds", seconds or 0) or 0)
        spec = self._get_reminder_response_builder().build_create_response(
            language=language,
            action=request.action if request is not None else "reminder_create",
            outcome_status=outcome.status,
            resolved_source=resolved.source,
            seconds=reminder_seconds,
            reminder_id=reminder_id,
            message=reminder_message,
            metadata=dict(outcome.metadata or {}),
        )
        return self._deliver_action_response_spec(language=language, spec=spec)

    def _handle_reminder_delete(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
        request: SkillRequest | None = None,
    ) -> bool:
        del route
        reminder_id = self._first_present(payload, "id", "reminder_id")
        message = self._first_present(payload, "message", "query", "content", "text")
        outcome = self._get_reminder_skill_executor().resolve_delete_target(
            reminder_id=reminder_id,
            message=message,
        )

        if not outcome.ok:
            spec = self._get_reminder_response_builder().build_delete_missing(
                language=language,
                action="reminder_delete",
                outcome_status=outcome.status,
                resolved_source=resolved.source,
                metadata=dict(outcome.metadata or {}),
            )
            return self._deliver_action_response_spec(language=language, spec=spec)

        target_id = str(outcome.data.get("reminder_id", "")).strip()
        target_message = str(outcome.data.get("message", message or target_id)).strip()
        self.assistant.pending_follow_up = {
            "type": "confirm_reminder_delete",
            "language": language,
            "reminder_id": target_id,
            "message": target_message,
        }

        spec = self._get_reminder_response_builder().build_delete_confirmation(
            language=language,
            action=request.action if request is not None else "reminder_delete",
            resolved_source=resolved.source,
            reminder_id=target_id,
            metadata=dict(outcome.metadata or {}),
        )
        return self._deliver_action_follow_up_prompt_spec(language=language, spec=spec)