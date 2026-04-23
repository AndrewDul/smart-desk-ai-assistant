from __future__ import annotations

import unittest
from unittest.mock import patch


class _FakeReader:
    def __init__(self, config) -> None:
        del config
        self.active_backend = "fake_backend"

    def close(self) -> None:
        return None


class _FakeControllableObjectDetector:
    def __init__(self) -> None:
        self.cadence_hz = 2.0
        self.pause_calls = 0
        self.resume_calls: list[float | None] = []

    def set_inference_cadence_hz(self, hz: float) -> None:
        self.cadence_hz = max(0.0, float(hz))

    def pause(self) -> None:
        self.pause_calls += 1
        self.cadence_hz = 0.0

    def resume(self, hz: float | None = None) -> None:
        self.resume_calls.append(hz)
        self.cadence_hz = 2.0 if hz is None else float(hz)

    def status(self) -> dict[str, object]:
        return {
            "cadence_hz": self.cadence_hz,
            "paused": self.cadence_hz <= 0.0,
        }


class _FakePerceptionPipeline:
    @classmethod
    def from_config(cls, config):
        del config
        instance = cls()
        instance.object_detector = _FakeControllableObjectDetector()
        return instance

    def detector_status(self) -> dict[str, str]:
        return {
            "people": "fake_people",
            "face": "fake_face",
            "objects": "fake_objects",
            "scene": "fake_scene",
        }


class _FakeBehaviorPipeline:
    def __init__(self) -> None:
        return None


class _FakeStabilizer:
    @classmethod
    def from_config(cls, config):
        del config
        return cls()


class _FakeSessionTracker:
    def __init__(self) -> None:
        return None


class CameraServiceBrokerControlTests(unittest.TestCase):
    @patch("modules.devices.vision.camera_service.service.VisionSessionTracker", _FakeSessionTracker)
    @patch("modules.devices.vision.camera_service.service.BehaviorStabilizer", _FakeStabilizer)
    @patch("modules.devices.vision.camera_service.service.BehaviorPipeline", _FakeBehaviorPipeline)
    @patch("modules.devices.vision.camera_service.service.PerceptionPipeline", _FakePerceptionPipeline)
    @patch("modules.devices.vision.camera_service.service.VisionCaptureReader", _FakeReader)
    def test_set_object_detection_cadence_hz_controls_detector(self) -> None:
        from modules.devices.vision.camera_service import CameraService

        service = CameraService(config={"enabled": True})
        updated = service.set_object_detection_cadence_hz(5.0)

        self.assertTrue(updated)
        status = service.object_detector_status()
        self.assertIsNotNone(status)
        self.assertAlmostEqual(status["cadence_hz"], 5.0, places=3)

    @patch("modules.devices.vision.camera_service.service.VisionSessionTracker", _FakeSessionTracker)
    @patch("modules.devices.vision.camera_service.service.BehaviorStabilizer", _FakeStabilizer)
    @patch("modules.devices.vision.camera_service.service.BehaviorPipeline", _FakeBehaviorPipeline)
    @patch("modules.devices.vision.camera_service.service.PerceptionPipeline", _FakePerceptionPipeline)
    @patch("modules.devices.vision.camera_service.service.VisionCaptureReader", _FakeReader)
    def test_pause_object_detection_controls_detector(self) -> None:
        from modules.devices.vision.camera_service import CameraService

        service = CameraService(config={"enabled": True})
        paused = service.pause_object_detection()

        self.assertTrue(paused)
        status = service.object_detector_status()
        self.assertIsNotNone(status)
        self.assertTrue(status["paused"])

    @patch("modules.devices.vision.camera_service.service.VisionSessionTracker", _FakeSessionTracker)
    @patch("modules.devices.vision.camera_service.service.BehaviorStabilizer", _FakeStabilizer)
    @patch("modules.devices.vision.camera_service.service.BehaviorPipeline", _FakeBehaviorPipeline)
    @patch("modules.devices.vision.camera_service.service.PerceptionPipeline", _FakePerceptionPipeline)
    @patch("modules.devices.vision.camera_service.service.VisionCaptureReader", _FakeReader)
    def test_resume_object_detection_controls_detector(self) -> None:
        from modules.devices.vision.camera_service import CameraService

        service = CameraService(config={"enabled": True})
        service.pause_object_detection()
        resumed = service.resume_object_detection(4.0)

        self.assertTrue(resumed)
        status = service.object_detector_status()
        self.assertIsNotNone(status)
        self.assertAlmostEqual(status["cadence_hz"], 4.0, places=3)
        self.assertFalse(status["paused"])


if __name__ == "__main__":
    unittest.main()