from __future__ import annotations

import unittest

from modules.devices.vision.behavior import BehaviorPipeline
from modules.devices.vision.perception import (
    BoundingBox,
    FaceDetection,
    ObjectDetection,
    PerceptionSnapshot,
    PersonDetection,
    SceneContext,
)


class BehaviorPipelineTests(unittest.TestCase):
    def test_behavior_pipeline_builds_expected_signals_for_desk_work(self) -> None:
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            people=(
                PersonDetection(
                    bounding_box=BoundingBox(left=320, top=120, right=860, bottom=700),
                    confidence=0.92,
                ),
            ),
            faces=(
                FaceDetection(
                    bounding_box=BoundingBox(left=480, top=80, right=640, bottom=260),
                    confidence=0.85,
                ),
            ),
            objects=(
                ObjectDetection(
                    label="laptop",
                    bounding_box=BoundingBox(left=360, top=180, right=920, bottom=430),
                    confidence=0.88,
                ),
            ),
            scene=SceneContext(
                desk_zone_people_count=1,
                engagement_face_count=1,
                screen_candidate_count=1,
                handheld_candidate_count=0,
            ),
        )

        snapshot = BehaviorPipeline().analyze(perception)

        self.assertTrue(snapshot.presence.active)
        self.assertTrue(snapshot.desk_activity.active)
        self.assertTrue(snapshot.computer_work.active)
        self.assertFalse(snapshot.phone_usage.active)
        self.assertTrue(snapshot.study_activity.active)

    def test_behavior_pipeline_does_not_treat_downward_attention_as_phone_usage(self) -> None:
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
                desk_zone_people_count=1,
                engagement_face_count=1,
                screen_candidate_count=0,
                handheld_candidate_count=0,
            ),
        )

        snapshot = BehaviorPipeline().analyze(perception)

        self.assertTrue(snapshot.presence.active)
        self.assertTrue(snapshot.desk_activity.active)
        self.assertFalse(snapshot.computer_work.active)
        self.assertFalse(snapshot.phone_usage.active)


if __name__ == "__main__":
    unittest.main()