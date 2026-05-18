from __future__ import annotations

import unittest

from modules.core.flows.dialogue_flow.models import DialogueRequest
from modules.core.flows.dialogue_flow.orchestrator import DialogueFlowOrchestrator
from modules.core.flows.pending_flow.orchestrator import PendingFlowOrchestrator
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
        self.pending_confirmation = None
        self.pending_follow_up = None
        self.last_plan = None
        self.last_delivery_metadata = None
        self.text_responses: list[dict[str, object]] = []
        self.completed_commands: list[str] = []
        self.thinking_ack_starts: list[dict[str, str]] = []
        self.thinking_ack_stops = 0
        self.ai_broker_modes: list[str] = []

    def _commit_language(self, language: str) -> str:
        return str(language or "en")

    def _build_dialogue_user_profile(self, *, preferred_language: str) -> dict[str, str]:
        return {"language": preferred_language}

    def _thinking_ack_start(self, *, language: str, detail: str) -> None:
        self.thinking_ack_starts.append({"language": language, "detail": detail})

    def _thinking_ack_stop(self) -> None:
        self.thinking_ack_stops += 1

    def _enter_ai_broker_conversation_answer_mode(self, *, reason: str) -> None:
        self.ai_broker_modes.append(f"answer:{reason}")

    def _enter_ai_broker_recovery_window(
        self,
        *,
        reason: str,
        return_to_mode: str,
    ) -> None:
        self.ai_broker_modes.append(f"recovery:{reason}:{return_to_mode}")

    def deliver_response_plan(self, plan, *, source: str, remember: bool, extra_metadata: dict | None = None) -> bool:
        self._thinking_ack_stop()
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

    def deliver_text_response(self, text: str, **kwargs) -> bool:
        self.text_responses.append({"text": str(text), **dict(kwargs)})
        return True

    def handle_command(self, text: str) -> bool:
        self.completed_commands.append(str(text))
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
        self.assertEqual(
            assistant.thinking_ack_starts,
            [{"language": "en", "detail": "dialogue_plan"}],
        )
        self.assertEqual(assistant.thinking_ack_stops, 1)
        self.assertEqual(assistant.dialogue.last_request.capture_phase, "conversation_after_wake")
        self.assertIsNotNone(flow._last_dialogue_result)
        self.assertTrue(flow._last_dialogue_result.delivered)
        self.assertEqual(flow._last_dialogue_result.metadata["reply_mode"], "reply_then_offer")

    def test_generic_unclear_polish_prompts_for_repeat_and_sets_follow_up(self) -> None:
        assistant = _FakeAssistant()
        flow = DialogueFlowOrchestrator(assistant)
        route = RouteDecision(
            turn_id="turn-unclear-pl",
            raw_text="ble ble",
            normalized_text="ble ble",
            language="pl",
            kind=RouteKind.UNCLEAR,
            confidence=0.0,
            primary_intent="unclear",
            intents=[],
            conversation_topics=[],
            tool_invocations=[],
            notes=["router_returned_none"],
            metadata={},
        )

        handled = flow.handle_unclear_route(route=route, language="pl")

        self.assertTrue(handled)
        self.assertEqual(assistant.text_responses[-1]["text"], "Nie zrozumiałam. Możesz powtórzyć?")
        self.assertEqual(assistant.pending_follow_up["type"], "clarification_repeat")
        self.assertEqual(assistant.pending_follow_up["language"], "pl")
        self.assertEqual(assistant.pending_follow_up["retry_count"], 0)
        self.assertIsNone(assistant.dialogue.last_request)

    def test_generic_unclear_english_prompts_for_repeat_and_sets_follow_up(self) -> None:
        assistant = _FakeAssistant()
        flow = DialogueFlowOrchestrator(assistant)
        route = RouteDecision(
            turn_id="turn-unclear-en",
            raw_text="mumble",
            normalized_text="mumble",
            language="en",
            kind=RouteKind.UNCLEAR,
            confidence=0.0,
            primary_intent="unclear",
            intents=[],
            conversation_topics=[],
            tool_invocations=[],
            notes=["router_returned_none"],
            metadata={},
        )

        handled = flow.handle_unclear_route(route=route, language="en")

        self.assertTrue(handled)
        self.assertEqual(assistant.text_responses[-1]["text"], "I didn’t catch that. Can you repeat?")
        self.assertEqual(assistant.pending_follow_up["type"], "clarification_repeat")
        self.assertEqual(assistant.pending_follow_up["language"], "en")
        self.assertIsNone(assistant.dialogue.last_request)

    def test_incomplete_dialogue_query_prompts_for_topic_and_sets_follow_up(self) -> None:
        assistant = _FakeAssistant()
        flow = DialogueFlowOrchestrator(assistant)
        route = RouteDecision(
            turn_id="turn-incomplete-topic",
            raw_text="Tell me about...",
            normalized_text="tell me about...",
            language="en",
            kind=RouteKind.UNCLEAR,
            confidence=0.86,
            primary_intent="incomplete_dialogue_query",
            intents=[],
            conversation_topics=[],
            tool_invocations=[],
            notes=["incomplete_dialogue_query"],
            metadata={
                "incomplete_dialogue_query": True,
                "clarification_prompt_kind": "tell_about_topic",
            },
        )

        handled = flow.handle_unclear_route(route=route, language="en")

        self.assertTrue(handled)
        self.assertEqual(assistant.text_responses[-1]["text"], "Tell you about what?")
        self.assertEqual(assistant.text_responses[-1]["source"], "dialogue_incomplete_query_clarification")
        self.assertEqual(assistant.pending_follow_up["type"], "clarification_repeat")
        self.assertEqual(assistant.pending_follow_up["source"], "incomplete_dialogue_query")
        self.assertIsNone(assistant.dialogue.last_request)

    def test_partial_polish_topic_prompts_for_specific_topic(self) -> None:
        assistant = _FakeAssistant()
        flow = DialogueFlowOrchestrator(assistant)
        route = RouteDecision(
            turn_id="turn-partial-polish-topic",
            raw_text="Powiedz mi coś o sztucznej.",
            normalized_text="powiedz mi coś o sztucznej",
            language="pl",
            kind=RouteKind.UNCLEAR,
            confidence=0.84,
            primary_intent="partial_dialogue_topic",
            intents=[],
            conversation_topics=[],
            tool_invocations=[],
            notes=["partial_polish_dialogue_topic"],
            metadata={
                "partial_polish_dialogue_topic": True,
                "clarification_prompt_kind": "partial_artificial_topic",
            },
        )

        handled = flow.handle_unclear_route(route=route, language="pl")

        self.assertTrue(handled)
        self.assertEqual(
            assistant.text_responses[-1]["text"],
            "O sztucznej czym? Chodzi Ci o sztuczną inteligencję?",
        )
        self.assertEqual(assistant.pending_follow_up["source"], "partial_polish_dialogue_topic")
        self.assertIsNone(assistant.dialogue.last_request)

    def test_incomplete_dialogue_topic_follow_up_completes_english_query(self) -> None:
        assistant = _FakeAssistant()
        assistant.pending_follow_up = {
            "type": "clarification_repeat",
            "language": "en",
            "retry_count": 0,
            "max_retries": 1,
            "source": "incomplete_dialogue_query",
        }
        flow = PendingFlowOrchestrator(assistant)

        decision = flow.process_pending_state(
            routing_text="Black holes.",
            command_lang="en",
        )

        self.assertTrue(decision.handled)
        self.assertIsNone(assistant.pending_follow_up)
        self.assertEqual(assistant.completed_commands, ["Tell me about Black holes."])
        self.assertEqual(decision.consumed_by, "follow_up:incomplete_dialogue_topic")

    def test_incomplete_dialogue_topic_follow_up_completes_polish_query(self) -> None:
        assistant = _FakeAssistant()
        assistant.pending_follow_up = {
            "type": "clarification_repeat",
            "language": "pl",
            "retry_count": 0,
            "max_retries": 1,
            "source": "incomplete_dialogue_query",
        }
        flow = PendingFlowOrchestrator(assistant)

        decision = flow.process_pending_state(
            routing_text="czarne dziury",
            command_lang="pl",
        )

        self.assertTrue(decision.handled)
        self.assertIsNone(assistant.pending_follow_up)
        self.assertEqual(assistant.completed_commands, ["Opowiedz mi o czarnych dziurach."])
        self.assertEqual(decision.consumed_by, "follow_up:incomplete_dialogue_topic")


if __name__ == "__main__":
    unittest.main()
