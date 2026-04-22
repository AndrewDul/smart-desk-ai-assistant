from __future__ import annotations

import unittest

from modules.devices.vision.behavior.computer_work import ComputerWorkInterpreter
from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.perception import BoundingBox, FaceDetection, ObjectDetection, PerceptionSnapshot, SceneContext


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
        self.assertEqual(signal.metadata["inference_mode"], "hybrid")

    def test_computer_work_is_active_from_desk_face_proxy_without_object_detection(self) -> None:
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            scene=SceneContext(
                desk_zone_people_count=0,
                engagement_face_count=1,
                screen_candidate_count=0,
                handheld_candidate_count=0,
            ),
        )

        signal = ComputerWorkInterpreter().interpret(
            perception=perception,
            presence=ActivitySignal(active=True, confidence=0.88),
            desk_activity=ActivitySignal(active=True, confidence=0.76),
        )

        self.assertTrue(signal.active)
        self.assertIn("desk_activity_confirmed", signal.reasons)
        self.assertIn("face_engaged_at_desk", signal.reasons)
        self.assertIn("desk_screen_posture_proxy", signal.reasons)
        self.assertIn("no_phone_like_evidence", signal.reasons)
        self.assertEqual(signal.metadata["inference_mode"], "desk_face_proxy")

    def test_computer_work_is_suppressed_when_phone_like_evidence_is_present(self) -> None:
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            scene=SceneContext(
                engagement_face_count=1,
                handheld_candidate_count=1,
            ),
        )

        signal = ComputerWorkInterpreter().interpret(
            perception=perception,
            presence=ActivitySignal(active=True, confidence=0.91),
            desk_activity=ActivitySignal(active=True, confidence=0.80),
        )

        self.assertFalse(signal.active)
        self.assertIn("phone_like_evidence_present", signal.reasons)
        self.assertNotIn("desk_screen_posture_proxy", signal.reasons)

    def test_computer_work_is_not_activated_from_downward_attention_without_screen_evidence(self) -> None:
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            faces=(
                FaceDetection(
                    bounding_box=BoundingBox(left=520, top=250, right=700, bottom=520),
                    confidence=0.87,
                ),
            ),
            scene=SceneContext(
                engagement_face_count=1,
                screen_candidate_count=0,
                handheld_candidate_count=0,
            ),
        )

        signal = ComputerWorkInterpreter().interpret(
            perception=perception,
            presence=ActivitySignal(active=True, confidence=0.9),
            desk_activity=ActivitySignal(active=True, confidence=0.78),
        )

        self.assertFalse(signal.active)
        self.assertIn("downward_attention_proxy", signal.reasons)
        self.assertNotIn("desk_screen_posture_proxy", signal.reasons)
        self.assertEqual(signal.metadata["inference_mode"], "suppressed_downward_attention")


if __name__ == "__main__":
    unittest.main()