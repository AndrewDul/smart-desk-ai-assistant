from __future__ import annotations

import unittest

from modules.core.assistant_impl.ai_broker_mixin import CoreAssistantAiBrokerMixin
from modules.runtime.ai_broker import AiBrokerMode


class _FakeBroker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object | None]] = []
        self.current_mode = "idle_baseline"

    def enter_idle_baseline(self, *, reason: str = "") -> dict[str, object]:
        self.calls.append(("idle", reason, None))
        self.current_mode = "idle_baseline"
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
        self.calls.append(("conversation", reason, None))
        self.current_mode = "conversation_answer"
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
        self.calls.append(("vision", reason, None))
        self.current_mode = "vision_action"
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
        self.calls.append(("focus", reason, None))
        self.current_mode = "focus_sentinel"
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

    def enter_recovery_window(
        self,
        *,
        reason: str = "",
        return_to_mode=AiBrokerMode.IDLE_BASELINE,
        seconds: float | None = None,
    ) -> dict[str, object]:
        self.calls.append(("recovery", reason, return_to_mode))
        self.current_mode = "recovery_window"
        return {
            "mode": "recovery_window",
            "owner": "balanced",
            "profile": {
                "heavy_lane_cadence_hz": 1.0,
                "keep_fast_lane_alive": True,
                "llm_priority": "normal",
                "notes": [],
            },
            "recovery_window_active": True,
            "recovery_until_monotonic": seconds,
        }

    def tick(self) -> dict[str, object]:
        return {
            "mode": self.current_mode,
            "owner": "balanced",
            "profile": {
                "heavy_lane_cadence_hz": 1.0,
                "keep_fast_lane_alive": True,
                "llm_priority": "normal",
                "notes": [],
            },
        }

    def status(self) -> dict[str, object]:
        return {
            "mode": self.current_mode,
            "owner": "balanced",
            "profile": {
                "heavy_lane_cadence_hz": 1.0,
                "keep_fast_lane_alive": True,
                "llm_priority": "normal",
                "notes": [],
            },
            "vision_control_available": True,
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
        self.assertEqual(
            host.ai_broker.calls,
            [("conversation", "dialogue_route_started:conversation", None)],
        )
        self.assertEqual(host._last_ai_broker_snapshot["owner"], "answer_path")

    def test_enter_idle_baseline_updates_snapshot(self) -> None:
        host = _Host()

        snapshot = host._enter_ai_broker_idle_baseline(
            reason="dialogue_route_finished:conversation",
        )

        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["mode"], "idle_baseline")
        self.assertEqual(
            host.ai_broker.calls,
            [("idle", "dialogue_route_finished:conversation", None)],
        )
        self.assertEqual(host._last_ai_broker_snapshot["owner"], "balanced")

    def test_enter_vision_action_mode_updates_snapshot(self) -> None:
        host = _Host()

        snapshot = host._enter_ai_broker_vision_action_mode(
            reason="action_route_started:look_direction",
        )

        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["mode"], "vision_action")
        self.assertEqual(
            host.ai_broker.calls,
            [("vision", "action_route_started:look_direction", None)],
        )
        self.assertEqual(host._last_ai_broker_snapshot["owner"], "vision_path")

    def test_enter_focus_sentinel_mode_updates_snapshot(self) -> None:
        host = _Host()

        snapshot = host._enter_ai_broker_focus_sentinel_mode(
            reason="focus_timer_started",
        )

        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["mode"], "focus_sentinel")
        self.assertEqual(
            host.ai_broker.calls,
            [("focus", "focus_timer_started", None)],
        )
        self.assertEqual(host._last_ai_broker_snapshot["owner"], "monitor_path")

    def test_enter_recovery_window_updates_snapshot(self) -> None:
        host = _Host()

        snapshot = host._enter_ai_broker_recovery_window(
            reason="dialogue_route_finished:conversation",
            return_to_mode="idle_baseline",
        )

        self.assertIsInstance(snapshot, dict)
        self.assertEqual(snapshot["mode"], "recovery_window")
        self.assertEqual(
            host.ai_broker.calls,
            [("recovery", "dialogue_route_finished:conversation", AiBrokerMode.IDLE_BASELINE)],
        )

    def test_ai_broker_status_snapshot_reads_status_payload(self) -> None:
        host = _Host()

        snapshot = host._ai_broker_status_snapshot()

        self.assertEqual(snapshot["mode"], "idle_baseline")
        self.assertTrue(snapshot["vision_control_available"])


if __name__ == "__main__":
    unittest.main()