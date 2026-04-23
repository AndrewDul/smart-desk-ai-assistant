from __future__ import annotations

import unittest

from modules.runtime.ai_broker import AiBrokerMode, AiBrokerService


class _FakeClock:
    def __init__(self, initial_now: float = 100.0) -> None:
        self.now = float(initial_now)

    def __call__(self) -> float:
        return self.now


class _FakeVisionBackend:
    def __init__(self) -> None:
        self.current_cadence_hz = 2.0
        self.cadence_calls: list[float] = []

    def set_object_detection_cadence_hz(self, hz: float) -> bool:
        self.current_cadence_hz = float(hz)
        self.cadence_calls.append(float(hz))
        return True

    def object_detector_status(self) -> dict[str, object]:
        return {
            "cadence_hz": self.current_cadence_hz,
            "paused": self.current_cadence_hz <= 0.0,
        }


class _PassiveVisionBackend:
    pass


class AiBrokerServiceTests(unittest.TestCase):
    def test_conversation_answer_mode_reduces_heavy_lane_cadence(self) -> None:
        clock = _FakeClock()
        vision = _FakeVisionBackend()
        service = AiBrokerService(
            vision_backend=vision,
            settings={},
            clock=clock,
        )

        snapshot = service.enter_conversation_answer_mode(
            reason="voice_turn_started",
        )

        self.assertEqual(snapshot["mode"], "conversation_answer")
        self.assertEqual(snapshot["owner"], "answer_path")
        self.assertAlmostEqual(
            snapshot["profile"]["heavy_lane_cadence_hz"],
            0.5,
            places=3,
        )
        self.assertEqual(vision.cadence_calls, [0.5])

    def test_vision_action_mode_increases_heavy_lane_cadence(self) -> None:
        clock = _FakeClock()
        vision = _FakeVisionBackend()
        service = AiBrokerService(
            vision_backend=vision,
            settings={},
            clock=clock,
        )

        snapshot = service.enter_vision_action_mode(
            reason="visual_task_started",
        )

        self.assertEqual(snapshot["mode"], "vision_action")
        self.assertEqual(snapshot["owner"], "vision_path")
        self.assertAlmostEqual(
            snapshot["profile"]["heavy_lane_cadence_hz"],
            6.0,
            places=3,
        )
        self.assertEqual(vision.cadence_calls, [6.0])

    def test_focus_sentinel_mode_uses_monitor_profile(self) -> None:
        clock = _FakeClock()
        vision = _FakeVisionBackend()
        service = AiBrokerService(
            vision_backend=vision,
            settings={},
            clock=clock,
        )

        snapshot = service.enter_focus_sentinel_mode(
            reason="monitor_mode_started",
        )

        self.assertEqual(snapshot["mode"], "focus_sentinel")
        self.assertEqual(snapshot["owner"], "monitor_path")
        self.assertAlmostEqual(
            snapshot["profile"]["heavy_lane_cadence_hz"],
            1.0,
            places=3,
        )
        self.assertEqual(vision.cadence_calls, [1.0])

    def test_recovery_window_returns_to_idle_baseline_after_deadline(self) -> None:
        clock = _FakeClock()
        vision = _FakeVisionBackend()
        service = AiBrokerService(
            vision_backend=vision,
            settings={},
            clock=clock,
        )

        service.enter_conversation_answer_mode(reason="voice_turn_started")
        recovery = service.enter_recovery_window(
            reason="voice_turn_finished",
            return_to_mode=AiBrokerMode.IDLE_BASELINE,
            seconds=1.5,
        )

        self.assertEqual(recovery["mode"], "recovery_window")
        self.assertTrue(recovery["recovery_window_active"])
        self.assertEqual(vision.cadence_calls, [0.5, 1.0])

        clock.now += 2.0
        after_tick = service.tick()

        self.assertEqual(after_tick["mode"], "idle_baseline")
        self.assertFalse(after_tick["recovery_window_active"])
        self.assertEqual(vision.cadence_calls, [0.5, 1.0, 2.0])

    def test_passive_backend_does_not_break_state_model(self) -> None:
        clock = _FakeClock()
        service = AiBrokerService(
            vision_backend=_PassiveVisionBackend(),
            settings={},
            clock=clock,
        )

        snapshot = service.enter_idle_baseline(reason="boot_baseline")

        self.assertEqual(snapshot["mode"], "idle_baseline")
        self.assertFalse(snapshot["vision_control_available"])
        self.assertFalse(snapshot["metadata"]["vision_profile_applied"])
        self.assertIsNone(snapshot["last_error"])


if __name__ == "__main__":
    unittest.main()