from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from modules.features.reminders.service import ReminderService
from modules.shared.persistence.repositories import ReminderRepository


class TestReminderManager(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.reminders_file = Path(self.temp_dir.name) / "reminders.json"

        self.manager = ReminderService(store=ReminderRepository(path=str(self.reminders_file)))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_add_after_seconds_creates_pending_reminder(self) -> None:
        reminder = self.manager.add_after_seconds(seconds=30, message="buy milk")

        self.assertEqual(reminder["message"], "buy milk")
        self.assertEqual(reminder["status"], "pending")
        self.assertTrue(self.reminders_file.exists())

    def test_message_is_cleaned_on_add(self) -> None:
        reminder = self.manager.add_after_seconds(seconds=20, message="  to drink water  ")

        self.assertEqual(reminder["message"], "drink water")

    def test_message_is_cleaned_in_polish(self) -> None:
        reminder = self.manager.add_after_seconds(20, "  o zakupach  ")

        self.assertEqual(reminder["message"], "zakupach")

    def test_add_uses_minimum_one_second(self) -> None:
        reminder = self.manager.add_after_seconds(0, "test")

        created = datetime.fromisoformat(reminder["created_at"])
        due = datetime.fromisoformat(reminder["due_at"])

        self.assertGreaterEqual((due - created).total_seconds(), 1)

    def test_list_all_sorts_pending_before_done(self) -> None:
        first = self.manager.add_after_seconds(seconds=5, message="first")
        second = self.manager.add_after_seconds(10, "second")

        self.assertTrue(self.manager.mark_done(first["id"]))

        items = self.manager.list_all()

        self.assertEqual(items[0]["id"], second["id"])
        self.assertEqual(items[0]["status"], "pending")
        self.assertEqual(items[1]["id"], first["id"])
        self.assertEqual(items[1]["status"], "done")

    def test_list_pending_returns_only_pending(self) -> None:
        first = self.manager.add_after_seconds(seconds=5, message="first")
        second = self.manager.add_after_seconds(10, "second")

        self.manager.mark_done(first["id"])
        pending = self.manager.list_pending()

        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], second["id"])

    def test_check_due_reminders_marks_due_as_done(self) -> None:
        reminder = self.manager.add_after_seconds(5, "call back")

        items = self.manager._load_reminders()
        items[0]["due_at"] = (datetime.now() - timedelta(seconds=1)).isoformat()
        self.manager._save_reminders(items)

        due = self.manager.check_due_reminders()

        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["id"], reminder["id"])
        self.assertEqual(due[0]["status"], "done")
        self.assertIn("triggered_at", due[0])

    def test_check_due_reminders_ignores_future_items(self) -> None:
        reminder = self.manager.add_after_seconds(60, "future task")

        due = self.manager.check_due_reminders()

        self.assertEqual(due, [])
        items = self.manager.list_all()
        self.assertEqual(items[0]["id"], reminder["id"])
        self.assertEqual(items[0]["status"], "pending")

    def test_mark_done_returns_true_for_existing_pending_reminder(self) -> None:
        reminder = self.manager.add_after_seconds(15, "stretch")

        result = self.manager.mark_done(reminder["id"])

        self.assertTrue(result)
        items = self.manager.list_all()
        self.assertEqual(items[0]["status"], "done")
        self.assertIn("triggered_at", items[0])

    def test_mark_done_returns_false_for_missing_reminder(self) -> None:
        result = self.manager.mark_done("missing-id")
        self.assertFalse(result)

    def test_delete_removes_reminder(self) -> None:
        reminder = self.manager.add_after_seconds(15, "meeting")

        deleted = self.manager.delete(reminder["id"])

        self.assertTrue(deleted)
        self.assertEqual(self.manager.list_all(), [])

    def test_delete_returns_false_for_missing_reminder(self) -> None:
        deleted = self.manager.delete("missing-id")
        self.assertFalse(deleted)

    def test_clear_done_removes_only_completed_items(self) -> None:
        first = self.manager.add_after_seconds(15, "first")
        second = self.manager.add_after_seconds(30, "second")

        self.manager.mark_done(first["id"])
        removed = self.manager.clear_done()

        self.assertEqual(removed, 1)
        items = self.manager.list_all()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], second["id"])
        self.assertEqual(items[0]["status"], "pending")

    def test_load_reminders_skips_invalid_entries(self) -> None:
        broken_data = [
            {"id": "abc123", "message": "valid", "due_at": datetime.now().isoformat(), "status": "pending"},
            {"id": "", "message": "missing id", "due_at": datetime.now().isoformat(), "status": "pending"},
            {"id": "x2", "message": "", "due_at": datetime.now().isoformat(), "status": "pending"},
            {"id": "x3", "message": "missing due", "status": "pending"},
            "not-a-dict",
        ]
        self.manager._save_reminders(broken_data)

        loaded = self.manager._load_reminders()

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["id"], "abc123")
        self.assertEqual(loaded[0]["message"], "valid")

    def test_due_items_persist_as_done_after_check(self) -> None:
        reminder = self.manager.add_after_seconds(5, "water plants")

        items = self.manager._load_reminders()
        items[0]["due_at"] = (datetime.now() - timedelta(seconds=2)).isoformat()
        self.manager._save_reminders(items)

        self.manager.check_due_reminders()
        reloaded = self.manager.list_all()

        self.assertEqual(reloaded[0]["id"], reminder["id"])
        self.assertEqual(reloaded[0]["status"], "done")
        self.assertIn("triggered_at", reloaded[0])


if __name__ == "__main__":
    unittest.main()