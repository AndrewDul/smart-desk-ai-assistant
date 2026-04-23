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


    def test_study_activity_threshold_can_be_tightened_from_mapping(self) -> None:
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            scene=SceneContext(screen_candidate_count=1),
        )

        signal = StudyActivityInterpreter.from_mapping(
            {
                "study_activity_active_threshold": 0.9,
            }
        ).interpret(
            perception=perception,
            presence=ActivitySignal(active=True, confidence=0.9),
            desk_activity=ActivitySignal(active=True, confidence=0.7),
            computer_work=ActivitySignal(active=True, confidence=0.8),
            phone_usage=ActivitySignal(active=False, confidence=0.0),
        )

        self.assertFalse(signal.active)
        self.assertEqual(signal.metadata["active_threshold"], 0.9)

    def test_study_activity_requires_study_evidence_when_enabled(self) -> None:
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            scene=SceneContext(screen_candidate_count=0),
        )

        signal = StudyActivityInterpreter.from_mapping(
            {
                "study_activity_require_desk_or_computer_evidence": True,
            }
        ).interpret(
            perception=perception,
            presence=ActivitySignal(active=True, confidence=0.9),
            desk_activity=ActivitySignal(active=False, confidence=0.1),
            computer_work=ActivitySignal(active=False, confidence=0.1),
            phone_usage=ActivitySignal(active=False, confidence=0.0),
        )

        self.assertFalse(signal.active)
        self.assertEqual(signal.reasons, ("study_evidence_missing",))
        self.assertEqual(signal.metadata["inference_mode"], "inactive_missing_study_evidence")

if __name__ == "__main__":
    unittest.main()