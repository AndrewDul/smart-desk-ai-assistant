from __future__ import annotations

import unittest
from unittest.mock import patch

from modules.runtime.contracts import VisionObservation


class _FakeReader:
    def __init__(self, config) -> None:
        self.config = config
        self.active_backend = "fake_backend"
        self.closed = False
        self.read_calls = 0
        self.next_error: Exception | None = None

    def read_frame(self):
        self.read_calls += 1
        if self.next_error is not None:
            error = self.next_error
            self.next_error = None
            raise error

        class _Packet:
            width = 640
            height = 480
            channels = 3
            backend_label = "fake_backend"
            captured_at = 123.0
            metadata = {"camera_index": 0}

        return _Packet()

    def close(self) -> None:
        self.closed = True


class CameraServiceTests(unittest.TestCase):
    @patch("modules.devices.vision.camera_service.service.build_camera_only_observation")
    @patch("modules.devices.vision.camera_service.service.VisionCaptureReader", _FakeReader)
    def test_latest_observation_captures_and_caches_snapshot(self, builder_mock) -> None:
        from modules.devices.vision.camera_service import CameraService

        builder_mock.return_value = VisionObservation(detected=True, confidence=0.9)

        service = CameraService(config={"enabled": True})
        first = service.latest_observation(force_refresh=True)
        second = service.latest_observation(force_refresh=False)

        self.assertTrue(first.detected)
        self.assertIs(first, second)
        self.assertEqual(service.status()["backend"], "fake_backend")
        self.assertIsNone(service.status()["last_error"])

    @patch("modules.devices.vision.camera_service.service.build_camera_only_observation")
    @patch("modules.devices.vision.camera_service.service.VisionCaptureReader", _FakeReader)
    def test_returns_cached_observation_when_refresh_capture_fails(self, builder_mock) -> None:
        from modules.devices.vision.camera_service import CameraService

        first_observation = VisionObservation(detected=True, confidence=0.9)
        builder_mock.return_value = first_observation

        service = CameraService(config={"enabled": True})
        first = service.latest_observation(force_refresh=True)

        service._reader.next_error = RuntimeError("camera offline")
        second = service.latest_observation(force_refresh=True)

        self.assertIs(first, second)
        self.assertEqual(builder_mock.call_count, 1)
        self.assertFalse(service.status()["ok"])
        self.assertIn("camera offline", str(service.status()["last_error"]))

    @patch("modules.devices.vision.camera_service.service.VisionCaptureReader", _FakeReader)
    def test_close_releases_reader_and_marks_service_closed(self) -> None:
        from modules.devices.vision.camera_service import CameraService

        service = CameraService(config={"enabled": True})
        service.close()

        self.assertTrue(service._reader.closed)
        self.assertTrue(service.status()["closed"])


if __name__ == "__main__":
    unittest.main()