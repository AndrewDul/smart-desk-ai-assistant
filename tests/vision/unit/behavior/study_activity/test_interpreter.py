from __future__ import annotations

import unittest

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.behavior.study_activity import StudyActivityInterpreter
from modules.devices.vision.perception import PerceptionSnapshot, SceneContext


class StudyActivityInterpreterTests(unittest.TestCase):
    def test_study_activity_is_active_when_desk_and_computer_are_active_without_phone(self) -> None:
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            scene=SceneContext(screen_candidate_count=1),
        )

        signal = StudyActivityInterpreter().interpret(
            perception=perception,
            presence=ActivitySignal(active=True, confidence=0.9),
            desk_activity=ActivitySignal(active=True, confidence=0.85),
            computer_work=ActivitySignal(active=True, confidence=0.8),
            phone_usage=ActivitySignal(active=False, confidence=0.0),
        )

        self.assertTrue(signal.active)
        self.assertIn("desk_activity_confirmed", signal.reasons)
        self.assertIn("computer_work_confirmed", signal.reasons)
        self.assertIn("phone_not_detected", signal.reasons)


if __name__ == "__main__":
    unittest.main()