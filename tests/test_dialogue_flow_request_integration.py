from __future__ import annotations

import unittest

from modules.core.flows.dialogue_flow.models import DialogueRequest
from modules.core.flows.dialogue_flow.orchestrator import DialogueFlowOrchestrator
from modules.runtime.contracts import ResponsePlan, RouteDecision, RouteKind, StreamMode, ToolInvocation


class _FakeVoiceSession:
    def __init__(self) -> None:
        self.states: list[tuple[str, str]] = []

    def set_state(self, state: str, *, detail: str = "") -> None:
        self.states.append((state, detail))


class _FakeDialogueService:
    def __init__(self) -> None:
        self.last_request = None

    def build_response_plan(self, request, user_profile, *, stream_mode=None):
        self.last_request = request
        plan = ResponsePlan(
            turn_id="reply-dialogue-1",
            language="en",
            route_kind=RouteKind.MIXED,
            stream_mode=stream_mode or StreamMode.SENTENCE,
            metadata={
                "display_title": "CHAT",
                "display_lines": ["Working on it"],
                "reply_source": "fake_dialogue_service",
            },
        )
        plan.add_text("I can help with that.")
        return plan


class _FakeActionFlow:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, *, route, language: str) -> bool:
        self.calls.append((route, language))
        return True


class _FakeAssistant:
    def __init__(self) -> None:
        self.dialogue = _FakeDialogueService()
        self.action_flow = _FakeActionFlow()
        self.voice_session = _FakeVoiceSession()
        self.stream_mode = StreamMode.SENTENCE
        self.pending_follow_up = None
        self.last_plan = None
        self.last_delivery_metadata = None

    def _commit_language(self, language: str) -> str:
        return str(language or "en")

    def _build_dialogue_user_profile(self, *, preferred_language: str) -> dict[str, str]:
        return {"language": preferred_language}

    def _thinking_ack_start(self, *, language: str, detail: str) -> None:
        return None

    def _thinking_ack_stop(self) -> None:
        return None

    def deliver_response_plan(self, plan, *, source: str, remember: bool, extra_metadata: dict | None = None) -> bool:
        self.last_plan = plan
        self.last_delivery_metadata = {
            "source": source,
            "remember": remember,
            "extra_metadata": dict(extra_metadata or {}),
        }
        return True

    def _localized(self, language: str, polish: str, english: str) -> str:
        return polish if language == "pl" else english

    def _display_lines(self, text: str) -> list[str]:
        return [str(text)]

    def deliver_text_response(self, *args, **kwargs) -> bool:
        return True


class DialogueFlowRequestIntegrationTests(unittest.TestCase):
    def test_execute_dialogue_route_passes_typed_dialogue_request_to_dialogue_service(self) -> None:
        assistant = _FakeAssistant()
        flow = DialogueFlowOrchestrator(assistant)
        route = RouteDecision(
            turn_id="turn-dialogue-integration",
            raw_text="can you help me focus and start a timer",
            normalized_text="can you help me focus and start a timer",
            language="en",
            kind=RouteKind.MIXED,
            confidence=0.91,
            primary_intent="support_request",
            intents=[],
            conversation_topics=["productivity"],
            tool_invocations=[
                ToolInvocation(
                    tool_name="focus.start",
                    payload={"minutes": 25},
                    execute_immediately=False,
                ),
                ToolInvocation(
                    tool_name="timer.start",
                    payload={"minutes": 25},
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

        handled = flow.execute_dialogue_route(route, "en")

        self.assertTrue(handled)
        self.assertIsInstance(assistant.dialogue.last_request, DialogueRequest)
        self.assertEqual(assistant.dialogue.last_request.turn_id, "turn-dialogue-integration")
        self.assertEqual(assistant.dialogue.last_request.kind, RouteKind.MIXED)
        self.assertEqual(assistant.dialogue.last_request.suggested_actions, ["focus_start"])
        self.assertEqual(assistant.dialogue.last_request.immediate_actions, ["timer_start"])
        self.assertEqual(assistant.dialogue.last_request.capture_phase, "conversation_after_wake")
        self.assertIsNotNone(flow._last_dialogue_result)
        self.assertTrue(flow._last_dialogue_result.delivered)
        self.assertEqual(flow._last_dialogue_result.metadata["reply_mode"], "reply_then_offer")


if __name__ == "__main__":
    unittest.main()