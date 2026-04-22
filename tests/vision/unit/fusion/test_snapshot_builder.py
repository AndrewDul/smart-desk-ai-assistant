from __future__ import annotations

import unittest

from modules.devices.vision.behavior import ActivitySignal, BehaviorSnapshot
from modules.devices.vision.capture.frame_packet import FramePacket
from modules.devices.vision.fusion import build_camera_only_observation, build_vision_observation
from modules.devices.vision.perception import (
    BoundingBox,
    FaceDetection,
    ObjectDetection,
    PerceptionSnapshot,
    PersonDetection,
    SceneContext,
)
from modules.devices.vision.sessions import ActivitySessionSnapshot, VisionSessionSnapshot


class SnapshotBuilderTests(unittest.TestCase):
    def test_builds_camera_observation_without_perception(self) -> None:
        packet = FramePacket(
            pixels=[[0]],
            width=1280,
            height=720,
            channels=3,
            backend_label="picamera2",
            metadata={"camera_index": 0},
        )

        observation = build_camera_only_observation(packet)

        self.assertTrue(observation.detected)
        self.assertFalse(observation.user_present)
        self.assertFalse(observation.computer_work_likely)
        self.assertEqual(observation.labels, ["camera_online", "capture_backend:picamera2"])
        self.assertEqual(observation.metadata["frame_width"], 1280)
        self.assertEqual(observation.metadata["frame_height"], 720)
        self.assertEqual(observation.metadata["capture_backend"], "picamera2")
        self.assertEqual(observation.metadata["sessions"]["presence"]["current_active_seconds"], 0.0)

    def test_builds_semantic_observation_from_perception_behavior_and_sessions(self) -> None:
        packet = FramePacket(
            pixels=[[0]],
            width=1280,
            height=720,
            channels=3,
            backend_label="picamera2",
        )
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            people=(
                PersonDetection(
                    bounding_box=BoundingBox(left=400, top=250, right=860, bottom=710),
                    confidence=0.91,
                ),
            ),
            faces=(
                FaceDetection(
                    bounding_box=BoundingBox(left=520, top=120, right=640, bottom=280),
                    confidence=0.83,
                ),
            ),
            objects=(
                ObjectDetection(
                    label="laptop",
                    bounding_box=BoundingBox(left=350, top=160, right=930, bottom=430),
                    confidence=0.88,
                ),
            ),
            scene=SceneContext(
                desk_zone_people_count=1,
                engagement_face_count=1,
                screen_candidate_count=1,
                handheld_candidate_count=0,
                labels=("person_in_desk_zone", "face_in_engagement_zone", "screen_candidate_visible"),
            ),
        )
        behavior = BehaviorSnapshot(
            presence=ActivitySignal(active=True, confidence=0.91, reasons=("person_detected", "face_detected")),
            desk_activity=ActivitySignal(active=True, confidence=0.8, reasons=("desk_zone_occupied", "face_in_engagement_zone")),
            computer_work=ActivitySignal(active=True, confidence=0.82, reasons=("computer_object_detected",)),
            phone_usage=ActivitySignal(active=False, confidence=0.0, reasons=()),
            study_activity=ActivitySignal(active=True, confidence=0.78, reasons=("computer_work_confirmed",)),
        )
        sessions = VisionSessionSnapshot(
            presence=ActivitySessionSnapshot(
                active=True,
                state="active",
                current_active_seconds=180.0,
                total_active_seconds=540.0,
                activations=2,
                last_started_at=100.0,
            ),
            desk_activity=ActivitySessionSnapshot(
                active=True,
                state="active",
                current_active_seconds=175.0,
                total_active_seconds=500.0,
                activations=2,
            ),
            computer_work=ActivitySessionSnapshot(
                active=True,
                state="active",
                current_active_seconds=160.0,
                total_active_seconds=470.0,
                activations=2,
            ),
            phone_usage=ActivitySessionSnapshot(
                active=False,
                state="inactive",
                current_active_seconds=0.0,
                last_active_streak_seconds=22.0,
                total_active_seconds=100.0,
                activations=3,
            ),
            study_activity=ActivitySessionSnapshot(
                active=True,
                state="active",
                current_active_seconds=140.0,
                total_active_seconds=430.0,
                activations=2,
            ),
        )

        observation = build_vision_observation(
            packet,
            perception=perception,
            behavior=behavior,
            sessions=sessions,
        )

        self.assertTrue(observation.detected)
        self.assertTrue(observation.user_present)
        self.assertTrue(observation.desk_active)
        self.assertTrue(observation.computer_work_likely)
        self.assertTrue(observation.studying_likely)
        self.assertFalse(observation.on_phone_likely)
        self.assertIn("object:laptop", observation.labels)
        self.assertIn("person_in_desk_zone", observation.labels)
        self.assertIn("face_in_engagement_zone", observation.labels)
        self.assertIn("face_detected", observation.labels)
        self.assertIn("behavior:computer_work", observation.labels)
        self.assertIn("session:presence_active", observation.labels)
        self.assertIn("session:study_active", observation.labels)
        self.assertEqual(observation.metadata["perception"]["people_count"], 1)
        self.assertEqual(observation.metadata["perception"]["face_count"], 1)
        self.assertEqual(observation.metadata["perception"]["engagement_face_count"], 1)
        self.assertEqual(observation.metadata["behavior"]["computer_work"]["active"], True)
        self.assertEqual(observation.metadata["sessions"]["presence"]["current_active_seconds"], 180.0)
        self.assertEqual(observation.metadata["sessions"]["phone_usage"]["last_active_streak_seconds"], 22.0)
        self.assertAlmostEqual(observation.confidence, 0.91, places=2)


if __name__ == "__main__":
    unittest.main()