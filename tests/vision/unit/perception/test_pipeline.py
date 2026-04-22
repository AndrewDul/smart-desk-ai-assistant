from __future__ import annotations
import unittest
from modules.devices.vision.capture.frame_packet import FramePacket
from modules.devices.vision.config import VisionRuntimeConfig
from modules.devices.vision.perception import PerceptionPipeline
from modules.devices.vision.perception.models import BoundingBox, FaceDetection


class _StubFaceDetector:
    backend_label = "stub_face"

    def __init__(self, faces):
        self._faces = tuple(faces)

    def detect_faces(self, packet):
        del packet
        return self._faces


class PerceptionPipelineTests(unittest.TestCase):
    def test_pipeline_returns_empty_snapshot_with_default_null_detectors(self) -> None:
        packet = FramePacket(
            pixels=[[0]],
            width=1280,
            height=720,
            channels=3,
            backend_label="picamera2",
        )

        snapshot = PerceptionPipeline().analyze(packet)

        self.assertEqual(snapshot.frame_width, 1280)
        self.assertEqual(snapshot.frame_height, 720)
        self.assertEqual(len(snapshot.people), 0)
        self.assertEqual(len(snapshot.faces), 0)
        self.assertEqual(len(snapshot.objects), 0)
        self.assertEqual(snapshot.scene.desk_zone_people_count, 0)
        self.assertEqual(snapshot.scene.screen_candidate_count, 0)
        self.assertEqual(snapshot.scene.handheld_candidate_count, 0)

    def test_pipeline_with_hybrid_detector_yields_face_projected_person(self) -> None:
        """
        End-to-end: the hybrid face-primary detector plugged into the real
        PerceptionPipeline turns a detected face into a PersonDetection that
        the pipeline exposes in snapshot.people.
        """
        from modules.devices.vision.perception.people import (
            HybridFacePrimaryPeopleDetector,
        )
        from modules.devices.vision.perception.scene import NullSceneAnalyzer

        packet = FramePacket(
            pixels=[[0]],
            width=1280,
            height=720,
            channels=3,
            backend_label="fake",
        )

        face = FaceDetection(
            bounding_box=BoundingBox(left=540, top=150, right=640, bottom=270),
            confidence=0.8,
        )
        hybrid_detector = HybridFacePrimaryPeopleDetector(
            face_detector=_StubFaceDetector(faces=(face,)),
        )

        pipeline = PerceptionPipeline(
            people_detector=hybrid_detector,
            scene_analyzer=NullSceneAnalyzer(),
        )

        snapshot = pipeline.analyze(packet)

        self.assertEqual(len(snapshot.people), 1)
        person = snapshot.people[0]
        self.assertEqual(person.metadata["source"], "face_projected")
        self.assertEqual(person.metadata["detector"], "hybrid_face_primary")
        self.assertGreater(snapshot.scene.desk_zone_people_count, 0)
        self.assertEqual(snapshot.metadata["people_count"], 1)
        self.assertEqual(snapshot.metadata["detectors"]["people"], "hybrid_face_primary")


if __name__ == "__main__":
    unittest.main()