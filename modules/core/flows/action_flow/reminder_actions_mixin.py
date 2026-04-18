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
        if not items:
            return self._deliver_simple_action_response(
                language=language,
                action="reminders_list",
                spoken_text=self._localized(
                    language,
                    "Nie mam zapisanych przypomnień.",
                    "I do not have any saved reminders.",
                ),
                display_title="REMINDERS",
                display_lines=self._localized_lines(language, ["brak przypomnien"], ["no reminders"]),
                extra_metadata={
                    **dict(outcome.metadata or {}),
                    "resolved_source": resolved.source,
                    "count": 0,
                },
            )

        lines = [
            self._localized(language, f"razem: {count}", f"total: {count}"),
            self._localized(language, f"oczekuje: {pending_count}", f"pending: {pending_count}"),
        ]
        for reminder in items[:2]:
            lines.append(self._trim_text(str(reminder.get("message", "")), 22))

        spoken = self._localized(
            language,
            f"Mam zapisane {count} przypomnień. Oczekujących jest {pending_count}.",
            f"I have {count} saved reminders. {pending_count} are still pending.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action=request.action if request is not None else "reminders_list",
            spoken_text=spoken,
            display_title="REMINDERS",
            display_lines=lines[:4],
            extra_metadata={
                **dict(outcome.metadata or {}),
                "resolved_source": resolved.source,
                "count": count,
                "pending_count": pending_count,
            },
        )

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
        spoken = self._localized(
            language,
            "Czy na pewno chcesz usunąć wszystkie przypomnienia?",
            "Are you sure you want to delete all reminders?",
        )
        return self._deliver_action_follow_up_prompt(
            language=language,
            action=request.action if request is not None else "reminders_clear",
            spoken_text=spoken,
            source="action_reminders_clear_confirmation",
            follow_up_type="confirm_reminders_clear",
            extra_metadata={"resolved_source": resolved.source},
        )

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

        if outcome.status == "missing_fields":
            return self._deliver_simple_action_response(
                language=language,
                action="reminder_create",
                spoken_text=self._localized(
                    language,
                    "Brakuje mi czasu albo treści przypomnienia.",
                    "I am missing either the reminder time or the reminder message.",
                ),
                display_title="REMINDER",
                display_lines=self._localized_lines(
                    language,
                    ["brak czasu", "lub tresci"],
                    ["missing time", "or message"],
                ),
                extra_metadata={
                    **dict(outcome.metadata or {}),
                    "resolved_source": resolved.source,
                    "phase": "missing_fields",
                },
            )

        if outcome.status == "unavailable":
            return self._deliver_feature_unavailable(language=language, action="reminder_create")

        reminder_id = str(outcome.data.get("reminder_id", "")).strip()
        reminder_message = str(outcome.data.get("message", message or "")).strip()
        reminder_seconds = int(outcome.data.get("seconds", seconds or 0) or 0)

        spoken = self._localized(
            language,
            f"Dobrze. Ustawiłam przypomnienie za {self._duration_text(reminder_seconds, language)}.",
            f"Okay. I set a reminder for {self._duration_text(reminder_seconds, language)}.",
        )

        lines = [
            self._trim_text(reminder_message, 22),
            self._localized(
                language,
                f"za {self._duration_text(reminder_seconds, language)}",
                f"in {self._duration_text(reminder_seconds, language)}",
            ),
        ]
        if reminder_id:
            lines.append(reminder_id)

        return self._deliver_simple_action_response(
            language=language,
            action=request.action if request is not None else "reminder_create",
            spoken_text=spoken,
            display_title="REMINDER SAVED",
            display_lines=lines[:3],
            extra_metadata={
                **dict(outcome.metadata or {}),
                "resolved_source": resolved.source,
                "seconds": reminder_seconds,
                "reminder_id": reminder_id,
            },
        )

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
            return self._deliver_simple_action_response(
                language=language,
                action="reminder_delete",
                spoken_text=self._localized(
                    language,
                    "Nie mogę znaleźć takiego przypomnienia.",
                    "I cannot find that reminder.",
                ),
                display_title="REMINDERS",
                display_lines=self._localized_lines(language, ["nie znaleziono"], ["not found"]),
                extra_metadata={
                    **dict(outcome.metadata or {}),
                    "resolved_source": resolved.source,
                    "phase": outcome.status or "not_found",
                },
            )

        target_id = str(outcome.data.get("reminder_id", "")).strip()
        target_message = str(outcome.data.get("message", message or target_id)).strip()
        self.assistant.pending_follow_up = {
            "type": "confirm_reminder_delete",
            "language": language,
            "reminder_id": target_id,
            "message": target_message,
        }

        spoken = self._localized(
            language,
            "Czy na pewno chcesz usunąć to przypomnienie?",
            "Are you sure you want to delete this reminder?",
        )
        return self._deliver_action_follow_up_prompt(
            language=language,
            action=request.action if request is not None else "reminder_delete",
            spoken_text=spoken,
            source="action_reminder_delete_confirmation",
            follow_up_type="confirm_reminder_delete",
            extra_metadata={
                **dict(outcome.metadata or {}),
                "resolved_source": resolved.source,
                "reminder_id": target_id,
            },
        )