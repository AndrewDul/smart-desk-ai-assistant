from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from modules.utils import REMINDERS_PATH, append_log, load_json, save_json


class ReminderManager:
    def __init__(self) -> None:
        self.path = REMINDERS_PATH

    def add_after_seconds(self, seconds: int, message: str) -> dict:
        reminders = load_json(self.path, [])

        reminder = {
            "id": str(uuid.uuid4())[:8],
            "message": message,
            "created_at": datetime.now().isoformat(),
            "due_at": (datetime.now() + timedelta(seconds=seconds)).isoformat(),
            "status": "pending",
        }

        reminders.append(reminder)
        save_json(self.path, reminders)
        append_log(
            f"Reminder added: id={reminder['id']}, seconds={seconds}, message={message}"
        )
        return reminder

    def list_all(self) -> list[dict]:
        return load_json(self.path, [])

    def check_due_reminders(self) -> list[dict]:
        reminders = load_json(self.path, [])
        due_reminders = []
        changed = False
        now = datetime.now()

        for reminder in reminders:
            if reminder.get("status") != "pending":
                continue

            due_time = datetime.fromisoformat(reminder["due_at"])
            if now >= due_time:
                reminder["status"] = "done"
                due_reminders.append(reminder)
                changed = True

        if changed:
            save_json(self.path, reminders)

        return due_reminders
