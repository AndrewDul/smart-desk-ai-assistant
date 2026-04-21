from __future__ import annotations

import unittest

from modules.devices.vision.behavior.computer_work import ComputerWorkInterpreter
from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.perception import BoundingBox, ObjectDetection, PerceptionSnapshot, SceneContext


class ComputerWorkInterpreterTests(unittest.TestCase):
    def test_computer_work_is_active_when_screen_and_laptop_are_visible(self) -> None:
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            objects=(
                ObjectDetection(
                    label="laptop",
                    bounding_box=BoundingBox(left=350, top=180, right=900, bottom=430),
                    confidence=0.88,
                ),
            ),
            scene=SceneContext(screen_candidate_count=1),
        )

        signal = ComputerWorkInterpreter().interpret(
            perception=perception,
            presence=ActivitySignal(active=True, confidence=0.9),
            desk_activity=ActivitySignal(active=True, confidence=0.8),
        )

        self.assertTrue(signal.active)
        self.assertIn("screen_candidate_visible", signal.reasons)
        self.assertIn("computer_object_detected", signal.reasons)


if __name__ == "__main__":
    unittest.main()