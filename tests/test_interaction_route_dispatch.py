from __future__ import annotations

import unittest
from types import SimpleNamespace

from modules.core.assistant_impl.interaction_mixin import CoreAssistantInteractionMixin
from modules.runtime.contracts import RouteDecision, RouteKind


class _FakeInterruptController:
    def clear(self) -> None:
        return None


class _FakeVoiceSession:
    def transition_to_routing(self, *, detail: str = "") -> None:
        self.detail = detail


class _FakeBenchmarkService:
    def __init__(self) -> None:
        self.route_events: list[dict[str, object]] = []

    def begin_turn(self, *, user_text: str, language: str, input_source: str = "voice") -> str:
        return "turn-benchmark-1"

    def note_route_resolved(self, *, route_kind: str, primary_intent: str, confidence: float) -> None:
        self.route_events.append(
            {
                "route_kind": route_kind,
                "primary_intent": primary_intent,
                "confidence": confidence,
            }
        )


class _FakeAssistant(CoreAssistantInteractionMixin):
    def __init__(self, route: RouteDecision, *, fast_lane_result=None) -> None:
        self.interrupt_controller = _FakeInterruptController()
        self.voice_session = _FakeVoiceSession()
        self.turn_benchmark_service = _FakeBenchmarkService()
        self.command_flow = SimpleNamespace(log_route_decision=lambda route: None)
        self.route = route
        self.fast_lane_result = fast_lane_result
        self.last_language = "en"
        self.pending_confirmation = None
        self._last_input_capture = {
            "input_source": "voice",
            "language": "en",
            "backend_label": "faster-whisper",
            "mode": "command",
            "phase": "inline_command_after_wake",
            "metadata": {"capture_origin": "test"},
        }
        self.route_calls = 0
        self.dispatched: list[tuple[str, str]] = []
        self.finished_telemetry = None

    def _prepare_command(self, text: str, **kwargs):
        return {
            "ignore": False,
            "language": "en",
            "source": SimpleNamespace(value="voice"),
            "capture_phase": "inline_command_after_wake",
            "capture_mode": "command",
            "capture_backend": "faster-whisper",
            "routing_text": text,
            "normalized_text": text.lower(),
            "already_remembered": True,
            "cancel_requested": False,
        }

    def _commit_language(self, language: str) -> str:
        return str(language or "en")

    def _handle_pending_state(self, prepared):
        return None

    def _handle_fast_lane(self, prepared):
        return self.fast_lane_result

    def _thinking_ack_start(self, **kwargs) -> None:
        return None

    def _thinking_ack_stop(self) -> None:
        return None

    def _route_command(self, text: str, **kwargs):
        self.route_calls += 1
        return self.route

    def _coerce_route_decision(self, routed, **kwargs):
        return routed

    def _execute_action_route(self, route, language: str) -> bool:
        self.dispatched.append(("action", language))
        return True

    def _handle_mixed_route(self, route, language: str) -> bool:
        self.dispatched.append(("mixed", language))
        return True

    def _handle_conversation_route(self, route, language: str) -> bool:
        self.dispatched.append(("conversation", language))
        return True

    def _handle_unclear_route(self, route, language: str) -> bool:
        self.dispatched.append(("unclear", language))
        return True

    def _finish_turn_telemetry(self, telemetry):
        self.finished_telemetry = dict(telemetry)


class InteractionRouteDispatchTests(unittest.TestCase):
    def _route(self, kind: RouteKind, primary_intent: str = "time_query") -> RouteDecision:
        return RouteDecision(
            turn_id="turn-route-dispatch",
            raw_text="what time is it",
            normalized_text="what time is it",
            language="en",
            kind=kind,
            confidence=0.93,
            primary_intent=primary_intent,
            intents=[],
            conversation_topics=["time"],
            tool_invocations=[],
            notes=["unit_test"],
            metadata={
                "capture_phase": "inline_command_after_wake",
                "capture_mode": "command",
                "capture_backend": "faster-whisper",
            },
        )

    def test_handle_command_dispatches_action_route_and_records_route_telemetry(self) -> None:
        assistant = _FakeAssistant(self._route(RouteKind.ACTION))

        handled = assistant.handle_command("what time is it")

        self.assertTrue(handled)
        self.assertEqual(assistant.dispatched, [("action", "en")])
        self.assertEqual(assistant.route_calls, 1)
        self.assertEqual(assistant.finished_telemetry["result"], "action_route")
        self.assertEqual(assistant.finished_telemetry["route_kind"], "action")
        self.assertEqual(assistant.turn_benchmark_service.route_events[0]["primary_intent"], "time_query")

    def test_handle_command_dispatches_mixed_route(self) -> None:
        assistant = _FakeAssistant(self._route(RouteKind.MIXED, primary_intent="support_request"))

        handled = assistant.handle_command("help me and set a timer")

        self.assertTrue(handled)
        self.assertEqual(assistant.dispatched, [("mixed", "en")])
        self.assertEqual(assistant.finished_telemetry["result"], "mixed_route")
        self.assertEqual(assistant.finished_telemetry["route_kind"], "mixed")

    def test_handle_command_stops_before_router_when_fast_lane_handles_request(self) -> None:
        assistant = _FakeAssistant(self._route(RouteKind.CONVERSATION), fast_lane_result=True)

        handled = assistant.handle_command("what time is it")

        self.assertTrue(handled)
        self.assertEqual(assistant.route_calls, 0)
        self.assertEqual(assistant.dispatched, [])
        self.assertEqual(assistant.finished_telemetry["result"], "fast_lane")


if __name__ == "__main__":
    unittest.main()