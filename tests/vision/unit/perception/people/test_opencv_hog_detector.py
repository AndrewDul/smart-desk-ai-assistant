from __future__ import annotations

import unittest

from modules.devices.vision.capture.frame_packet import FramePacket
from modules.devices.vision.perception.people.opencv_hog_detector import (
    OpenCvHogPeopleDetector,
    _DetectionPass,
)


class _FakeHog:
    def __init__(self, mapping) -> None:
        self._mapping = dict(mapping)
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
        return self._mapping.get(image, ([], []))


class _TestableOpenCvHogPeopleDetector(OpenCvHogPeopleDetector):
    def __init__(self, *, passes, **kwargs) -> None:
        super().__init__(**kwargs)
        self._passes = tuple(passes)

    def _build_detection_passes(self, packet):
        del packet
        return self._passes


class OpenCvHogPeopleDetectorTests(unittest.TestCase):
    def test_detector_maps_box_back_from_upscaled_roi_pass(self) -> None:
        fake_hog = _FakeHog(
            {
                "desk-upscaled": (
                    [(20, 10, 200, 400)],
                    [2.6],
                )
            }
        )
        detector = _TestableOpenCvHogPeopleDetector(
            passes=[
                _DetectionPass(
                    name="desk_roi_upscaled",
                    image="desk-upscaled",
                    x_offset=100,
                    y_offset=50,
                    scale_x=2.0,
                    scale_y=2.0,
                )
            ],
            hog=fake_hog,
            min_confidence=0.4,
            min_area_ratio=0.02,
            min_height_ratio=0.10,
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
        detection = detections[0]
        self.assertEqual(detection.bounding_box.left, 110)
        self.assertEqual(detection.bounding_box.top, 55)
        self.assertEqual(detection.bounding_box.right, 210)
        self.assertEqual(detection.bounding_box.bottom, 255)
        self.assertEqual(detection.metadata["pass_name"], "desk_roi_upscaled")

    def test_detector_filters_small_boxes_and_suppresses_overlaps_across_passes(self) -> None:
        fake_hog = _FakeHog(
            {
                "full": (
                    [
                        (100, 100, 400, 500),
                        (10, 10, 40, 40),
                    ],
                    [2.6, 4.0],
                ),
                "desk": (
                    [
                        (120, 120, 390, 480),
                    ],
                    [2.0],
                ),
            }
        )
        detector = _TestableOpenCvHogPeopleDetector(
            passes=[
                _DetectionPass(
                    name="full_frame",
                    image="full",
                    x_offset=0,
                    y_offset=0,
                    scale_x=1.0,
                    scale_y=1.0,
                ),
                _DetectionPass(
                    name="desk_roi",
                    image="desk",
                    x_offset=0,
                    y_offset=0,
                    scale_x=1.0,
                    scale_y=1.0,
                ),
            ],
            hog=fake_hog,
            min_confidence=0.4,
            min_area_ratio=0.05,
            min_height_ratio=0.15,
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
        self.assertEqual(fake_hog.calls[0]["image"], "full")

    def test_detector_returns_empty_tuple_when_no_people_are_found(self) -> None:
        fake_hog = _FakeHog({"full": ([], [])})
        detector = _TestableOpenCvHogPeopleDetector(
            passes=[
                _DetectionPass(
                    name="full_frame",
                    image="full",
                    x_offset=0,
                    y_offset=0,
                    scale_x=1.0,
                    scale_y=1.0,
                )
            ],
            hog=fake_hog,
        )
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