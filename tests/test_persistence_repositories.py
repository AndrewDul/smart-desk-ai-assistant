from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.shared.persistence.repositories import (
    MemoryRepository,
    ReminderRepository,
    SessionStateRepository,
    UserProfileRepository,
)


class PersistenceRepositoriesTests(unittest.TestCase):
    def test_memory_repository_persists_dictionary_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = MemoryRepository(path=str(Path(temp_dir) / "memory.json"))

            initial = repo.ensure_exists()
            written = repo.write({"keys": "in kitchen"})

            self.assertEqual(initial, {})
            self.assertEqual(written, {"keys": "in kitchen"})
            self.assertEqual(repo.read(), {"keys": "in kitchen"})

    def test_reminder_repository_persists_list_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = ReminderRepository(path=str(Path(temp_dir) / "reminders.json"))

            initial = repo.ensure_exists()
            written = repo.write(
                [
                    {
                        "id": "r1",
                        "message": "stand up",
                        "language": "en",
                        "created_at": "2026-04-19T10:00:00",
                        "due_at": "2026-04-19T10:05:00",
                        "status": "pending",
                        "acknowledged": False,
                        "delivered_count": 0,
                    }
                ]
            )

            self.assertEqual(initial, [])
            self.assertEqual(len(written), 1)
            self.assertEqual(repo.read()[0]["id"], "r1")

    def test_session_state_repository_uses_runtime_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = SessionStateRepository(path=str(Path(temp_dir) / "session_state.json"))

            payload = repo.ensure_exists()

            self.assertEqual(
                payload,
                {
                    "assistant_running": False,
                    "focus_mode": False,
                    "break_mode": False,
                    "current_timer": None,
                },
            )

    def test_user_profile_repository_uses_assistant_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = UserProfileRepository(
                default_user_name="Andrzej",
                project_name="NeXa",
                path=str(Path(temp_dir) / "user_profile.json"),
            )

            payload = repo.ensure_exists()

            self.assertEqual(
                payload,
                {
                    "name": "Andrzej",
                    "conversation_partner_name": "",
                    "project": "NeXa",
                },
            )


if __name__ == "__main__":
    unittest.main()