from __future__ import annotations

import unittest

from modules.devices.vision.behavior.presence import PresenceInterpreter
from modules.devices.vision.perception import BoundingBox, PerceptionSnapshot, PersonDetection, SceneContext


class PresenceInterpreterTests(unittest.TestCase):
    def test_presence_is_active_when_person_is_detected(self) -> None:
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            people=(
                PersonDetection(
                    bounding_box=BoundingBox(left=300, top=120, right=850, bottom=700),
                    confidence=0.93,
                ),
            ),
            scene=SceneContext(desk_zone_people_count=1),
        )

        signal = PresenceInterpreter().interpret(perception)

        self.assertTrue(signal.active)
        self.assertGreaterEqual(signal.confidence, 0.9)
        self.assertIn("person_detected", signal.reasons)
        self.assertIn("person_in_desk_zone", signal.reasons)


if __name__ == "__main__":
    unittest.main()