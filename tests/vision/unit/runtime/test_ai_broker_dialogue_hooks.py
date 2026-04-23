from __future__ import annotations

import unittest

from modules.core.flows.dialogue_flow.orchestrator import DialogueFlowOrchestrator
from modules.runtime.contracts import ResponsePlan, RouteDecision, RouteKind, StreamMode


class _FakeVoiceSession:
    def __init__(self) -> None:
        self.states: list[tuple[str, str]] = []

    def set_state(self, state: str, *, detail: str = "") -> None:
        self.states.append((state, detail))


class _FakeDialogueService:
    def build_response_plan(self, request, user_profile, *, stream_mode=None):
        del request, user_profile
        plan = ResponsePlan(
            turn_id="reply-dialogue-broker-1",
            language="en",
            route_kind=RouteKind.CONVERSATION,
            stream_mode=stream_mode or StreamMode.SENTENCE,
            metadata={
                "display_title": "CHAT",
                "display_lines": ["Working on it"],
                "reply_source": "fake_dialogue_service",
            },
        )
        plan.add_text("I can help with that.")
        return plan


class _FakeAssistant:
    def __init__(self, *, deliver_ok: bool = True) -> None:
        self.dialogue = _FakeDialogueService()
        self.voice_session = _FakeVoiceSession()
        self.stream_mode = StreamMode.SENTENCE
        self.pending_follow_up = None
        self.deliver_ok = bool(deliver_ok)
        self.ai_broker_calls: list[tuple[str, str]] = []

    def _commit_language(self, language: str) -> str:
        return str(language or "en")

    def _build_dialogue_user_profile(self, *, preferred_language: str) -> dict[str, str]:
        return {"language": preferred_language}

    def _thinking_ack_start(self, *, language: str, detail: str) -> None:
        del language, detail
        return None

    def _thinking_ack_stop(self) -> None:
        return None

    def _enter_ai_broker_conversation_answer_mode(self, *, reason: str = "") -> dict[str, object]:
        self.ai_broker_calls.append(("conversation", reason))
        return {
            "mode": "conversation_answer",
            "owner": "answer_path",
            "profile": {"heavy_lane_cadence_hz": 0.5},
        }

    def _enter_ai_broker_idle_baseline(self, *, reason: str = "") -> dict[str, object]:
        self.ai_broker_calls.append(("idle", reason))
        return {
            "mode": "idle_baseline",
            "owner": "balanced",
            "profile": {"heavy_lane_cadence_hz": 2.0},
        }

    def _enter_ai_broker_recovery_window(
        self,
        *,
        reason: str = "",
        return_to_mode="idle_baseline",
        seconds: float | None = None,
    ) -> dict[str, object]:
        del seconds
        mode_value = getattr(return_to_mode, "value", return_to_mode)
        self.ai_broker_calls.append(("recovery", f"{reason}|{mode_value}"))
        return {
            "mode": "recovery_window",
            "owner": "balanced",
            "profile": {"heavy_lane_cadence_hz": 1.0},
            "recovery_window_active": True,
        }

    def deliver_response_plan(self, plan, *, source: str, remember: bool, extra_metadata=None) -> bool:
        del plan, source, remember, extra_metadata
        return self.deliver_ok

    def _localized(self, language: str, polish: str, english: str) -> str:
        return polish if language == "pl" else english

    def _display_lines(self, text: str) -> list[str]:
        return [str(text)]

    def deliver_text_response(self, *args, **kwargs) -> bool:
        del args, kwargs
        return True


class AiBrokerDialogueHookTests(unittest.TestCase):
    def _build_route(self) -> RouteDecision:
        return RouteDecision(
            turn_id="turn-dialogue-broker-hooks",
            raw_text="explain black holes",
            normalized_text="explain black holes",
            language="en",
            kind=RouteKind.CONVERSATION,
            confidence=0.92,
            primary_intent="general_question",
            intents=[],
            conversation_topics=["space"],
            tool_invocations=[],
            notes=[],
            metadata={
                "capture_phase": "conversation_after_wake",
                "capture_mode": "conversation",
                "capture_backend": "speech_recognition_service",
            },
        )

    def test_execute_dialogue_route_enters_conversation_mode_and_returns_to_idle(self) -> None:
        assistant = _FakeAssistant(deliver_ok=True)
        flow = DialogueFlowOrchestrator(assistant)

        handled = flow.execute_dialogue_route(self._build_route(), "en")

        self.assertTrue(handled)
        self.assertEqual(
            assistant.ai_broker_calls,
            [
                ("conversation", "dialogue_route_started:conversation"),
                ("recovery", "dialogue_route_finished:conversation|idle_baseline"),
            ],
        )

    def test_execute_dialogue_route_returns_to_idle_even_when_delivery_reports_false(self) -> None:
        assistant = _FakeAssistant(deliver_ok=False)
        flow = DialogueFlowOrchestrator(assistant)

        handled = flow.execute_dialogue_route(self._build_route(), "en")

        self.assertTrue(handled)
        self.assertEqual(
            assistant.ai_broker_calls,
            [
                ("conversation", "dialogue_route_started:conversation"),
                ("recovery", "dialogue_route_finished:conversation|idle_baseline"),
            ],
        )


if __name__ == "__main__":
    unittest.main()