from __future__ import annotations

from .base import BaseSkillExecutor
from .models import ExecutorOutcome


class ReminderSkillExecutor(BaseSkillExecutor):
    def list_items(self) -> ExecutorOutcome:
        list_method = self.first_callable(self.assistant.reminders, "list_all", "all", "items", "list")
        if list_method is None:
            return ExecutorOutcome(ok=False, status="unavailable")
        try:
            result = list_method()
        except Exception as error:
            return ExecutorOutcome(ok=False, status="list_failed", message=str(error))
        items = list(result or []) if isinstance(result, list) else []
        pending_count = len([item for item in items if str(item.get("status", "pending")) == "pending"])
        return ExecutorOutcome(
            ok=True,
            status="listed",
            data={"items": items, "count": len(items), "pending_count": pending_count},
            metadata={"source": "reminder_service.list"},
        )

    def create(self, *, seconds: int | None, message: str | None, language: str) -> ExecutorOutcome:
        normalized_message = str(message or "").strip()
        if seconds is None or not normalized_message:
            return ExecutorOutcome(ok=False, status="missing_fields")

        add_method = self.first_callable(
            self.assistant.reminders,
            "add_after_seconds",
            "add_in_seconds",
            "create_after_seconds",
        )
        if add_method is None:
            return ExecutorOutcome(ok=False, status="unavailable")

        reminder = add_method(seconds=int(seconds), message=normalized_message, language=language)
        reminder_id = str(reminder.get("id", "")).strip() if isinstance(reminder, dict) else ""
        return ExecutorOutcome(
            ok=True,
            status="created",
            data={"seconds": int(seconds), "message": normalized_message, "reminder_id": reminder_id},
            metadata={"source": "reminder_service.create"},
        )

    def resolve_delete_target(self, *, reminder_id: str | None, message: str | None) -> ExecutorOutcome:
        normalized_id = str(reminder_id or "").strip()
        normalized_message = str(message or "").strip()
        target_id = ""
        target_message = ""

        if normalized_id:
            finder = self.first_callable(self.assistant.reminders, "find_by_id")
            if callable(finder):
                found = finder(normalized_id)
                if isinstance(found, dict):
                    target_id = str(found.get("id", "")).strip() or normalized_id
                    target_message = str(found.get("message", "")).strip()
            if not target_id:
                target_id = normalized_id

        elif normalized_message:
            finder = self.first_callable(self.assistant.reminders, "find_by_message")
            if finder is None:
                finder = self.first_callable(self.assistant.reminders, "match_by_message")
            if finder is not None:
                found = finder(normalized_message)
                if isinstance(found, dict):
                    target_id = str(found.get("id", "")).strip()
                    target_message = str(found.get("message", "")).strip()
                else:
                    reminder = getattr(found, "reminder", None)
                    if isinstance(reminder, dict):
                        target_id = str(reminder.get("id", "")).strip()
                        target_message = str(reminder.get("message", "")).strip()

        if not target_id and not target_message:
            return ExecutorOutcome(ok=False, status="not_found", metadata={"source": "reminder_service.resolve_delete"})

        return ExecutorOutcome(
            ok=True,
            status="delete_target_resolved",
            data={
                "reminder_id": target_id,
                "message": target_message or normalized_message or target_id,
            },
            metadata={"source": "reminder_service.resolve_delete"},
        )


__all__ = ["ReminderSkillExecutor"]