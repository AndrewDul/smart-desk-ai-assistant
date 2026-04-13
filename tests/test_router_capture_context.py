from __future__ import annotations

import unittest

from modules.runtime.contracts import RouteKind
from modules.understanding.parsing.models import IntentResult
from modules.understanding.routing.companion_router import SemanticCompanionRouter


class _FakeParser:
    def __init__(self, result: IntentResult) -> None:
        self._result = result

    def parse(self, text: str) -> IntentResult:
        return self._result


class RouterCaptureContextTests(unittest.TestCase):
    def test_follow_up_context_biases_unclear_into_conversation(self) -> None:
        router = SemanticCompanionRouter(
            _FakeParser(
                IntentResult.unclear(
                    normalized_text="and tomorrow",
                    confidence=0.22,
                )
            )
        )

        route = router.route(
            "and tomorrow",
            preferred_language="en",
            context={
                "input_source": "voice",
                "capture_phase": "follow_up",
                "capture_mode": "follow_up",
                "capture_backend": "faster_whisper",
            },
        )

        self.assertEqual(route.kind, RouteKind.CONVERSATION)
        self.assertEqual(route.primary_intent, "follow_up_conversation")
        self.assertIn("follow_up_context_bias", route.notes)
        self.assertEqual(route.metadata["capture_phase"], "follow_up")
        self.assertEqual(route.metadata["capture_backend"], "faster_whisper")

    def test_inline_command_after_wake_preserves_context_for_explicit_action(self) -> None:
        router = SemanticCompanionRouter(
            _FakeParser(
                IntentResult.from_action(
                    action="time_query",
                    normalized_text="what time is it",
                    confidence=0.91,
                )
            )
        )

        route = router.route(
            "what time is it",
            preferred_language="en",
            context={
                "input_source": "voice",
                "capture_phase": "inline_command_after_wake",
                "capture_mode": "inline_command_after_wake",
                "capture_backend": "wake_inline_command",
            },
        )

        self.assertEqual(route.kind, RouteKind.ACTION)
        self.assertGreaterEqual(route.confidence, 0.92)
        self.assertEqual(route.metadata["capture_phase"], "inline_command_after_wake")
        self.assertEqual(route.metadata["capture_backend"], "wake_inline_command")
        self.assertIn("capture_phase:inline_command_after_wake", route.notes)


if __name__ == "__main__":
    unittest.main()