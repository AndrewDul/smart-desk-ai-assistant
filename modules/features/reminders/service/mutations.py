from __future__ import annotations

import copy
import uuid
from datetime import datetime, timedelta
from typing import Any

from modules.shared.logging.logger import append_log

from .models import ReminderMatch


class ReminderServiceMutations:
    """Write and state-change operations for reminders."""

    def add_after_seconds(
        self,
        *,
        seconds: int,
        message: str,
        language: str | None = None,
    ) -> dict[str, Any]:
        safe_seconds = max(1, int(seconds))
        clean_message = self._clean_message(message)
        reminder_language = self._normalize_language(language)
        now = datetime.now()

        reminder = {
            "id": str(uuid.uuid4())[:8],
            "message": clean_message,
            "language": reminder_language,
            "created_at": now.isoformat(),
            "due_at": (now + timedelta(seconds=safe_seconds)).isoformat(),
            "status": "pending",
            "acknowledged": False,
            "delivered_count": 0,
        }

        reminders = self._load_reminders()
        reminders.append(reminder)
        self._save_reminders(reminders)

        append_log(
            "Reminder added: "
            f"id={reminder['id']}, seconds={safe_seconds}, language={reminder_language}, message={clean_message}"
        )
        return copy.deepcopy(reminder)

    def check_due_reminders(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        reminders = self._load_reminders()
        due_reminders: list[dict[str, Any]] = []
        changed = False
        now = datetime.now()
        safe_limit = max(1, int(limit)) if limit is not None else None

        for reminder in reminders:
            if reminder.get("status") != "pending":
                continue

            due_at_raw = reminder.get("due_at")
            if not due_at_raw:
                continue

            try:
                due_time = datetime.fromisoformat(str(due_at_raw))
            except ValueError:
                append_log(f"Reminder skipped due to invalid due_at: {reminder}")
                continue

            if now >= due_time:
                reminder["status"] = "done"
                reminder["triggered_at"] = now.isoformat()
                reminder["acknowledged"] = False
                reminder["delivered_count"] = int(reminder.get("delivered_count", 0)) + 1
                due_reminders.append(copy.deepcopy(reminder))
                changed = True

                if safe_limit is not None and len(due_reminders) >= safe_limit:
                    break

        if changed:
            self._save_reminders(reminders)

        return due_reminders

    def mark_done(self, reminder_id: str) -> bool:
        reminders = self._load_reminders()
        changed = False

        for reminder in reminders:
            if reminder.get("id") == reminder_id and reminder.get("status") != "done":
                reminder["status"] = "done"
                reminder["triggered_at"] = datetime.now().isoformat()
                reminder["acknowledged"] = False
                reminder["delivered_count"] = int(reminder.get("delivered_count", 0)) + 1
                changed = True
                break

        if changed:
            self._save_reminders(reminders)
            append_log(f"Reminder marked done manually: id={reminder_id}")

        return changed

    def mark_acknowledged(self, reminder_id: str) -> bool:
        reminders = self._load_reminders()
        changed = False

        for reminder in reminders:
            if reminder.get("id") != reminder_id:
                continue

            if not bool(reminder.get("acknowledged", False)):
                reminder["acknowledged"] = True
                reminder["acknowledged_at"] = datetime.now().isoformat()
                changed = True
            break

        if changed:
            self._save_reminders(reminders)
            append_log(f"Reminder acknowledged: id={reminder_id}")

        return changed

    def delete(self, reminder_id: str) -> bool:
        reminders = self._load_reminders()
        new_reminders = [item for item in reminders if item.get("id") != reminder_id]

        if len(new_reminders) == len(reminders):
            return False

        self._save_reminders(new_reminders)
        append_log(f"Reminder deleted: id={reminder_id}")
        return True

    def delete_by_message(self, query: str) -> tuple[str | None, str | None]:
        reminders = self._load_reminders()
        if not reminders:
            return None, None

        matched = self.find_by_message(query)
        if matched is None:
            return None, None

        matched_id = str(matched["id"])
        matched_message = str(matched["message"])

        new_reminders = [item for item in reminders if item.get("id") != matched_id]
        self._save_reminders(new_reminders)

        append_log(f"Reminder deleted by message: id={matched_id}, message={matched_message}")
        return matched_id, matched_message

    def clear(self) -> int:
        reminders = self._load_reminders()
        count = len(reminders)
        self._save_reminders([])
        append_log(f"All reminders cleared: removed {count} item(s).")
        return count

    def clear_all(self) -> int:
        return self.clear()

    def delete_all(self) -> int:
        return self.clear()

    def clear_done(self) -> int:
        reminders = self._load_reminders()
        kept = [item for item in reminders if item.get("status") != "done"]
        removed = len(reminders) - len(kept)

        if removed > 0:
            self._save_reminders(kept)
            append_log(f"Completed reminders cleared: removed {removed} item(s).")

        return removed


__all__ = ["ReminderServiceMutations"]