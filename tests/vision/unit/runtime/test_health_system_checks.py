from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules.runtime.health.system_checks import HealthSystemChecks


def _base_vision_settings() -> dict[str, object]:
    return {
        "enabled": True,
        "backend": "picamera2",
        "fallback_backend": "opencv",
        "camera_index": 0,
        "frame_width": 1280,
        "frame_height": 720,
    }


class _FakeHealthSystemChecks(HealthSystemChecks):
    def __init__(self, settings: dict[str, object], available_modules: set[str]) -> None:
        self.settings = settings
        self._available_modules = set(available_modules)

    def _module_exists(self, module_name: str) -> bool:
        return module_name in self._available_modules

    def _resolve_local_path(self, raw_path: str):
        return Path(raw_path)


class VisionHealthSystemChecksTests(unittest.TestCase):
    def test_hybrid_face_primary_is_accepted_when_opencv_is_available(self) -> None:
        settings = {
            "vision": {
                **_base_vision_settings(),
                "people_detection_enabled": True,
                "people_detector_backend": "hybrid_face_primary",
                "face_detection_enabled": True,
                "face_detector_backend": "opencv_haar",
            }
        }

        checks = _FakeHealthSystemChecks(
            settings,
            {"numpy", "cv2", "picamera2"},
        )
        item = checks._check_vision_runtime()

        self.assertTrue(item.ok, item.details)
        self.assertIn("people=hybrid_face_primary", item.details)
        self.assertIn("face=opencv_haar", item.details)

    def test_hailo_yolo_is_accepted_when_runtime_and_hef_are_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            hef_path = Path(temp_dir) / "yolov11m_h10.hef"
            hef_path.write_bytes(b"hef")

            settings = {
                "vision": {
                    **_base_vision_settings(),
                    "object_detection_enabled": True,
                    "object_detector_backend": "hailo_yolov11",
                    "object_detector_hailo_hef_path": str(hef_path),
                }
            }

            checks = _FakeHealthSystemChecks(
                settings,
                {"numpy", "picamera2", "hailo_platform"},
            )
            item = checks._check_vision_runtime()

            self.assertTrue(item.ok, item.details)
            self.assertIn("objects=hailo_yolov11", item.details)

    def test_hailo_yolo_requires_hailo_platform_module(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            hef_path = Path(temp_dir) / "yolov11m_h10.hef"
            hef_path.write_bytes(b"hef")

            settings = {
                "vision": {
                    **_base_vision_settings(),
                    "object_detection_enabled": True,
                    "object_detector_backend": "hailo_yolov11",
                    "object_detector_hailo_hef_path": str(hef_path),
                }
            }

            checks = _FakeHealthSystemChecks(
                settings,
                {"numpy", "picamera2"},
            )
            item = checks._check_vision_runtime()

            self.assertFalse(item.ok)
            self.assertIn("hailo_platform", item.details)

    def test_hailo_yolo_requires_existing_hef_file(self) -> None:
        settings = {
            "vision": {
                **_base_vision_settings(),
                "object_detection_enabled": True,
                "object_detector_backend": "hailo_yolov11",
                "object_detector_hailo_hef_path": "/tmp/does-not-exist.hef",
            }
        }

        checks = _FakeHealthSystemChecks(
            settings,
            {"numpy", "picamera2", "hailo_platform"},
        )
        item = checks._check_vision_runtime()

        self.assertFalse(item.ok)
        self.assertIn("missing Hailo HEF model", item.details)


if __name__ == "__main__":
    unittest.main()