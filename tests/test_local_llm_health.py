from __future__ import annotations

import unittest
from unittest import mock

from modules.understanding.dialogue.llm.local_llm import LocalLLMService


class LocalLLMHealthTests(unittest.TestCase):
    def _build_service(self) -> LocalLLMService:
        return LocalLLMService(
            {
                "llm": {
                    "enabled": True,
                    "runner": "hailo-ollama",
                    "server_url": "http://127.0.0.1:8000",
                    "startup_warmup": True,
                    "auto_recovery_enabled": True,
                    "auto_recovery_cooldown_seconds": 0.0,
                    "max_auto_recovery_attempts": 2,
                }
            }
        )

    def test_backend_health_snapshot_reports_degraded_when_server_is_available_but_not_warmed(self) -> None:
        service = self._build_service()
        service._record_backend_availability_result(True, error="")
        service._last_warmup_ok = False

        snapshot = service.backend_health_snapshot()

        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["state"], "degraded")
        self.assertTrue(snapshot["warmup_required"])
        self.assertFalse(snapshot["warmup_ready"])
        self.assertIn("warmup", snapshot["capabilities"])

    def test_ensure_backend_ready_attempts_auto_recovery_and_returns_ready_snapshot(self) -> None:
        service = self._build_service()
        state = {"available": False}

        def fake_is_available() -> bool:
            service._record_backend_availability_result(
                state["available"],
                error="" if state["available"] else "server down",
            )
            return state["available"]

        def fake_warmup() -> bool:
            state["available"] = True
            service._record_warmup_result(ok=True, error="")
            service._record_backend_availability_result(True, error="")
            return True

        with mock.patch.object(service, "is_available", side_effect=fake_is_available):
            with mock.patch.object(service, "warmup_backend_if_enabled", side_effect=fake_warmup):
                snapshot = service.ensure_backend_ready(auto_recover=True)

        self.assertTrue(snapshot["recovery_attempted"])
        self.assertTrue(snapshot["recovery_ok"])
        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["state"], "ready")


if __name__ == "__main__":
    unittest.main()