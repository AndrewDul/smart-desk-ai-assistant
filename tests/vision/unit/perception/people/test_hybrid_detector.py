# tests/vision/unit/perception/people/test_hybrid_detector.py
from __future__ import annotations

import unittest

from modules.devices.vision.capture.frame_packet import FramePacket
from modules.devices.vision.perception.models import (
    BoundingBox,
    FaceDetection,
    PersonDetection,
)
from modules.devices.vision.perception.people.hybrid_detector import (
    HybridFacePrimaryPeopleDetector,
)


def _make_packet(width: int = 1280, height: int = 720) -> FramePacket:
    return FramePacket(
        pixels=[[0]],
        width=width,
        height=height,
        channels=1,
        backend_label="fake",
    )


class _FakeFaceDetector:
    backend_label = "fake_face"

    def __init__(self, faces: tuple[FaceDetection, ...] = ()) -> None:
        self._faces = faces
        self.calls = 0

    def detect_faces(self, packet: FramePacket) -> tuple[FaceDetection, ...]:
        del packet
        self.calls += 1
        return self._faces


class _FakeSecondaryDetector:
    backend_label = "fake_secondary"

    def __init__(
        self,
        results: tuple[PersonDetection, ...] = (),
        *,
        raise_error: bool = False,
    ) -> None:
        self._results = results
        self._raise_error = raise_error
        self.calls = 0

    def detect_people(self, packet: FramePacket) -> tuple[PersonDetection, ...]:
        del packet
        self.calls += 1
        if self._raise_error:
            raise RuntimeError("secondary detector boom")
        return self._results


