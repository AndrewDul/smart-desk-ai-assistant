from __future__ import annotations

import unittest

from modules.core.flows.action_flow.models import ResolvedAction, SkillRequest, SkillResult
from modules.runtime.contracts import RouteDecision, RouteKind


class ActionSkillModelsTests(unittest.TestCase):
    def test_skill_request_from_route_merges_route_and_resolved_context(self) -> None:
        route = RouteDecision(
            turn_id="turn-skill-request",
            raw_text="what time is it",
            normalized_text="what time is it",
            language="en",
            kind=RouteKind.ACTION,
            confidence=0.93,
            primary_intent="time_query",
            intents=[],
            conversation_topics=[],
            tool_invocations=[],
            notes=["explicit_action"],
            metadata={
                "capture_phase": "inline_command_after_wake",
                "capture_mode": "inline_command_after_wake",
                "capture_backend": "wake_inline_command",
            },
        )
        resolved = ResolvedAction(
            name="ask_time",
            payload={},
            source="route.primary_intent",
            confidence=0.93,
            route_kind="action",
            primary_intent="time_query",
        )

        request = SkillRequest.from_route(route=route, resolved=resolved, language="en")

        self.assertEqual(request.turn_id, "turn-skill-request")
        self.assertEqual(request.action, "ask_time")
        self.assertEqual(request.source, "route.primary_intent")
        self.assertAlmostEqual(request.confidence, 0.93)
        self.assertEqual(request.route_kind, "action")
        self.assertEqual(request.primary_intent, "time_query")
        self.assertEqual(request.capture_phase, "inline_command_after_wake")
        self.assertEqual(request.capture_mode, "inline_command_after_wake")
        self.assertEqual(request.capture_backend, "wake_inline_command")
        self.assertEqual(request.normalized_text, "what time is it")

    def test_skill_result_bool_follows_handled_state(self) -> None:
        success = SkillResult(
            action="ask_time",
            handled=True,
            response_delivered=True,
            status="completed",
        )
        failure = SkillResult(
            action="ask_time",
            handled=False,
            response_delivered=False,
            status="not_handled",
        )

        self.assertTrue(success)
        self.assertFalse(failure)
        self.assertTrue(success.ok)
        self.assertFalse(failure.ok)


if __name__ == "__main__":
    unittest.main()