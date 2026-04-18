from __future__ import annotations

import unittest

from modules.core.flows.action_flow.executors import (
    MemorySkillExecutor,
    ReminderSkillExecutor,
    TimerSkillExecutor,
)


class _FakeTimer:
    def __init__(self) -> None:
        self.started = []
        self.stopped = 0

    def start(self, minutes: float, mode: str):
        self.started.append((minutes, mode))
        return True, f"{mode} started"

    def stop(self):
        self.stopped += 1
        return True, "stopped"


class _FakeMemory:
    def __init__(self) -> None:
        self.data = {"keys": "in kitchen"}

    def remember(self, key: str, value: str) -> None:
        self.data[key] = value

    def recall(self, key: str):
        return self.data.get(key)

    def forget(self, key: str):
        if key in self.data:
            del self.data[key]
            return key
        return None

    def get_all(self):
        return dict(self.data)


class _FakeReminders:
    def __init__(self) -> None:
        self.items = [
            {"id": "r1", "message": "stand up", "status": "pending"},
            {"id": "r2", "message": "drink water", "status": "done"},
        ]

    def list_all(self):
        return list(self.items)

    def add_after_seconds(self, *, seconds: int, message: str, language: str):
        reminder = {"id": "r3", "message": message, "status": "pending", "seconds": seconds, "language": language}
        self.items.append(reminder)
        return reminder

    def find_by_id(self, reminder_id: str):
        for item in self.items:
            if item["id"] == reminder_id:
                return dict(item)
        return None

    def find_by_message(self, message: str):
        for item in self.items:
            if item["message"] == message:
                return dict(item)
        return None


class _FakeAssistant:
    def __init__(self) -> None:
        self.timer = _FakeTimer()
        self.memory = _FakeMemory()
        self.reminders = _FakeReminders()


class ActionSkillExecutorsTests(unittest.TestCase):
    def test_timer_executor_returns_accepted_contract(self) -> None:
        executor = TimerSkillExecutor(assistant=_FakeAssistant())

        started = executor.start(mode="focus", minutes=25)
        stopped = executor.stop()

        self.assertTrue(started.ok)
        self.assertEqual(started.status, "accepted")
        self.assertEqual(started.data["mode"], "focus")
        self.assertEqual(started.metadata["source"], "timer_service.start")
        self.assertTrue(stopped.ok)
        self.assertEqual(stopped.metadata["source"], "timer_service.stop")

    def test_memory_executor_exposes_request_driven_service_contract(self) -> None:
        executor = MemorySkillExecutor(assistant=_FakeAssistant())

        stored = executor.store(key="wallet", value="on desk")
        recalled = executor.recall(key="wallet")
        listed = executor.list_items()
        removed = executor.forget(key="wallet")

        self.assertEqual(stored.status, "stored")
        self.assertEqual(recalled.status, "found")
        self.assertEqual(recalled.data["value"], "on desk")
        self.assertEqual(listed.status, "listed")
        self.assertGreaterEqual(listed.data["count"], 1)
        self.assertEqual(removed.status, "removed")
        self.assertEqual(removed.data["key"], "wallet")

    def test_reminder_executor_exposes_create_list_and_delete_target_contracts(self) -> None:
        executor = ReminderSkillExecutor(assistant=_FakeAssistant())

        listed = executor.list_items()
        created = executor.create(seconds=300, message="call back", language="en")
        resolved = executor.resolve_delete_target(reminder_id="r1", message=None)

        self.assertEqual(listed.status, "listed")
        self.assertEqual(listed.data["pending_count"], 1)
        self.assertEqual(created.status, "created")
        self.assertEqual(created.data["reminder_id"], "r3")
        self.assertEqual(resolved.status, "delete_target_resolved")
        self.assertEqual(resolved.data["reminder_id"], "r1")


if __name__ == "__main__":
    unittest.main()