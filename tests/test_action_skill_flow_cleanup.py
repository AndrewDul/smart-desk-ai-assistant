from __future__ import annotations

import unittest

from modules.core.flows.action_flow.orchestrator import ActionFlowOrchestrator
from modules.runtime.contracts import EntityValue, IntentMatch, RouteDecision, RouteKind


class _FakeTimer:
    def start(self, minutes: float, mode: str):
        return True, f"{mode} started"


class _FakeAssistant:
    def __init__(self) -> None:
        self.settings = {
            "streaming": {"max_display_chars_per_line": 20},
            "system": {"allow_shutdown_commands": True},
        }
        self.default_focus_minutes = 25
        self.default_break_minutes = 5
        self.timer = _FakeTimer()
        self.pending_follow_up = None
        self.last_text_response = None

    def _normalize_lang(self, language: str) -> str:
        return str(language or "en").strip().lower() or "en"

    def deliver_text_response(self, text: str, *, language: str, route_kind, source: str, metadata=None) -> bool:
        self.last_text_response = {
            "text": text,
            "language": language,
            "route_kind": getattr(route_kind, "value", str(route_kind)),
            "source": source,
            "metadata": dict(metadata or {}),
        }
        return True

    def deliver_response_plan(self, *args, **kwargs) -> bool:
        return True


class ActionSkillFlowCleanupTests(unittest.TestCase):
    def test_timer_start_success_marks_skill_as_accepted_without_response_delivery(self) -> None:
        assistant = _FakeAssistant()
        flow = ActionFlowOrchestrator(assistant)
        route = RouteDecision(
            turn_id="turn-timer-start",
            raw_text="start a timer for 5 minutes",
            normalized_text="start a timer for 5 minutes",
            language="en",
            kind=RouteKind.ACTION,
            confidence=0.93,
            primary_intent="timer_start",
            intents=[IntentMatch(name="timer_start", confidence=0.93)],
            metadata={"capture_phase": "inline_command_after_wake"},
        )
        route.intents[0].entities.append(EntityValue(name="minutes", value=5))

        handled = flow.execute(route=route, language="en")

        self.assertTrue(handled)
        self.assertIsNotNone(flow._last_skill_result)
        self.assertEqual(flow._last_skill_result.action, "timer_start")
        self.assertEqual(flow._last_skill_result.status, "accepted")
        self.assertFalse(flow._last_skill_result.response_delivered)
        self.assertEqual(flow._last_skill_result.metadata["source"], "timer_service.start")

    def test_memory_clear_confirmation_uses_skill_result_and_action_metadata(self) -> None:
        assistant = _FakeAssistant()
        flow = ActionFlowOrchestrator(assistant)
        route = RouteDecision(
            turn_id="turn-memory-clear",
            raw_text="clear memory",
            normalized_text="clear memory",
            language="en",
            kind=RouteKind.ACTION,
            confidence=0.9,
            primary_intent="memory_clear",
        )

        handled = flow.execute(route=route, language="en")

        self.assertTrue(handled)
        self.assertEqual(assistant.pending_follow_up["type"], "confirm_memory_clear")
        self.assertIsNotNone(flow._last_skill_result)
        self.assertEqual(flow._last_skill_result.status, "awaiting_confirmation")
        self.assertTrue(flow._last_skill_result.response_delivered)
        self.assertEqual(flow._last_skill_result.metadata["follow_up_type"], "confirm_memory_clear")
        self.assertEqual(assistant.last_text_response["source"], "action_memory_clear_confirmation")
        self.assertEqual(assistant.last_text_response["metadata"]["action"], "memory_clear")


if __name__ == "__main__":
    unittest.main()