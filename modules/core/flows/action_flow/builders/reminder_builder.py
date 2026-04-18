from __future__ import annotations

from .base import BaseActionResponseBuilder
from .models import ActionFollowUpPromptSpec, ActionResponseSpec


class ReminderSkillResponseBuilder(BaseActionResponseBuilder):
    def build_list_response(
        self,
        *,
        language: str,
        action: str,
        resolved_source: str,
        items: list[dict],
        count: int,
        pending_count: int,
        metadata: dict | None = None,
    ) -> ActionResponseSpec:
        if not items:
            return ActionResponseSpec(
                action=action,
                spoken_text=self.localized(
                    language,
                    "Nie mam zapisanych przypomnień.",
                    "I do not have any saved reminders.",
                ),
                display_title="REMINDERS",
                display_lines=self.localized_lines(language, ["brak przypomnien"], ["no reminders"]),
                extra_metadata={
                    **dict(metadata or {}),
                    "resolved_source": resolved_source,
                    "count": 0,
                },
            )

        lines = [
            self.localized(language, f"razem: {count}", f"total: {count}"),
            self.localized(language, f"oczekuje: {pending_count}", f"pending: {pending_count}"),
        ]
        for reminder in items[:2]:
            lines.append(self.trim_text(str(reminder.get("message", "")), 22))

        return ActionResponseSpec(
            action=action,
            spoken_text=self.localized(
                language,
                f"Mam zapisane {count} przypomnień. Oczekujących jest {pending_count}.",
                f"I have {count} saved reminders. {pending_count} are still pending.",
            ),
            display_title="REMINDERS",
            display_lines=lines[:4],
            extra_metadata={
                **dict(metadata or {}),
                "resolved_source": resolved_source,
                "count": count,
                "pending_count": pending_count,
            },
        )

    def build_create_response(
        self,
        *,
        language: str,
        action: str,
        outcome_status: str,
        resolved_source: str,
        seconds: int | None,
        reminder_id: str,
        message: str,
        metadata: dict | None = None,
    ) -> ActionResponseSpec:
        if outcome_status == "missing_fields":
            return ActionResponseSpec(
                action=action,
                spoken_text=self.localized(
                    language,
                    "Brakuje mi czasu albo treści przypomnienia.",
                    "I am missing either the reminder time or the reminder message.",
                ),
                display_title="REMINDER",
                display_lines=self.localized_lines(
                    language,
                    ["brak czasu", "lub tresci"],
                    ["missing time", "or message"],
                ),
                extra_metadata={
                    **dict(metadata or {}),
                    "resolved_source": resolved_source,
                    "phase": "missing_fields",
                },
            )

        safe_seconds = int(seconds or 1)
        lines = [
            self.trim_text(message, 22),
            self.localized(
                language,
                f"za {self.duration_text(safe_seconds, language)}",
                f"in {self.duration_text(safe_seconds, language)}",
            ),
        ]
        if reminder_id:
            lines.append(reminder_id)

        return ActionResponseSpec(
            action=action,
            spoken_text=self.localized(
                language,
                f"Dobrze. Ustawiłam przypomnienie za {self.duration_text(safe_seconds, language)}.",
                f"Okay. I set a reminder for {self.duration_text(safe_seconds, language)}.",
            ),
            display_title="REMINDER SAVED",
            display_lines=lines[:3],
            extra_metadata={
                **dict(metadata or {}),
                "resolved_source": resolved_source,
                "seconds": safe_seconds,
                "reminder_id": reminder_id,
            },
        )

    def build_delete_missing(
        self,
        *,
        language: str,
        action: str,
        outcome_status: str,
        resolved_source: str,
        metadata: dict | None = None,
    ) -> ActionResponseSpec:
        return ActionResponseSpec(
            action=action,
            spoken_text=self.localized(
                language,
                "Nie mogę znaleźć takiego przypomnienia.",
                "I cannot find that reminder.",
            ),
            display_title="REMINDERS",
            display_lines=self.localized_lines(language, ["nie znaleziono"], ["not found"]),
            extra_metadata={
                **dict(metadata or {}),
                "resolved_source": resolved_source,
                "phase": outcome_status or "not_found",
            },
        )

    def build_delete_confirmation(
        self,
        *,
        language: str,
        action: str,
        resolved_source: str,
        reminder_id: str,
        metadata: dict | None = None,
    ) -> ActionFollowUpPromptSpec:
        return ActionFollowUpPromptSpec(
            action=action,
            spoken_text=self.localized(
                language,
                "Czy na pewno chcesz usunąć to przypomnienie?",
                "Are you sure you want to delete this reminder?",
            ),
            source="action_reminder_delete_confirmation",
            follow_up_type="confirm_reminder_delete",
            extra_metadata={
                **dict(metadata or {}),
                "resolved_source": resolved_source,
                "reminder_id": reminder_id,
            },
        )

    def build_clear_confirmation(
        self,
        *,
        language: str,
        action: str,
        resolved_source: str,
        metadata: dict | None = None,
    ) -> ActionFollowUpPromptSpec:
        return ActionFollowUpPromptSpec(
            action=action,
            spoken_text=self.localized(
                language,
                "Czy na pewno chcesz usunąć wszystkie przypomnienia?",
                "Are you sure you want to remove all reminders?",
            ),
            source="action_reminders_clear_confirmation",
            follow_up_type="confirm_reminders_clear",
            extra_metadata={
                **dict(metadata or {}),
                "resolved_source": resolved_source,
            },
        )


__all__ = ["ReminderSkillResponseBuilder"]