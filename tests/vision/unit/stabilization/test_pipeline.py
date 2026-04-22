from __future__ import annotations

import unittest

from modules.devices.vision.behavior import ActivitySignal, BehaviorSnapshot
from modules.devices.vision.stabilization import BehaviorStabilizer


class BehaviorStabilizerTests(unittest.TestCase):
    def test_presence_requires_two_positive_hits_to_turn_on(self) -> None:
        stabilizer = BehaviorStabilizer(
            enabled=True,
            activation_hits=2,
            deactivation_hits=2,
            hold_seconds=1.25,
        )

        first = stabilizer.stabilize(
            BehaviorSnapshot(
                presence=ActivitySignal(active=True, confidence=0.9),
            ),
            captured_at=10.0,
        )
        second = stabilizer.stabilize(
            BehaviorSnapshot(
                presence=ActivitySignal(active=True, confidence=0.9),
            ),
            captured_at=10.5,
        )

        self.assertFalse(first.presence.active)
        self.assertTrue(second.presence.active)

    def test_presence_hold_keeps_signal_active_for_short_drop(self) -> None:
        stabilizer = BehaviorStabilizer(
            enabled=True,
            activation_hits=1,
            deactivation_hits=2,
            hold_seconds=1.25,
        )

        active = stabilizer.stabilize(
            BehaviorSnapshot(
                presence=ActivitySignal(active=True, confidence=0.9),
            ),
            captured_at=20.0,
        )
        held = stabilizer.stabilize(
            BehaviorSnapshot(
                presence=ActivitySignal(active=False, confidence=0.0),
            ),
            captured_at=20.6,
        )

        self.assertTrue(active.presence.active)
        self.assertTrue(held.presence.active)
        self.assertIn("stability_hold_active", held.presence.reasons)

    def test_presence_turns_off_after_enough_negative_hits_outside_hold(self) -> None:
        stabilizer = BehaviorStabilizer(
            enabled=True,
            activation_hits=1,
            deactivation_hits=2,
            hold_seconds=0.5,
        )

        stabilizer.stabilize(
            BehaviorSnapshot(
                presence=ActivitySignal(active=True, confidence=0.9),
            ),
            captured_at=30.0,
        )
        first_drop = stabilizer.stabilize(
            BehaviorSnapshot(
                presence=ActivitySignal(active=False, confidence=0.0),
            ),
            captured_at=31.0,
        )
        second_drop = stabilizer.stabilize(
            BehaviorSnapshot(
                presence=ActivitySignal(active=False, confidence=0.0),
            ),
            captured_at=31.7,
        )

        self.assertTrue(first_drop.presence.active)
        self.assertFalse(second_drop.presence.active)


if __name__ == "__main__":
    unittest.main()