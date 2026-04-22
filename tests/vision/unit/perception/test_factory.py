from __future__ import annotations

import unittest

from modules.devices.vision.config import VisionRuntimeConfig
from modules.devices.vision.perception.factory import (
    build_face_detector,
    build_object_detector,
    build_people_detector,
)
from modules.devices.vision.perception.face import NullFaceDetector, OpenCvHaarFaceDetector
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

    def test_build_people_detector_returns_tuned_opencv_hog_when_enabled(self) -> None:
        config = VisionRuntimeConfig.from_mapping(
            {
                "enabled": True,
                "people_detection_enabled": True,
                "people_detector_backend": "opencv_hog",
                "people_detector_min_confidence": 0.4,
                "people_detector_min_area_ratio": 0.02,
                "people_detector_min_height_ratio": 0.15,
                "people_detector_max_width_ratio": 0.8,
                "people_detector_use_clahe": True,
                "people_detector_upscale_factor": 1.5,
                "people_detector_desk_roi_enabled": True,
                "people_detector_roi_x_min": 0.12,
                "people_detector_roi_y_min": 0.10,
                "people_detector_roi_x_max": 0.88,
                "people_detector_roi_y_max": 0.96,
            }
        )

        detector = build_people_detector(config)

        self.assertIsInstance(detector, OpenCvHogPeopleDetector)
        self.assertAlmostEqual(detector.min_confidence, 0.4, places=3)
        self.assertAlmostEqual(detector.min_area_ratio, 0.02, places=3)
        self.assertAlmostEqual(detector.min_height_ratio, 0.15, places=3)
        self.assertAlmostEqual(detector.max_width_ratio, 0.8, places=3)
        self.assertTrue(detector.use_clahe)
        self.assertAlmostEqual(detector.upscale_factor, 1.5, places=3)
        self.assertTrue(detector.desk_roi_enabled)
        self.assertEqual(detector.desk_roi_bounds, (0.12, 0.10, 0.88, 0.96))

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

    def test_build_face_detector_returns_null_when_disabled(self) -> None:
        config = VisionRuntimeConfig.from_mapping(
            {
                "enabled": True,
                "face_detection_enabled": False,
            }
        )

        detector = build_face_detector(config)

        self.assertIsInstance(detector, NullFaceDetector)

    def test_build_face_detector_returns_opencv_haar_when_enabled(self) -> None:
        config = VisionRuntimeConfig.from_mapping(
            {
                "enabled": True,
                "face_detection_enabled": True,
                "face_detector_backend": "opencv_haar",
                "face_detector_min_area_ratio": 0.003,
                "face_detector_use_clahe": True,
                "face_detector_roi_enabled": True,
            }
        )

        detector = build_face_detector(config)

        self.assertIsInstance(detector, OpenCvHaarFaceDetector)
        self.assertAlmostEqual(detector.min_area_ratio, 0.003, places=3)
        self.assertTrue(detector.use_clahe)
        self.assertTrue(detector.roi_enabled)

    def test_build_object_detector_returns_null_for_now(self) -> None:
        config = VisionRuntimeConfig.from_mapping({"enabled": True})
        detector = build_object_detector(config)
        self.assertIsInstance(detector, NullObjectDetector)

    def test_build_people_detector_returns_hybrid_when_configured(self) -> None:
        config = VisionRuntimeConfig.from_mapping(
            {
                "enabled": True,
                "people_detection_enabled": True,
                "people_detector_backend": "hybrid_face_primary",
                "face_detector_backend": "opencv_haar",
                "people_detector_hybrid_body_width_multiplier": 3.0,
                "people_detector_hybrid_body_height_multiplier": 6.0,
            }
        )

        detector = build_people_detector(config)

        self.assertEqual(detector.backend_label, "hybrid_face_primary")
        self.assertIsNotNone(detector.face_detector)
        self.assertIsNone(detector.secondary_detector)
        self.assertAlmostEqual(detector.body_width_multiplier, 3.0, places=3)
        self.assertAlmostEqual(detector.body_height_multiplier, 6.0, places=3)

    def test_build_people_detector_hybrid_attaches_hog_secondary_when_enabled(self) -> None:
        config = VisionRuntimeConfig.from_mapping(
            {
                "enabled": True,
                "people_detection_enabled": True,
                "people_detector_backend": "hybrid_face_primary",
                "face_detector_backend": "opencv_haar",
                "people_detector_hybrid_use_hog_secondary": True,
            }
        )

        detector = build_people_detector(config)

        self.assertEqual(detector.backend_label, "hybrid_face_primary")
        self.assertIsNotNone(detector.secondary_detector)
        self.assertIsInstance(detector.secondary_detector, OpenCvHogPeopleDetector)

    def test_build_people_detector_hybrid_uses_null_face_when_backend_unknown(self) -> None:
        config = VisionRuntimeConfig.from_mapping(
            {
                "enabled": True,
                "people_detection_enabled": True,
                "people_detector_backend": "hybrid_face_primary",
                "face_detector_backend": "unknown_face_backend",
            }
        )

        detector = build_people_detector(config)

        self.assertEqual(detector.backend_label, "hybrid_face_primary")
        self.assertEqual(
            getattr(detector.face_detector, "backend_label", ""),
            "null",
        )


if __name__ == "__main__":
    unittest.main()