from __future__ import annotations

import unittest

from modules.core.flows.action_flow.models import ResolvedAction, SkillRequest
from modules.core.flows.action_flow.response_helpers_mixin import ActionResponseHelpersMixin
from modules.runtime.contracts import RouteDecision, RouteKind


class _ActionResponseMetadataProbe(ActionResponseHelpersMixin):
    def __init__(self) -> None:
        self.assistant = object()
        self._active_route = None
        self._active_resolved_action = None
        self._active_skill_request = None


class _FakeVoiceOut:
    def __init__(self) -> None:
        self.prepare_calls: list[dict[str, str | None]] = []

    def prepare_speech(self, text: str, language: str | None = None) -> None:
        self.prepare_calls.append({"text": str(text), "language": language})


class _FakeAssistantForDelivery:
    def __init__(self) -> None:
        self.voice_out = _FakeVoiceOut()
        self.settings = {"streaming": {"prefetch_action_responses": True}}
        self._last_plan = None
        self._last_source = ""
        self._last_extra_metadata = {}

    def deliver_response_plan(self, plan, *, source, remember=True, extra_metadata=None):
        del remember
        self._last_plan = plan
        self._last_source = source
        self._last_extra_metadata = dict(extra_metadata or {})
        return True


class _ActionResponseDeliveryProbe(ActionResponseHelpersMixin):
    def __init__(self) -> None:
        self.assistant = _FakeAssistantForDelivery()
        self._active_route = None
        self._active_resolved_action = None
        self._active_skill_request = None


class ActionResponseMetadataTests(unittest.TestCase):
    def test_current_action_response_metadata_includes_route_action_and_skill_request_context(self) -> None:
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
        probe._active_skill_request = SkillRequest.from_route(
            route=probe._active_route,
            resolved=probe._active_resolved_action,
            language="en",
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

        self.assertEqual(metadata["skill_request_turn_id"], "turn-action-meta")
        self.assertEqual(metadata["skill_request_action"], "ask_time")
        self.assertEqual(metadata["skill_request_source"], "route.primary_intent")
        self.assertAlmostEqual(metadata["skill_request_confidence"], 0.94)
        self.assertEqual(metadata["skill_request_capture_phase"], "inline_command_after_wake")
        self.assertEqual(metadata["skill_request_capture_backend"], "wake_inline_command")

        self.assertEqual(metadata["phase"], "unit_test")

    def test_simple_action_response_skips_same_turn_prefetch_before_immediate_delivery(self) -> None:
        probe = _ActionResponseDeliveryProbe()

        ok = probe._deliver_simple_action_response(
            language="en",
            action="ask_time",
            spoken_text="It is ten thirty.",
            display_title="TIME",
            display_lines=["10:30"],
        )

        self.assertTrue(ok)
        self.assertEqual(probe.assistant.voice_out.prepare_calls, [])
        self.assertEqual(probe.assistant._last_source, "action_flow:ask_time")
        self.assertEqual(probe.assistant._last_plan.chunks[0].text, "It is ten thirty.")


if __name__ == "__main__":
    unittest.main()