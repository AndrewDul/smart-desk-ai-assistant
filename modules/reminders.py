from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from typing import Any

from modules.utils import REMINDERS_PATH, append_log, load_json, save_json


class ReminderManager:
    def __init__(self) -> None:
        self.path = REMINDERS_PATH

    def add_after_seconds(self, seconds: int, message: str) -> dict[str, Any]:
        safe_seconds = max(1, int(seconds))
        clean_message = self._clean_message(message)

        reminders = self._load_reminders()

        reminder = {
            "id": str(uuid.uuid4())[:8],
            "message": clean_message,
            "created_at": datetime.now().isoformat(),
            "due_at": (datetime.now() + timedelta(seconds=safe_seconds)).isoformat(),
            "status": "pending",
        }

        reminders.append(reminder)
        self._save_reminders(reminders)

        append_log(
            f"Reminder added: id={reminder['id']}, seconds={safe_seconds}, message={clean_message}"
        )
        return reminder

    def list_all(self) -> list[dict[str, Any]]:
        reminders = self._load_reminders()
        reminders.sort(key=self._sort_key)
        return reminders

    def list_pending(self) -> list[dict[str, Any]]:
        return [item for item in self.list_all() if item.get("status") == "pending"]

    def check_due_reminders(self) -> list[dict[str, Any]]:
        reminders = self._load_reminders()
        due_reminders: list[dict[str, Any]] = []
        changed = False
        now = datetime.now()

        for reminder in reminders:
            if reminder.get("status") != "pending":
                continue

            due_at_raw = reminder.get("due_at")
            if not due_at_raw:
                continue

            try:
                due_time = datetime.fromisoformat(due_at_raw)
            except ValueError:
                append_log(f"Reminder skipped due to invalid due_at: {reminder}")
                continue

            if now >= due_time:
                reminder["status"] = "done"
                reminder["triggered_at"] = now.isoformat()
                due_reminders.append(reminder)
                changed = True

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
                changed = True
                break

        if changed:
            self._save_reminders(reminders)
            append_log(f"Reminder marked done manually: id={reminder_id}")

        return changed

    def delete(self, reminder_id: str) -> bool:
        reminders = self._load_reminders()
        new_reminders = [item for item in reminders if item.get("id") != reminder_id]

        if len(new_reminders) == len(reminders):
            return False

        self._save_reminders(new_reminders)
        append_log(f"Reminder deleted: id={reminder_id}")
        return True

    def clear_done(self) -> int:
        reminders = self._load_reminders()
        pending = [item for item in reminders if item.get("status") != "done"]
        removed = len(reminders) - len(pending)

        if removed > 0:
            self._save_reminders(pending)
            append_log(f"Cleared completed reminders: count={removed}")

        return removed

    def _load_reminders(self) -> list[dict[str, Any]]:
        data = load_json(self.path, [])
        if not isinstance(data, list):
            return []

        clean_items: list[dict[str, Any]] = []

        for item in data:
            if not isinstance(item, dict):
                continue

            reminder_id = str(item.get("id", "")).strip()
            message = self._clean_message(str(item.get("message", "")).strip())
            created_at = str(item.get("created_at", "")).strip()
            due_at = str(item.get("due_at", "")).strip()
            status = str(item.get("status", "pending")).strip().lower() or "pending"

            if not reminder_id or not message or not due_at:
                continue

            clean_items.append(
                {
                    "id": reminder_id,
                    "message": message,
                    "created_at": created_at,
                    "due_at": due_at,
                    "status": status,
                    **({"triggered_at": item["triggered_at"]} if item.get("triggered_at") else {}),
                }
            )

        return clean_items

    def _save_reminders(self, reminders: list[dict[str, Any]]) -> None:
        save_json(self.path, reminders)

    @staticmethod
    def _clean_message(message: str) -> str:
        cleaned = message.strip()
        cleaned = re.sub(r"\s+", " ", cleaned)

        cleaned = re.sub(r"^(to|about)\s+", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"^(o)\s+", "", cleaned, flags=re.IGNORECASE)

        cleaned = cleaned.strip(" .,!?:;")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        if not cleaned:
            return "Reminder"

        return cleaned

    @staticmethod
    def _sort_key(reminder: dict[str, Any]) -> tuple[int, str]:
        status = reminder.get("status", "pending")
        due_at = reminder.get("due_at", "")
        priority = 0 if status == "pending" else 1
        return priority, due_at