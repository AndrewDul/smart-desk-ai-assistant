from __future__ import annotations

import unittest

from modules.devices.vision.capture.frame_packet import FramePacket
from modules.devices.vision.perception.people import OpenCvHogPeopleDetector


class _FakeHog:
    def __init__(self, boxes, weights) -> None:
        self._boxes = boxes
        self._weights = weights
        self.calls = []

    def detectMultiScale(self, image, winStride, padding, scale):
        self.calls.append(
            {
                "image": image,
                "winStride": winStride,
                "padding": padding,
                "scale": scale,
            }
        )
        return self._boxes, self._weights


class _TestableOpenCvHogPeopleDetector(OpenCvHogPeopleDetector):
    def _prepare_bgr_frame(self, packet: FramePacket):
        del packet
        return "prepared-frame"


class OpenCvHogPeopleDetectorTests(unittest.TestCase):
    def test_detector_filters_small_boxes_and_suppresses_overlaps(self) -> None:
        fake_hog = _FakeHog(
            boxes=[
                (100, 100, 400, 500),
                (120, 120, 390, 480),
                (10, 10, 40, 40),
            ],
            weights=[2.6, 2.0, 4.0],
        )
        detector = _TestableOpenCvHogPeopleDetector(
            hog=fake_hog,
            min_confidence=0.4,
            min_area_ratio=0.05,
            nms_iou_threshold=0.3,
        )
        packet = FramePacket(
            pixels=[[0]],
            width=1280,
            height=720,
            channels=3,
            backend_label="picamera2",
        )

        detections = detector.detect_people(packet)

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].label, "person")
        self.assertEqual(detections[0].bounding_box.left, 100)
        self.assertEqual(detections[0].metadata["detector"], "opencv_hog")
        self.assertEqual(fake_hog.calls[0]["image"], "prepared-frame")

    def test_detector_returns_empty_tuple_when_no_people_are_found(self) -> None:
        fake_hog = _FakeHog(boxes=[], weights=[])
        detector = _TestableOpenCvHogPeopleDetector(hog=fake_hog)
        packet = FramePacket(
            pixels=[[0]],
            width=1280,
            height=720,
            channels=3,
            backend_label="picamera2",
        )

        detections = detector.detect_people(packet)

        self.assertEqual(detections, ())


if __name__ == "__main__":
    unittest.main()