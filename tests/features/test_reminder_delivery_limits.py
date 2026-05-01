from __future__ import annotations

from modules.features.reminders.service import ReminderService
from modules.shared.persistence.repositories import ReminderRepository


def test_check_due_reminders_can_claim_only_one_due_reminder(tmp_path) -> None:
    repository = ReminderRepository(path=str(tmp_path / "reminders.json"))
    reminders = ReminderService(store=repository)

    reminders.add_after_seconds(seconds=1, message="first", language="en")
    reminders.add_after_seconds(seconds=1, message="second", language="en")

    # Force both reminders to be due without sleeping.
    stored = reminders._load_reminders()
    for reminder in stored:
        reminder["due_at"] = "2020-01-01T00:00:00"
    reminders._save_reminders(stored)

    due = reminders.check_due_reminders(limit=1)

    assert len(due) == 1
    assert due[0]["message"] == "first"

    pending = reminders.list_pending()
    assert len(pending) == 1
    assert pending[0]["message"] == "second"

    due_again = reminders.check_due_reminders(limit=1)

    assert len(due_again) == 1
    assert due_again[0]["message"] == "second"
    assert reminders.list_pending() == []
