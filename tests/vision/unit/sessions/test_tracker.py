from __future__ import annotations

import unittest

from modules.devices.vision.behavior import ActivitySignal, BehaviorSnapshot
from modules.devices.vision.sessions import VisionSessionTracker


class VisionSessionTrackerTests(unittest.TestCase):
    def test_tracker_accumulates_presence_session_time(self) -> None:
        tracker = VisionSessionTracker()

        first = tracker.update(
            BehaviorSnapshot(
                presence=ActivitySignal(active=True, confidence=0.9),
            ),
            captured_at=10.0,
        )
        second = tracker.update(
            BehaviorSnapshot(
                presence=ActivitySignal(active=True, confidence=0.9),
            ),
            captured_at=16.5,
        )
        third = tracker.update(
            BehaviorSnapshot(
                presence=ActivitySignal(active=False, confidence=0.0),
            ),
            captured_at=20.0,
        )

        self.assertTrue(first.presence.active)
        self.assertEqual(first.presence.activations, 1)
        self.assertAlmostEqual(second.presence.current_active_seconds, 6.5, places=2)
        self.assertAlmostEqual(second.presence.total_active_seconds, 6.5, places=2)
        self.assertFalse(third.presence.active)
        self.assertAlmostEqual(third.presence.last_active_streak_seconds, 10.0, places=2)
        self.assertAlmostEqual(third.presence.total_active_seconds, 10.0, places=2)
        self.assertEqual(third.presence.state, "inactive")


if __name__ == "__main__":
    unittest.main()