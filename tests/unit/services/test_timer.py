from __future__ import annotations

import threading
import time
import unittest

from modules.features.timer.service import TimerService


class TestSessionTimer(unittest.TestCase):
    def setUp(self) -> None:
        self.started_events: list[tuple[str, float]] = []
        self.finished_events: list[str] = []
        self.stopped_events: list[str] = []

        self.finished_signal = threading.Event()
        self.stopped_signal = threading.Event()

        self.timer = TimerService(
            on_started=self._on_started,
            on_finished=self._on_finished,
            on_stopped=self._on_stopped,
        )

    def _on_started(self, mode: str, minutes: float) -> None:
        self.started_events.append((mode, minutes))

    def _on_finished(self, mode: str) -> None:
        self.finished_events.append(mode)
        self.finished_signal.set()

    def _on_stopped(self, mode: str) -> None:
        self.stopped_events.append(mode)
        self.stopped_signal.set()

    def test_start_timer_successfully(self) -> None:
        ok, message = self.timer.start(0.05, "timer")

        self.assertTrue(ok)
        self.assertIn("started", message.lower())
        self.assertEqual(len(self.started_events), 1)
        self.assertEqual(self.started_events[0][0], "timer")

        status = self.timer.status()
        self.assertTrue(status["running"])
        self.assertEqual(status["mode"], "timer")
        self.assertGreater(status["remaining_seconds"], 0)
        self.assertGreater(status["started_at"], 0)
        self.assertGreater(status["ends_at"], status["started_at"])

        self.timer.stop()

    def test_cannot_start_second_timer_while_running(self) -> None:
        ok1, _ = self.timer.start(0.1, "focus")
        ok2, message2 = self.timer.start(0.1, "break")

        self.assertTrue(ok1)
        self.assertFalse(ok2)
        self.assertIn("already running", message2.lower())
        self.assertEqual(len(self.started_events), 1)
        self.assertEqual(self.started_events[0][0], "focus")

        self.timer.stop()

    def test_cannot_start_with_zero_or_negative_duration(self) -> None:
        for minutes in [0, -1]:
            with self.subTest(minutes=minutes):
                ok, message = self.timer.start(minutes, "timer")
                self.assertFalse(ok)
                self.assertIn("greater than zero", message.lower())

    def test_timer_finishes_and_calls_callback(self) -> None:
        ok, _ = self.timer.start(0.02, "timer")
        self.assertTrue(ok)

        finished = self.finished_signal.wait(timeout=3.0)
        self.assertTrue(finished, "Timer did not finish in time.")

        self.assertEqual(self.finished_events, ["timer"])

        status = self.timer.status()
        self.assertFalse(status["running"])
        self.assertIsNone(status["mode"])
        self.assertEqual(status["remaining_seconds"], 0)
        self.assertEqual(status["started_at"], 0.0)
        self.assertEqual(status["ends_at"], 0.0)

    def test_stop_timer_successfully(self) -> None:
        ok, _ = self.timer.start(0.2, "focus")
        self.assertTrue(ok)

        stopped_ok, stopped_message = self.timer.stop()
        self.assertTrue(stopped_ok)
        self.assertIn("stopped", stopped_message.lower())

        stopped = self.stopped_signal.wait(timeout=1.0)
        self.assertTrue(stopped, "Stop callback was not triggered.")

        self.assertEqual(self.stopped_events, ["focus"])

        status = self.timer.status()
        self.assertFalse(status["running"])
        self.assertIsNone(status["mode"])
        self.assertEqual(status["remaining_seconds"], 0)
        self.assertEqual(status["started_at"], 0.0)
        self.assertEqual(status["ends_at"], 0.0)

    def test_stop_returns_false_when_nothing_is_running(self) -> None:
        ok, message = self.timer.stop()

        self.assertFalse(ok)
        self.assertIn("no timer", message.lower())
        self.assertEqual(self.stopped_events, [])

    def test_remaining_seconds_decrease_over_time(self) -> None:
        ok, _ = self.timer.start(0.1, "timer")
        self.assertTrue(ok)

        first_status = self.timer.status()
        time.sleep(1.2)
        second_status = self.timer.status()

        self.assertTrue(first_status["running"])
        self.assertLessEqual(second_status["remaining_seconds"], first_status["remaining_seconds"])

        self.timer.stop()

    def test_focus_mode_finishes_correctly(self) -> None:
        ok, _ = self.timer.start(0.02, "focus")
        self.assertTrue(ok)

        finished = self.finished_signal.wait(timeout=3.0)
        self.assertTrue(finished, "Focus timer did not finish in time.")
        self.assertEqual(self.finished_events, ["focus"])

    def test_break_mode_finishes_correctly(self) -> None:
        ok, _ = self.timer.start(0.02, "break")
        self.assertTrue(ok)

        finished = self.finished_signal.wait(timeout=3.0)
        self.assertTrue(finished, "Break timer did not finish in time.")
        self.assertEqual(self.finished_events, ["break"])

    def test_stop_does_not_trigger_finished_callback(self) -> None:
        ok, _ = self.timer.start(0.2, "timer")
        self.assertTrue(ok)

        self.timer.stop()
        time.sleep(0.4)

        self.assertEqual(self.finished_events, [])
        self.assertEqual(self.stopped_events, ["timer"])

    def test_minimum_one_second_runtime_is_applied(self) -> None:
        ok, _ = self.timer.start(0.001, "timer")
        self.assertTrue(ok)

        status = self.timer.status()
        self.assertGreaterEqual(status["remaining_seconds"], 1)

        self.timer.stop()


if __name__ == "__main__":
    unittest.main()