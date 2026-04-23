from __future__ import annotations

import unittest

from modules.core.assistant_impl.ai_broker_mixin import CoreAssistantAiBrokerMixin


class _FakeBroker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def enter_idle_baseline(self, *, reason: str = "") -> dict[str, object]:
        self.calls.append(("idle", reason))
        return {
            "mode": "idle_baseline",
            "owner": "balanced",
            "profile": {
                "heavy_lane_cadence_hz": 2.0,
                "keep_fast_lane_alive": True,
                "llm_priority": "normal",
                "notes": [],
            },
        }

    def enter_conversation_answer_mode(self, *, reason: str = "") -> dict[str, object]:
        self.calls.append(("conversation", reason))
        return {
            "mode": "conversation_answer",
            "owner": "answer_path",
            "profile": {
                "heavy_lane_cadence_hz": 0.5,
                "keep_fast_lane_alive": True,
                "llm_priority": "high",
                "notes": [],
            },
        }

    def enter_vision_action_mode(self, *, reason: str = "") -> dict[str, object]:
        self.calls.append(("vision", reason))
        return {
            "mode": "vision_action",
            "owner": "vision_path",
            "profile": {
                "heavy_lane_cadence_hz": 6.0,
                "keep_fast_lane_alive": True,
                "llm_priority": "low",
                "notes": [],
            },
        }

    def enter_focus_sentinel_mode(self, *, reason: str = "") -> dict[str, object]:
        self.calls.append(("focus", reason))
        return {
            "mode": "focus_sentinel",
            "owner": "monitor_path",
            "profile": {
                "heavy_lane_cadence_hz": 1.0,
                "keep_fast_lane_alive": True,
                "llm_priority": "low",
                "notes": [],
            },
        }


class _Host(CoreAssistantAiBrokerMixin):
    def __init__(self) -> None:
        self.ai_broker = _FakeBroker()
        self._last_ai_broker_snapshot: dict[str, object] = {}


class CoreAssistantAiBrokerMixinTests(unittest.TestCase):
    def test_enter_conversation_answer_mode_updates_snapshot(self) -> None:
        host = _Host()

        snapshot = host._enter_ai_broker_conversation_answer_mode(
            reason="dialogue_route_started:conversation",
        )

        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["mode"], "conversation_answer")
        self.assertEqual(host.ai_broker.calls, [("conversation", "dialogue_route_started:conversation")])
        self.assertEqual(host._last_ai_broker_snapshot["owner"], "answer_path")

    def test_enter_idle_baseline_updates_snapshot(self) -> None:
        host = _Host()

        snapshot = host._enter_ai_broker_idle_baseline(
            reason="dialogue_route_finished:conversation",
        )

        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["mode"], "idle_baseline")
        self.assertEqual(host.ai_broker.calls, [("idle", "dialogue_route_finished:conversation")])
        self.assertEqual(host._last_ai_broker_snapshot["owner"], "balanced")

    def test_enter_vision_action_mode_updates_snapshot(self) -> None:
        host = _Host()

        snapshot = host._enter_ai_broker_vision_action_mode(
            reason="action_route_started:look_direction",
        )

        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["mode"], "vision_action")
        self.assertEqual(host.ai_broker.calls, [("vision", "action_route_started:look_direction")])
        self.assertEqual(host._last_ai_broker_snapshot["owner"], "vision_path")

    def test_enter_focus_sentinel_mode_updates_snapshot(self) -> None:
        host = _Host()

        snapshot = host._enter_ai_broker_focus_sentinel_mode(
            reason="focus_timer_started",
        )

        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["mode"], "focus_sentinel")
        self.assertEqual(host.ai_broker.calls, [("focus", "focus_timer_started")])
        self.assertEqual(host._last_ai_broker_snapshot["owner"], "monitor_path")


if __name__ == "__main__":
    unittest.main()