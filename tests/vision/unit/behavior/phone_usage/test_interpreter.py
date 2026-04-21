from __future__ import annotations

import unittest

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.behavior.phone_usage import PhoneUsageInterpreter
from modules.devices.vision.perception import BoundingBox, ObjectDetection, PerceptionSnapshot, SceneContext


class PhoneUsageInterpreterTests(unittest.TestCase):
    def test_phone_usage_is_active_when_phone_is_visible_in_handheld_zone(self) -> None:
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            objects=(
                ObjectDetection(
                    label="phone",
                    bounding_box=BoundingBox(left=500, top=420, right=660, bottom=650),
                    confidence=0.9,
                ),
            ),
            scene=SceneContext(handheld_candidate_count=1),
        )

        signal = PhoneUsageInterpreter().interpret(
            perception=perception,
            presence=ActivitySignal(active=True, confidence=0.9),
        )

        self.assertTrue(signal.active)
        self.assertIn("handheld_candidate_visible", signal.reasons)
        self.assertIn("phone_object_detected", signal.reasons)


if __name__ == "__main__":
    unittest.main()