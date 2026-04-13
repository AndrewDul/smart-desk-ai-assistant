from __future__ import annotations

import unittest

from modules.core.flows.action_flow.models import ResolvedAction
from modules.core.flows.action_flow.response_helpers_mixin import ActionResponseHelpersMixin
from modules.runtime.contracts import RouteDecision, RouteKind


class _ActionResponseMetadataProbe(ActionResponseHelpersMixin):
    def __init__(self) -> None:
        self.assistant = object()
        self._active_route = None
        self._active_resolved_action = None


class ActionResponseMetadataTests(unittest.TestCase):
    def test_current_action_response_metadata_includes_route_and_action_context(self) -> None:
        probe = _ActionResponseMetadataProbe()
        probe._active_route = RouteDecision(
            turn_id="turn-action-meta",
            raw_text="what time is it",
            normalized_text="what time is it",
            language="en",
            kind=RouteKind.ACTION,
            confidence=0.94,
            primary_intent="time_query",
            intents=[],
            conversation_topics=[],
            tool_invocations=[],
            notes=["capture_phase:inline_command_after_wake", "explicit_action"],
            metadata={
                "capture_phase": "inline_command_after_wake",
                "capture_mode": "inline_command_after_wake",
                "capture_backend": "wake_inline_command",
                "parser_action": "time_query",
            },
        )
        probe._active_resolved_action = ResolvedAction(
            name="ask_time",
            payload={},
            source="route.primary_intent",
            confidence=0.94,
            route_kind="action",
            primary_intent="time_query",
            route_notes=("capture_phase:inline_command_after_wake", "explicit_action"),
            route_metadata={"capture_phase": "inline_command_after_wake"},
        )

        metadata = probe._current_action_response_metadata(
            language="en",
            action="ask_time",
            extra_metadata={"phase": "unit_test"},
        )

        self.assertEqual(metadata["action"], "ask_time")
        self.assertEqual(metadata["route_kind"], "action")
        self.assertEqual(metadata["primary_intent"], "time_query")
        self.assertEqual(metadata["capture_phase"], "inline_command_after_wake")
        self.assertEqual(metadata["capture_backend"], "wake_inline_command")
        self.assertEqual(metadata["action_source"], "route.primary_intent")
        self.assertAlmostEqual(metadata["action_confidence"], 0.94)
        self.assertEqual(metadata["phase"], "unit_test")


if __name__ == "__main__":
    unittest.main()