class HybridFacePrimaryPeopleDetectorTests(unittest.TestCase):

    # ------------------------------------------------------------------
    # Face-only path
    # ------------------------------------------------------------------

    def test_no_faces_and_no_secondary_returns_empty(self) -> None:
        detector = HybridFacePrimaryPeopleDetector(
            face_detector=_FakeFaceDetector(faces=()),
            secondary_detector=None,
        )
        self.assertEqual(detector.detect_people(_make_packet()), ())

    def test_single_face_projects_into_person_box(self) -> None:
        face = FaceDetection(
            bounding_box=BoundingBox(left=500, top=140, right=620, bottom=290),
            confidence=0.82,
        )
        detector = HybridFacePrimaryPeopleDetector(
            face_detector=_FakeFaceDetector(faces=(face,)),
        )

        people = detector.detect_people(_make_packet())

        self.assertEqual(len(people), 1)
        person = people[0]
        self.assertEqual(person.label, "person")
        self.assertEqual(person.metadata["source"], "face_projected")
        self.assertEqual(person.metadata["detector"], "hybrid_face_primary")
        # Projected box must be substantially larger than the face box.
        self.assertGreater(person.bounding_box.width, face.bounding_box.width)
        self.assertGreater(person.bounding_box.height, face.bounding_box.height)

    def test_face_only_confidence_floor_applied(self) -> None:
        face = FaceDetection(
            bounding_box=BoundingBox(left=500, top=140, right=620, bottom=290),
            confidence=0.40,
        )
        detector = HybridFacePrimaryPeopleDetector(
            face_detector=_FakeFaceDetector(faces=(face,)),
            face_only_confidence_floor=0.65,
        )

        (person,) = detector.detect_people(_make_packet())
        self.assertAlmostEqual(person.confidence, 0.65, places=3)

    def test_projected_box_clamped_to_frame(self) -> None:
        # Face near right edge — projection must not exceed frame width.
        face = FaceDetection(
            bounding_box=BoundingBox(left=1200, top=100, right=1270, bottom=200),
            confidence=0.8,
        )
        detector = HybridFacePrimaryPeopleDetector(
            face_detector=_FakeFaceDetector(faces=(face,)),
        )

        (person,) = detector.detect_people(_make_packet(width=1280, height=720))
        self.assertLessEqual(person.bounding_box.right, 1280)
        self.assertGreaterEqual(person.bounding_box.left, 0)
        self.assertLessEqual(person.bounding_box.bottom, 720)

    # ------------------------------------------------------------------
    # Secondary-only path
    # ------------------------------------------------------------------

    def test_secondary_only_detections_pass_through(self) -> None:
        hog_detection = PersonDetection(
            bounding_box=BoundingBox(left=100, top=100, right=300, bottom=600),
            confidence=0.7,
            metadata={"detector": "opencv_hog"},
        )
        detector = HybridFacePrimaryPeopleDetector(
            face_detector=_FakeFaceDetector(faces=()),
            secondary_detector=_FakeSecondaryDetector(results=(hog_detection,)),
        )

        (person,) = detector.detect_people(_make_packet())
        self.assertEqual(person.metadata["source"], "hog")
        self.assertAlmostEqual(person.confidence, 0.7, places=3)

    # ------------------------------------------------------------------
    # Merge path
    # ------------------------------------------------------------------

    def test_overlapping_face_and_secondary_are_merged(self) -> None:
        face = FaceDetection(
            bounding_box=BoundingBox(left=540, top=140, right=620, bottom=240),
            confidence=0.7,
        )
        # Secondary detector returns a box that significantly overlaps the
        # face-projected body box.
        hog_detection = PersonDetection(
            bounding_box=BoundingBox(left=450, top=130, right=720, bottom=690),
            confidence=0.6,
            metadata={"detector": "opencv_hog"},
        )
        detector = HybridFacePrimaryPeopleDetector(
            face_detector=_FakeFaceDetector(faces=(face,)),
            secondary_detector=_FakeSecondaryDetector(results=(hog_detection,)),
            merged_confidence_boost=0.2,
        )

        people = detector.detect_people(_make_packet())
        self.assertEqual(len(people), 1)
        merged = people[0]
        self.assertEqual(merged.metadata["source"], "hog+face")
        # Merged confidence must be boosted above either input.
        self.assertGreater(merged.confidence, 0.7)
        # Merged box uses secondary geometry (better body shape).
        self.assertEqual(merged.bounding_box, hog_detection.bounding_box)

    def test_non_overlapping_face_and_secondary_are_kept_separately(self) -> None:
        face = FaceDetection(
            bounding_box=BoundingBox(left=100, top=100, right=180, bottom=200),
            confidence=0.8,
        )
        # Secondary detector returns a completely unrelated box far away.
        hog_detection = PersonDetection(
            bounding_box=BoundingBox(left=1000, top=400, right=1200, bottom=700),
            confidence=0.6,
            metadata={"detector": "opencv_hog"},
        )
        detector = HybridFacePrimaryPeopleDetector(
            face_detector=_FakeFaceDetector(faces=(face,)),
            secondary_detector=_FakeSecondaryDetector(results=(hog_detection,)),
        )

        people = detector.detect_people(_make_packet())
        self.assertEqual(len(people), 2)
        sources = {p.metadata["source"] for p in people}
        self.assertEqual(sources, {"face_projected", "hog"})

    # ------------------------------------------------------------------
    # Error resilience
    # ------------------------------------------------------------------

    def test_secondary_detector_exception_does_not_break_face_path(self) -> None:
        face = FaceDetection(
            bounding_box=BoundingBox(left=500, top=140, right=620, bottom=290),
            confidence=0.85,
        )
        detector = HybridFacePrimaryPeopleDetector(
            face_detector=_FakeFaceDetector(faces=(face,)),
            secondary_detector=_FakeSecondaryDetector(raise_error=True),
        )

        people = detector.detect_people(_make_packet())
        self.assertEqual(len(people), 1)
        self.assertEqual(people[0].metadata["source"], "face_projected")

    def test_max_detections_cap_enforced(self) -> None:
        faces = tuple(
            FaceDetection(
                bounding_box=BoundingBox(
                    left=50 + i * 120,
                    top=100,
                    right=130 + i * 120,
                    bottom=200,
                ),
                confidence=0.5 + i * 0.05,
            )
            for i in range(8)
        )
        detector = HybridFacePrimaryPeopleDetector(
            face_detector=_FakeFaceDetector(faces=faces),
            max_detections=3,
        )

        people = detector.detect_people(_make_packet())
        self.assertEqual(len(people), 3)
        # Sorted by confidence descending.
        confidences = [p.confidence for p in people]
        self.assertEqual(confidences, sorted(confidences, reverse=True))

    # ------------------------------------------------------------------
    # Backend label
    # ------------------------------------------------------------------

    def test_backend_label_is_hybrid(self) -> None:
        detector = HybridFacePrimaryPeopleDetector(
            face_detector=_FakeFaceDetector(),
        )
        self.assertEqual(detector.backend_label, "hybrid_face_primary")


if __name__ == "__main__":
    unittest.main()