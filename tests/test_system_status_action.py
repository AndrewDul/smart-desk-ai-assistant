from __future__ import annotations

import unittest

from modules.core.flows.action_flow.models import ResolvedAction
from modules.core.flows.action_flow.response_helpers_mixin import ActionResponseHelpersMixin
from modules.core.flows.action_flow.system_actions_mixin import ActionSystemActionsMixin
from modules.runtime.contracts import RouteDecision, RouteKind


class _FakeMemory:
    def __init__(self, items: dict[str, str]) -> None:
        self._items = dict(items)

    def get_all(self) -> dict[str, str]:
        return dict(self._items)


class _FakeReminders:
    def __init__(self, items: list[dict[str, object]]) -> None:
        self._items = list(items)

    def list_all(self) -> list[dict[str, object]]:
        return list(self._items)


class _FakeTimer:
    def __init__(self, status: dict[str, object]) -> None:
        self._status = dict(status)

    def status(self) -> dict[str, object]:
        return dict(self._status)


class _FakeAssistant:
    def __init__(self, runtime_snapshot: dict[str, object]) -> None:
        self._runtime_snapshot_value = dict(runtime_snapshot)
        self.settings: dict[str, object] = {}
        self.state = {
            "current_timer": "focus",
            "focus_mode": True,
            "break_mode": False,
        }
        self.memory = _FakeMemory({"keys": "kitchen"})
        self.reminders = _FakeReminders([{"id": "r1"}])
        self.timer = _FakeTimer({"running": True})

        self.last_plan = None
        self.last_source = ""
        self.last_extra_metadata: dict[str, object] = {}

    def _runtime_status_snapshot(self) -> dict[str, object]:
        return dict(self._runtime_snapshot_value)

    def deliver_response_plan(
        self,
        plan,
        *,
        source: str,
        remember: bool = True,
        extra_metadata: dict[str, object] | None = None,
    ) -> bool:
        self.last_plan = plan
        self.last_source = source
        self.last_extra_metadata = dict(extra_metadata or {})
        return True


class _SystemStatusProbe(ActionSystemActionsMixin, ActionResponseHelpersMixin):
    def __init__(self, assistant: _FakeAssistant) -> None:
        self.assistant = assistant

    @staticmethod
    def _localized(language: str, pl_text: str, en_text: str) -> str:
        return pl_text if language == "pl" else en_text

    @staticmethod
    def _localized_lines(language: str, pl_lines: list[str], en_lines: list[str]) -> list[str]:
        return list(pl_lines if language == "pl" else en_lines)

    @staticmethod
    def _display_lines(text: str) -> list[str]:
        return [str(text)]


class SystemStatusActionTests(unittest.TestCase):
    def test_status_reports_premium_runtime_ready(self) -> None:
        assistant = _FakeAssistant(
            {
                "lifecycle_state": "ready",
                "ready": True,
                "primary_ready": True,
                "premium_ready": True,
                "status_message": "runtime ready in premium mode",
                "services": {
                    "voice_input": {"backend": "faster_whisper", "state": "ready", "primary": True},
                    "wake_gate": {"backend": "openwakeword", "state": "ready", "primary": True},
                    "llm": {"backend": "hailo-ollama", "state": "ready", "primary": True},
                },
            }
        )
        probe = _SystemStatusProbe(assistant)

        ok = probe._handle_status(
            route=RouteDecision(
                turn_id="turn-status-premium",
                raw_text="status",
                normalized_text="status",
                language="en",
                kind=RouteKind.ACTION,
                confidence=0.95,
                primary_intent="status",
            ),
            language="en",
            payload={},
            resolved=ResolvedAction(
                name="status",
                payload={},
                source="route.primary_intent",
                confidence=0.95,
            ),
        )

        self.assertTrue(ok)
        self.assertEqual(assistant.last_source, "action_flow:status")
        self.assertTrue(assistant.last_extra_metadata["runtime_premium_ready"])
        self.assertTrue(assistant.last_extra_metadata["runtime_primary_ready"])

        spoken = assistant.last_plan.chunks[0].text
        self.assertIn("Premium mode is ready.", spoken)
        self.assertIn("Wake uses oww", spoken)
        self.assertIn("STT uses faster", spoken)
        self.assertIn("LLM uses hailo", spoken)

    def test_status_reports_compatibility_path(self) -> None:
        assistant = _FakeAssistant(
            {
                "lifecycle_state": "degraded",
                "ready": False,
                "primary_ready": True,
                "premium_ready": False,
                "compatibility_components": ["wake_gate"],
                "status_message": "runtime ready with compatibility path: wake_gate",
                "services": {
                    "voice_input": {"backend": "faster_whisper", "state": "ready", "primary": True},
                    "wake_gate": {
                        "backend": "compatibility_voice_input",
                        "state": "ready",
                        "primary": False,
                        "compatibility_mode": True,
                    },
                    "llm": {"backend": "hailo-ollama", "state": "ready", "primary": True},
                },
            }
        )
        probe = _SystemStatusProbe(assistant)

        ok = probe._handle_status(
            route=RouteDecision(
                turn_id="turn-status-compat",
                raw_text="status systemu",
                normalized_text="status systemu",
                language="pl",
                kind=RouteKind.ACTION,
                confidence=0.94,
                primary_intent="status",
            ),
            language="pl",
            payload={},
            resolved=ResolvedAction(
                name="status",
                payload={},
                source="route.primary_intent",
                confidence=0.94,
            ),
        )

        self.assertTrue(ok)
        self.assertFalse(assistant.last_extra_metadata["runtime_premium_ready"])
        self.assertTrue(assistant.last_extra_metadata["runtime_primary_ready"])
        self.assertEqual(
            assistant.last_extra_metadata["runtime_compatibility_components"],
            ["wake_gate"],
        )

        spoken = assistant.last_plan.chunks[0].text
        self.assertIn("ścieżka kompatybilności", spoken)
        self.assertIn("wake używa compat", spoken.lower())
        self.assertIn("stt używa faster", spoken.lower())
        self.assertIn("llm używa hailo", spoken.lower())


if __name__ == "__main__":
    unittest.main()