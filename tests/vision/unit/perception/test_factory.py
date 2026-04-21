from __future__ import annotations

import unittest

from modules.devices.vision.config import VisionRuntimeConfig
from modules.devices.vision.perception.factory import build_object_detector, build_people_detector
from modules.devices.vision.perception.objects import NullObjectDetector
from modules.devices.vision.perception.people import NullPeopleDetector, OpenCvHogPeopleDetector


class PerceptionFactoryTests(unittest.TestCase):
    def test_build_people_detector_returns_null_when_disabled(self) -> None:
        config = VisionRuntimeConfig.from_mapping(
            {
                "enabled": True,
                "people_detection_enabled": False,
            }
        )

        detector = build_people_detector(config)

        self.assertIsInstance(detector, NullPeopleDetector)

    def test_build_people_detector_returns_opencv_hog_when_enabled(self) -> None:
        config = VisionRuntimeConfig.from_mapping(
            {
                "enabled": True,
                "people_detection_enabled": True,
                "people_detector_backend": "opencv_hog",
                "people_detector_min_confidence": 0.4,
                "people_detector_min_area_ratio": 0.02,
            }
        )

        detector = build_people_detector(config)

        self.assertIsInstance(detector, OpenCvHogPeopleDetector)
        self.assertAlmostEqual(detector.min_confidence, 0.4, places=3)
        self.assertAlmostEqual(detector.min_area_ratio, 0.02, places=3)

    def test_build_people_detector_rejects_unsupported_backend(self) -> None:
        config = VisionRuntimeConfig.from_mapping(
            {
                "enabled": True,
                "people_detection_enabled": True,
                "people_detector_backend": "unknown_backend",
            }
        )

        with self.assertRaises(ValueError):
            build_people_detector(config)

    def test_build_object_detector_returns_null_for_now(self) -> None:
        config = VisionRuntimeConfig.from_mapping({"enabled": True})

        detector = build_object_detector(config)

        self.assertIsInstance(detector, NullObjectDetector)


if __name__ == "__main__":
    unittest.main()