from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from modules.features.memory.service import MemoryService
from modules.features.reminders.service.service import ReminderService
from modules.runtime.product.service import RuntimeProductService
from modules.shared.persistence.repositories import (
    MemoryRepository,
    ReminderRepository,
    SessionStateRepository,
    UserProfileRepository,
)


class PersistenceRecoveryTests(unittest.TestCase):
    def test_memory_repository_repairs_wrong_container_type_on_ensure_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "memory.json"
            path.write_text("[]", encoding="utf-8")

            repo = MemoryRepository(path=str(path))
            payload = repo.ensure_valid()
            read_result = repo.read_result()

            self.assertEqual(payload, {})
            self.assertTrue(read_result.valid)
            self.assertEqual(repo.read(), {})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {})

    def test_reminder_repository_repairs_malformed_json_on_ensure_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "reminders.json"
            path.write_text('{"broken": ', encoding="utf-8")

            repo = ReminderRepository(path=str(path))
            payload = repo.ensure_valid()
            read_result = repo.read_result()

            self.assertEqual(payload, [])
            self.assertTrue(read_result.valid)
            self.assertEqual(repo.read(), [])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), [])

    def test_session_state_and_user_profile_repositories_repair_invalid_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            session_path = Path(temp_dir) / "session_state.json"
            profile_path = Path(temp_dir) / "user_profile.json"
            session_path.write_text("[]", encoding="utf-8")
            profile_path.write_text('{"broken": ', encoding="utf-8")

            session_repo = SessionStateRepository(path=str(session_path))
            profile_repo = UserProfileRepository(
                default_user_name="Andrzej",
                project_name="NeXa",
                path=str(profile_path),
            )

            session_payload = session_repo.ensure_valid()
            profile_payload = profile_repo.ensure_valid()

            self.assertEqual(session_payload["assistant_running"], False)
            self.assertEqual(profile_payload["name"], "Andrzej")
            self.assertEqual(json.loads(session_path.read_text(encoding="utf-8"))["focus_mode"], False)
            self.assertEqual(json.loads(profile_path.read_text(encoding="utf-8"))["project"], "NeXa")

    def test_memory_and_reminder_services_boot_from_corrupt_storage_and_recover(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            memory_path = Path(temp_dir) / "memory.json"
            reminder_path = Path(temp_dir) / "reminders.json"
            memory_path.write_text("[]", encoding="utf-8")
            reminder_path.write_text("{}", encoding="utf-8")

            memory_service = MemoryService(store=MemoryRepository(path=str(memory_path)))
            reminder_service = ReminderService(store=ReminderRepository(path=str(reminder_path)))

            memory_service.remember("keys", "in kitchen")
            reminder = reminder_service.add_after_seconds(seconds=60, message="stand up", language="en")

            self.assertEqual(memory_service.recall("key"), "in kitchen")
            self.assertEqual(reminder["message"], "stand up")
            self.assertIsInstance(json.loads(memory_path.read_text(encoding="utf-8")), dict)
            self.assertIsInstance(json.loads(reminder_path.read_text(encoding="utf-8")), list)

    def test_runtime_product_service_repairs_corrupt_runtime_status_file_on_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime_status.json"
            path.write_text('{"broken": ', encoding="utf-8")

            service = RuntimeProductService(
                settings={},
                persist_enabled=True,
                path=str(path),
            )

            snapshot = service.snapshot()

            self.assertEqual(snapshot["lifecycle_state"], "created")
            self.assertTrue(path.exists())
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["lifecycle_state"], "created")


if __name__ == "__main__":
    unittest.main()