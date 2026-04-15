from __future__ import annotations

import unittest

from modules.core.flows.action_flow.models import ResolvedAction
from modules.core.flows.action_flow.response_helpers_mixin import ActionResponseHelpersMixin
from modules.core.flows.action_flow.system_actions_mixin import ActionSystemActionsMixin
from modules.runtime.contracts import RouteDecision, RouteKind


class _FakeMemory:
    def get_all(self):
        return {"keys": "kitchen"}


class _FakeReminders:
    def list_all(self):
        return [{"id": "r1"}, {"id": "r2"}]


class _FakeTimer:
    def status(self):
        return {"running": True, "mode": "focus"}


class _FakeBenchmarkService:
    def latest_snapshot(self):
        return {
            "latest_sample": {
                "total_turn_ms": 910.0,
                "result": "conversation_route",
                "route_kind": "conversation",
            },
            "summary": {
                "avg_total_turn_ms": 930.0,
                "avg_response_first_audio_ms": 145.0,
                "avg_llm_first_chunk_ms": 82.0,
            },
            "overlay_lines": [
                "turn:910ms audio:145ms",
                "llm:82ms result:conver",
            ],
        }


class _FakeAssistant:
    def __init__(self):
        self.state = {
            "current_timer": "focus",
            "focus_mode": True,
            "break_mode": False,
        }
        self.memory = _FakeMemory()
        self.reminders = _FakeReminders()
        self.timer = _FakeTimer()
        self.turn_benchmark_service = _FakeBenchmarkService()
        self.backend_statuses = {}
        self._last_plan = None
        self._last_source = ""
        self._last_extra_metadata = {}

    def _runtime_status_snapshot(self):
        return {
            "lifecycle_state": "ready",
            "startup_mode": "premium",
            "ready": True,
            "degraded": False,
            "services": {
                "wake_gate": {"backend": "openwakeword"},
                "voice_input": {"backend": "faster_whisper"},
                "llm": {"backend": "hailo-ollama"},
            },
        }

    def deliver_response_plan(self, plan, *, source, remember=True, extra_metadata=None):
        self._last_plan = plan
        self._last_source = source
        self._last_extra_metadata = dict(extra_metadata or {})
        return True


class _Probe(ActionSystemActionsMixin, ActionResponseHelpersMixin):
    def __init__(self):
        self.assistant = _FakeAssistant()

    @staticmethod
    def _localized(language: str, pl_text: str, en_text: str) -> str:
        return pl_text if language == "pl" else en_text

    @staticmethod
    def _localized_lines(language: str, pl_lines: list[str], en_lines: list[str]) -> list[str]:
        return list(pl_lines if language == "pl" else en_lines)

    @staticmethod
    def _display_lines(text: str) -> list[str]:
        return [str(text)]


class SystemStatusMetricsTests(unittest.TestCase):
    def test_status_includes_runtime_backends_and_benchmark_metrics(self) -> None:
        probe = _Probe()

        ok = probe._handle_status(
            route=RouteDecision(
                turn_id="turn-status",
                raw_text="status",
                normalized_text="status",
                language="en",
                kind=RouteKind.ACTION,
                confidence=0.95,
                primary_intent="status",
                intents=[],
                conversation_topics=[],
                tool_invocations=[],
                notes=[],
                metadata={},
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
        self.assertEqual(probe.assistant._last_source, "action_flow:status")

        spoken = probe.assistant._last_plan.chunks[0].text
        self.assertIn("Wake uses oww", spoken)
        self.assertIn("STT uses faster", spoken)
        self.assertIn("LLM uses hailo", spoken)
        self.assertIn("latest full turn took 910 milliseconds", spoken.lower())
        self.assertIn("average voice start is 145 milliseconds", spoken.lower())
        self.assertIn("average llm first chunk is 82 milliseconds", spoken.lower())

        metadata = probe.assistant._last_extra_metadata
        self.assertEqual(metadata["wake_backend"], "oww")
        self.assertEqual(metadata["stt_backend"], "faster")
        self.assertEqual(metadata["llm_backend"], "hailo")
        self.assertAlmostEqual(metadata["last_turn_ms"], 910.0)
        self.assertAlmostEqual(metadata["avg_response_first_audio_ms"], 145.0)
        self.assertAlmostEqual(metadata["avg_llm_first_chunk_ms"], 82.0)

    def test_debug_status_exposes_technical_snapshot(self) -> None:
        probe = _Probe()

        ok = probe._handle_debug_status(
            route=RouteDecision(
                turn_id="turn-debug-status",
                raw_text="debug status",
                normalized_text="debug status",
                language="en",
                kind=RouteKind.ACTION,
                confidence=0.95,
                primary_intent="debug_status",
                intents=[],
                conversation_topics=[],
                tool_invocations=[],
                notes=[],
                metadata={},
            ),
            language="en",
            payload={},
            resolved=ResolvedAction(
                name="debug_status",
                payload={},
                source="route.primary_intent",
                confidence=0.95,
            ),
        )

        self.assertTrue(ok)
        self.assertEqual(probe.assistant._last_source, "action_flow:debug_status")

        spoken = probe.assistant._last_plan.chunks[0].text
        self.assertIn("technical debug status", spoken.lower())
        self.assertIn("latest result is conversation_route", spoken.lower())
        self.assertIn("debug overlay contains 2 lines", spoken.lower())

        metadata = probe.assistant._last_extra_metadata
        self.assertEqual(metadata["wake_backend"], "oww")
        self.assertEqual(metadata["stt_backend"], "faster")
        self.assertEqual(metadata["llm_backend"], "hailo")
        self.assertTrue(metadata["overlay_lines"])
        self.assertTrue(metadata["debug_lines"])


if __name__ == "__main__":
    unittest.main()