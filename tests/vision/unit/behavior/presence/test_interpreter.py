from __future__ import annotations

import unittest

from modules.devices.vision.behavior.presence import PresenceInterpreter
from modules.devices.vision.perception import (
    BoundingBox,
    FaceDetection,
    PerceptionSnapshot,
    PersonDetection,
    SceneContext,
)


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

    def test_presence_is_active_when_face_is_detected(self) -> None:
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            faces=(
                FaceDetection(
                    bounding_box=BoundingBox(left=500, top=140, right=620, bottom=290),
                    confidence=0.82,
                ),
            ),
        )

        signal = PresenceInterpreter().interpret(perception)

        self.assertTrue(signal.active)
        self.assertGreaterEqual(signal.confidence, 0.8)
        self.assertIn("face_detected", signal.reasons)
        self.assertEqual(signal.metadata["face_count"], 1)


if __name__ == "__main__":
    unittest.main()