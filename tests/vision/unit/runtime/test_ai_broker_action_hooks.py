from __future__ import annotations

import unittest

from modules.core.flows.action_flow.orchestrator import ActionFlowOrchestrator
from modules.runtime.contracts import EntityValue, IntentMatch, RouteDecision, RouteKind


class _FakePanTiltBackend:
    def __init__(self) -> None:
        self.moves: list[str] = []

    def move_direction(self, direction: str):
        self.moves.append(direction)
        return {
            "ok": True,
            "pan_angle": 90.0,
            "tilt_angle": 90.0,
            "direction": direction,
        }


class _FakeAssistant:
    def __init__(self) -> None:
        self.settings = {
            "streaming": {"max_display_chars_per_line": 20},
            "system": {"allow_shutdown_commands": True},
        }
        self.default_focus_minutes = 25
        self.default_break_minutes = 5
        self.pending_follow_up = None
        self.pan_tilt = _FakePanTiltBackend()
        self.ai_broker_calls: list[tuple[str, str]] = []
        self.last_response = None

    def _normalize_lang(self, language: str) -> str:
        return str(language or "en").strip().lower() or "en"

    def _enter_ai_broker_vision_action_mode(self, *, reason: str = "") -> dict[str, object]:
        self.ai_broker_calls.append(("vision", reason))
        return {
            "mode": "vision_action",
            "owner": "vision_path",
            "profile": {"heavy_lane_cadence_hz": 6.0},
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
        self.last_response = {
            "source": source,
            "remember": remember,
            "extra_metadata": dict(extra_metadata or {}),
            "text": [chunk.text for chunk in plan.chunks],
        }
        return True


class AiBrokerActionHookTests(unittest.TestCase):
    def _look_route(self) -> RouteDecision:
        route = RouteDecision(
            turn_id="turn-action-vision-1",
            raw_text="look left",
            normalized_text="look left",
            language="en",
            kind=RouteKind.ACTION,
            confidence=0.94,
            primary_intent="look_direction",
            intents=[IntentMatch(name="look_direction", confidence=0.94)],
            conversation_topics=[],
            tool_invocations=[],
            notes=[],
            metadata={
                "capture_phase": "inline_command_after_wake",
                "capture_mode": "command",
                "capture_backend": "faster-whisper",
                "parser_action": "look_direction",
            },
        )
        route.intents[0].entities.append(EntityValue(name="direction", value="left"))
        return route

    def _time_route(self) -> RouteDecision:
        return RouteDecision(
            turn_id="turn-action-time-1",
            raw_text="what time is it",
            normalized_text="what time is it",
            language="en",
            kind=RouteKind.ACTION,
            confidence=0.95,
            primary_intent="ask_time",
            intents=[IntentMatch(name="ask_time", confidence=0.95)],
            conversation_topics=["time"],
            tool_invocations=[],
            notes=[],
            metadata={
                "capture_phase": "inline_command_after_wake",
                "capture_mode": "command",
                "capture_backend": "faster-whisper",
                "parser_action": "ask_time",
            },
        )

    def test_visual_priority_action_enters_vision_mode_and_returns_to_idle(self) -> None:
        assistant = _FakeAssistant()
        flow = ActionFlowOrchestrator(assistant)

        handled = flow.execute(route=self._look_route(), language="en")

        self.assertTrue(handled)
        self.assertEqual(assistant.pan_tilt.moves, ["left"])
        self.assertEqual(
            assistant.ai_broker_calls,
            [
                ("vision", "action_route_started:look_direction"),
                ("recovery", "action_route_finished:look_direction|idle_baseline"),
            ],
        )

    def test_non_visual_action_does_not_switch_into_vision_mode(self) -> None:
        assistant = _FakeAssistant()
        flow = ActionFlowOrchestrator(assistant)

        handled = flow.execute(route=self._time_route(), language="en")

        self.assertTrue(handled)
        self.assertEqual(assistant.ai_broker_calls, [])


if __name__ == "__main__":
    unittest.main()