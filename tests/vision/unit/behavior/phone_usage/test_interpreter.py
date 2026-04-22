from __future__ import annotations

import unittest

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.behavior.phone_usage import PhoneUsageInterpreter
from modules.devices.vision.perception import BoundingBox, FaceDetection, ObjectDetection, PerceptionSnapshot, SceneContext


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
            desk_activity=ActivitySignal(active=True, confidence=0.8),
            computer_work=ActivitySignal(active=False, confidence=0.2),
        )

        self.assertTrue(signal.active)
        self.assertIn("handheld_candidate_visible", signal.reasons)
        self.assertIn("phone_object_detected", signal.reasons)
        self.assertTrue(signal.metadata["visual_phone_evidence"])
        self.assertEqual(signal.metadata["inference_mode"], "confirmed_phone_object")

    def test_phone_usage_is_not_active_from_downward_desk_proxy_without_object_detection(self) -> None:
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

        signal = PhoneUsageInterpreter().interpret(
            perception=perception,
            presence=ActivitySignal(active=True, confidence=0.9),
            desk_activity=ActivitySignal(active=True, confidence=0.78),
            computer_work=ActivitySignal(active=False, confidence=0.25),
        )

        self.assertFalse(signal.active)
        self.assertIn("phone_visual_evidence_missing", signal.reasons)
        self.assertIn("downward_attention_proxy", signal.reasons)
        self.assertEqual(signal.metadata["inference_mode"], "inactive_no_visual_evidence")
        self.assertFalse(signal.metadata["visual_phone_evidence"])

    def test_phone_usage_is_not_active_from_handheld_candidate_without_phone_object(self) -> None:
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            scene=SceneContext(
                engagement_face_count=1,
                handheld_candidate_count=1,
                screen_candidate_count=0,
            ),
        )

        signal = PhoneUsageInterpreter().interpret(
            perception=perception,
            presence=ActivitySignal(active=True, confidence=0.92),
            desk_activity=ActivitySignal(active=True, confidence=0.81),
            computer_work=ActivitySignal(active=False, confidence=0.20),
        )

        self.assertFalse(signal.active)
        self.assertIn("phone_visual_evidence_missing", signal.reasons)
        self.assertIn("handheld_candidate_visible", signal.reasons)
        self.assertEqual(signal.metadata["phone_object_count"], 0)

    def test_phone_usage_is_suppressed_when_computer_work_is_active(self) -> None:
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            faces=(
                FaceDetection(
                    bounding_box=BoundingBox(left=500, top=260, right=690, bottom=520),
                    confidence=0.88,
                ),
            ),
            objects=(
                ObjectDetection(
                    label="phone",
                    bounding_box=BoundingBox(left=650, top=420, right=760, bottom=650),
                    confidence=0.74,
                ),
            ),
            scene=SceneContext(
                engagement_face_count=1,
                screen_candidate_count=1,
                handheld_candidate_count=0,
            ),
        )

        signal = PhoneUsageInterpreter().interpret(
            perception=perception,
            presence=ActivitySignal(active=True, confidence=0.9),
            desk_activity=ActivitySignal(active=True, confidence=0.8),
            computer_work=ActivitySignal(active=True, confidence=0.72),
        )

        self.assertFalse(signal.active)
        self.assertIn("computer_work_active", signal.reasons)
        self.assertIn("screen_candidate_visible", signal.reasons)
        self.assertIn("phone_object_detected", signal.reasons)


if __name__ == "__main__":
    unittest.main()