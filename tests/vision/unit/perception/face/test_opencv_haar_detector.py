from __future__ import annotations

import unittest

from modules.devices.vision.capture.frame_packet import FramePacket
from modules.devices.vision.perception.face.opencv_haar_detector import OpenCvHaarFaceDetector


class _FakeCascade:
    def __init__(self, faces) -> None:
        self.faces = faces
        self.calls = []

    def detectMultiScale(self, image, scaleFactor, minNeighbors):
        self.calls.append(
            {
                "image": image,
                "scaleFactor": scaleFactor,
                "minNeighbors": minNeighbors,
            }
        )
        return self.faces


class _TestableOpenCvHaarFaceDetector(OpenCvHaarFaceDetector):
    def __init__(self, *, prepared_gray, offsets=(0, 0), **kwargs) -> None:
        super().__init__(**kwargs)
        self._prepared_gray = prepared_gray
        self._offsets = offsets

    def _prepare_gray_frame(self, packet):
        del packet
        return self._prepared_gray, self._offsets[0], self._offsets[1]


class OpenCvHaarFaceDetectorTests(unittest.TestCase):
    def test_detector_maps_roi_face_back_to_frame(self) -> None:
        fake_cascade = _FakeCascade(
            faces=[
                (20, 30, 80, 100),
            ]
        )
        detector = _TestableOpenCvHaarFaceDetector(
            prepared_gray="gray-roi",
            offsets=(100, 50),
            cascade=fake_cascade,
            min_area_ratio=0.001,
        )
        packet = FramePacket(
            pixels=[[0]],
            width=1280,
            height=720,
            channels=3,
            backend_label="picamera2",
        )

        detections = detector.detect_faces(packet)

        self.assertEqual(len(detections), 1)
        detection = detections[0]
        self.assertEqual(detection.bounding_box.left, 120)
        self.assertEqual(detection.bounding_box.top, 80)
        self.assertEqual(detection.bounding_box.right, 200)
        self.assertEqual(detection.bounding_box.bottom, 180)
        self.assertEqual(detection.metadata["detector"], "opencv_haar")
        self.assertEqual(fake_cascade.calls[0]["image"], "gray-roi")

    def test_detector_filters_too_small_faces(self) -> None:
        fake_cascade = _FakeCascade(
            faces=[
                (10, 10, 10, 10),
            ]
        )
        detector = _TestableOpenCvHaarFaceDetector(
            prepared_gray="gray-roi",
            cascade=fake_cascade,
            min_area_ratio=0.01,
        )
        packet = FramePacket(
            pixels=[[0]],
            width=1280,
            height=720,
            channels=3,
            backend_label="picamera2",
        )

        detections = detector.detect_faces(packet)

        self.assertEqual(detections, ())


if __name__ == "__main__":
    unittest.main()