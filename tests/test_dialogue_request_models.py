from __future__ import annotations

import unittest

from modules.core.flows.dialogue_flow.models import DialogueRequest, DialogueResult
from modules.runtime.contracts import RouteDecision, RouteKind, ToolInvocation


class DialogueRequestModelsTests(unittest.TestCase):
    def test_dialogue_request_from_route_preserves_router_context(self) -> None:
        route = RouteDecision(
            turn_id="turn-dialogue-1",
            raw_text="can you help me focus and maybe set a timer",
            normalized_text="can you help me focus and maybe set a timer",
            language="en",
            kind=RouteKind.MIXED,
            confidence=0.88,
            primary_intent="support_request",
            intents=[],
            conversation_topics=["productivity"],
            tool_invocations=[
                ToolInvocation(
                    tool_name="focus.start",
                    payload={"minutes": 25},
                    reason="focus mode suggestion",
                    confidence=0.9,
                    execute_immediately=False,
                ),
                ToolInvocation(
                    tool_name="timer.start",
                    payload={"minutes": 25},
                    reason="timer action",
                    confidence=0.95,
                    execute_immediately=True,
                ),
            ],
            notes=["mixed_route"],
            metadata={
                "capture_phase": "conversation_after_wake",
                "capture_mode": "conversation",
                "capture_backend": "speech_recognition_service",
            },
        )

        request = DialogueRequest.from_route(
            route=route,
            language="en",
            reply_mode="reply_then_offer",
            suggested_actions=["focus_start"],
            immediate_actions=["timer_start"],
        )

        self.assertEqual(request.turn_id, "turn-dialogue-1")
        self.assertEqual(request.kind, RouteKind.MIXED)
        self.assertEqual(request.reply_mode, "reply_then_offer")
        self.assertEqual(request.primary_intent, "support_request")
        self.assertEqual(request.suggested_actions, ["focus_start"])
        self.assertEqual(request.immediate_actions, ["timer_start"])
        self.assertEqual(request.capture_phase, "conversation_after_wake")
        self.assertEqual(request.capture_mode, "conversation")
        self.assertEqual(request.capture_backend, "speech_recognition_service")
        self.assertTrue(request.has_action)
        self.assertIsNotNone(request.action_result)
        self.assertEqual(request.action_result.action, "timer_start")

    def test_dialogue_result_bool_reflects_handled(self) -> None:
        success = DialogueResult(handled=True, delivered=True, status="completed")
        failure = DialogueResult(handled=False, delivered=False, status="not_handled")

        self.assertTrue(success)
        self.assertFalse(failure)
        self.assertTrue(success.ok)
        self.assertFalse(failure.ok)


if __name__ == "__main__":
    unittest.main()