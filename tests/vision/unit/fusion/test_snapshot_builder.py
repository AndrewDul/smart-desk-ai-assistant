from __future__ import annotations

import unittest

from modules.devices.vision.capture.frame_packet import FramePacket
from modules.devices.vision.fusion import build_camera_only_observation, build_vision_observation
from modules.devices.vision.perception import (
    BoundingBox,
    ObjectDetection,
    PerceptionSnapshot,
    PersonDetection,
    SceneContext,
)


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
        self.assertEqual(observation.labels, ["camera_online", "capture_backend:picamera2"])
        self.assertEqual(observation.metadata["frame_width"], 1280)
        self.assertEqual(observation.metadata["frame_height"], 720)
        self.assertEqual(observation.metadata["capture_backend"], "picamera2")

    def test_builds_semantic_observation_from_perception_snapshot(self) -> None:
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
            objects=(
                ObjectDetection(
                    label="laptop",
                    bounding_box=BoundingBox(left=350, top=160, right=930, bottom=430),
                    confidence=0.88,
                ),
            ),
            scene=SceneContext(
                desk_zone_people_count=1,
                screen_candidate_count=1,
                handheld_candidate_count=0,
                labels=("person_in_desk_zone", "screen_candidate_visible"),
            ),
        )

        observation = build_vision_observation(packet, perception=perception)

        self.assertTrue(observation.detected)
        self.assertTrue(observation.user_present)
        self.assertTrue(observation.desk_active)
        self.assertIn("object:laptop", observation.labels)
        self.assertIn("person_in_desk_zone", observation.labels)
        self.assertEqual(observation.metadata["perception"]["people_count"], 1)
        self.assertEqual(observation.metadata["perception"]["screen_candidate_count"], 1)
        self.assertAlmostEqual(observation.confidence, 0.91, places=2)


if __name__ == "__main__":
    unittest.main()