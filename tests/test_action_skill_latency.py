from __future__ import annotations

import unittest

from modules.core.flows.action_flow.orchestrator import ActionFlowOrchestrator
from modules.runtime.contracts import EntityValue, IntentMatch, RouteDecision, RouteKind


class _FakeTimer:
    def start(self, minutes: float, mode: str):
        return True, f"{mode} started"


class _FakeBenchmarkService:
    def __init__(self) -> None:
        self.skill_started_calls: list[dict[str, object]] = []
        self.skill_finished_calls: list[dict[str, object]] = []

    def note_skill_started(self, *, action: str, source: str = "") -> None:
        self.skill_started_calls.append({"action": action, "source": source})

    def note_skill_finished(self, *, action: str, status: str, source: str = "") -> None:
        self.skill_finished_calls.append(
            {"action": action, "status": status, "source": source}
        )


class _FakeAssistant:
    def __init__(self) -> None:
        self.settings = {
            "streaming": {"max_display_chars_per_line": 20},
            "system": {"allow_shutdown_commands": True},
        }
        self.default_focus_minutes = 25
        self.default_break_minutes = 5
        self.timer = _FakeTimer()
        self.turn_benchmark_service = _FakeBenchmarkService()

    def _normalize_lang(self, language: str) -> str:
        return str(language or "en").strip().lower() or "en"


class ActionSkillLatencyTests(unittest.TestCase):
    def test_timer_start_records_skill_latency_and_response_kind(self) -> None:
        assistant = _FakeAssistant()
        flow = ActionFlowOrchestrator(assistant)
        route = RouteDecision(
            turn_id="turn-skill-latency",
            raw_text="start a timer for 5 minutes",
            normalized_text="start a timer for 5 minutes",
            language="en",
            kind=RouteKind.ACTION,
            confidence=0.94,
            primary_intent="timer_start",
            intents=[IntentMatch(name="timer_start", confidence=0.94)],
            metadata={"capture_phase": "inline_command_after_wake"},
        )
        route.intents[0].entities.append(EntityValue(name="minutes", value=5))

        handled = flow.execute(route=route, language="en")

        self.assertTrue(handled)
        self.assertIsNotNone(flow._last_skill_result)
        self.assertGreaterEqual(float(flow._last_skill_result.metadata.get("latency_ms", -1.0)), 0.0)
        self.assertEqual(flow._last_skill_result.metadata.get("response_kind"), "accepted_only")
        self.assertEqual(flow._last_skill_result.metadata.get("source"), "timer_service.start")
        self.assertEqual(assistant.turn_benchmark_service.skill_started_calls[0]["action"], "timer_start")
        self.assertEqual(assistant.turn_benchmark_service.skill_started_calls[0]["source"], "route.primary_intent")
        self.assertEqual(assistant.turn_benchmark_service.skill_finished_calls[0]["action"], "timer_start")
        self.assertEqual(assistant.turn_benchmark_service.skill_finished_calls[0]["status"], "accepted")
        self.assertEqual(assistant.turn_benchmark_service.skill_finished_calls[0]["source"], "timer_service.start")


if __name__ == "__main__":
    unittest.main()