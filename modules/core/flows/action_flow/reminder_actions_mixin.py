from __future__ import annotations

from typing import Any

from modules.runtime.contracts import RouteDecision, RouteKind

from .models import ResolvedAction


class ActionReminderActionsMixin:
    def _handle_reminders_list(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route, payload
        items = self._reminder_items()
        pending_count = len([item for item in items if str(item.get("status", "pending")) == "pending"])

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
                extra_metadata={"resolved_source": resolved.source, "count": 0},
            )

        lines = [
            self._localized(language, f"razem: {len(items)}", f"total: {len(items)}"),
            self._localized(language, f"oczekuje: {pending_count}", f"pending: {pending_count}"),
        ]
        for reminder in items[:2]:
            lines.append(self._trim_text(str(reminder.get("message", "")), 22))

        spoken = self._localized(
            language,
            f"Mam zapisane {len(items)} przypomnień. Oczekujących jest {pending_count}.",
            f"I have {len(items)} saved reminders. {pending_count} are still pending.",
        )
        return self._deliver_simple_action_response(
            language=language,
            action="reminders_list",
            spoken_text=spoken,
            display_title="REMINDERS",
            display_lines=lines[:4],
            extra_metadata={
                "resolved_source": resolved.source,
                "count": len(items),
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
        return self.assistant.deliver_text_response(
            spoken,
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="action_reminders_clear_confirmation",
            metadata={"resolved_source": resolved.source, "follow_up_type": "confirm_reminders_clear"},
        )

    def _handle_reminder_create(
        self,
        *,
        route: RouteDecision,
        language: str,
        payload: dict[str, Any],
        resolved: ResolvedAction,
    ) -> bool:
        del route
        seconds = self._resolve_reminder_seconds(payload)
        message = self._first_present(payload, "message", "content", "text", "value")

        if seconds is None or not message:
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
                extra_metadata={"resolved_source": resolved.source, "phase": "missing_fields"},
            )

        add_method = self._first_callable(
            self.assistant.reminders,
            "add_after_seconds",
            "add_in_seconds",
            "create_after_seconds",
        )
        if add_method is None:
            return self._deliver_feature_unavailable(language=language, action="reminder_create")

        reminder = add_method(seconds=int(seconds), message=str(message), language=language)
        reminder_id = str(reminder.get("id", "")).strip() if isinstance(reminder, dict) else ""

        spoken = self._localized(
            language,
            f"Dobrze. Ustawiłam przypomnienie za {self._duration_text(int(seconds), language)}.",
            f"Okay. I set a reminder for {self._duration_text(int(seconds), language)}.",
        )

        lines = [
            self._trim_text(str(message), 22),
            self._localized(
                language,
                f"za {self._duration_text(int(seconds), language)}",
                f"in {self._duration_text(int(seconds), language)}",
            ),
        ]
        if reminder_id:
            lines.append(reminder_id)

        return self._deliver_simple_action_response(
            language=language,
            action="reminder_create",
            spoken_text=spoken,
            display_title="REMINDER SAVED",
            display_lines=lines[:3],
            extra_metadata={
                "resolved_source": resolved.source,
                "seconds": int(seconds),
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
    ) -> bool:
        del route

        reminder_id = self._first_present(payload, "id", "reminder_id")
        message = self._first_present(payload, "message", "query", "content", "text")

        target_id = ""
        target_message = ""

        if reminder_id:
            finder = self._first_callable(self.assistant.reminders, "find_by_id")
            if callable(finder):
                found = finder(str(reminder_id))
                if isinstance(found, dict):
                    target_id = str(found.get("id", "")).strip() or str(reminder_id)
                    target_message = str(found.get("message", "")).strip()
            if not target_id:
                target_id = str(reminder_id)

        elif message:
            finder = self._first_callable(self.assistant.reminders, "find_by_message")
            if finder is None:
                finder = self._first_callable(self.assistant.reminders, "match_by_message")
            if finder is not None:
                found = finder(str(message))
                if isinstance(found, dict):
                    target_id = str(found.get("id", "")).strip()
                    target_message = str(found.get("message", "")).strip()
                else:
                    reminder = getattr(found, "reminder", None)
                    if isinstance(reminder, dict):
                        target_id = str(reminder.get("id", "")).strip()
                        target_message = str(reminder.get("message", "")).strip()

        if not target_id and not target_message:
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
                extra_metadata={"resolved_source": resolved.source, "phase": "not_found"},
            )

        self.assistant.pending_follow_up = {
            "type": "confirm_reminder_delete",
            "language": language,
            "reminder_id": target_id,
            "message": target_message or message or target_id,
        }

        spoken = self._localized(
            language,
            "Czy na pewno chcesz usunąć to przypomnienie?",
            "Are you sure you want to delete this reminder?",
        )
        return self.assistant.deliver_text_response(
            spoken,
            language=language,
            route_kind=RouteKind.CONVERSATION,
            source="action_reminder_delete_confirmation",
            metadata={
                "resolved_source": resolved.source,
                "follow_up_type": "confirm_reminder_delete",
                "reminder_id": target_id,
            },
        )