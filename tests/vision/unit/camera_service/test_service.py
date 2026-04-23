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


class _FakePerceptionPipeline:
    @classmethod
    def from_config(cls, config):
        del config
        return cls()

    def detector_status(self) -> dict[str, str]:
        return {
            "people": "fake_people",
            "face": "fake_face",
            "objects": "fake_objects",
            "scene": "fake_scene",
        }

    def analyze(self, packet):
        del packet

        class _Scene:
            desk_zone_people_count = 0
            engagement_face_count = 0
            screen_candidate_count = 0
            handheld_candidate_count = 0
            labels = ()
            metadata = {}

        class _Snapshot:
            people = ()
            faces = ()
            objects = ()
            scene = _Scene()
            metadata = {"detectors": {"people": "fake_people", "face": "fake_face"}}

        return _Snapshot()



class _FakeClosableObjectDetector:
    backend_label = "fake_hailo"

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _FakePerceptionPipelineWithClosableObject(_FakePerceptionPipeline):
    @classmethod
    def from_config(cls, config):
        del config
        instance = cls()
        instance.object_detector = _FakeClosableObjectDetector()
        return instance


class _FakeBehaviorPipeline:
    def __init__(self) -> None:
        self.calls = 0

    def analyze(self, perception):
        self.calls += 1
        del perception

        class _Signal:
            def __init__(self, active=False, confidence=0.0):
                self.active = active
                self.confidence = confidence
                self.reasons = ()
                self.metadata = {}

        class _Snapshot:
            presence = _Signal(active=False, confidence=0.0)
            desk_activity = _Signal(active=False, confidence=0.0)
            computer_work = _Signal(active=False, confidence=0.0)
            phone_usage = _Signal(active=False, confidence=0.0)
            study_activity = _Signal(active=False, confidence=0.0)
            metadata = {}

        return _Snapshot()


class _FakeStabilizer:
    @classmethod
    def from_config(cls, config):
        del config
        return cls()

    def stabilize(self, behavior, captured_at):
        del captured_at
        return behavior


class _FakeSessionTracker:
    def __init__(self) -> None:
        self.calls = 0

    def update(self, behavior, captured_at):
        self.calls += 1
        del behavior
        del captured_at

        class _Session:
            def __init__(self, active=False):
                self.active = active
                self.state = "inactive"
                self.current_active_seconds = 0.0
                self.last_active_streak_seconds = 0.0
                self.total_active_seconds = 0.0
                self.activations = 0
                self.last_started_at = None
                self.last_ended_at = None
                self.metadata = {}

        class _Snapshot:
            presence = _Session(active=False)
            desk_activity = _Session(active=False)
            computer_work = _Session(active=False)
            phone_usage = _Session(active=False)
            study_activity = _Session(active=False)
            metadata = {}

        return _Snapshot()


class CameraServiceTests(unittest.TestCase):
    @patch("modules.devices.vision.camera_service.service.build_vision_observation")
    @patch("modules.devices.vision.camera_service.service.VisionSessionTracker", _FakeSessionTracker)
    @patch("modules.devices.vision.camera_service.service.BehaviorStabilizer", _FakeStabilizer)
    @patch("modules.devices.vision.camera_service.service.BehaviorPipeline", _FakeBehaviorPipeline)
    @patch("modules.devices.vision.camera_service.service.PerceptionPipeline", _FakePerceptionPipeline)
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
        self.assertTrue(service.status()["perception_pipeline_ready"])
        self.assertTrue(service.status()["behavior_pipeline_ready"])
        self.assertTrue(service.status()["stabilization_pipeline_ready"])
        self.assertTrue(service.status()["session_tracker_ready"])
        self.assertEqual(service.status()["detectors"]["people"], "fake_people")
        self.assertEqual(service.status()["detectors"]["face"], "fake_face")
        self.assertIn("diagnostics", first.metadata)
        self.assertIn("signals", first.metadata["diagnostics"])

    @patch("modules.devices.vision.camera_service.service.build_vision_observation")
    @patch("modules.devices.vision.camera_service.service.VisionSessionTracker", _FakeSessionTracker)
    @patch("modules.devices.vision.camera_service.service.BehaviorStabilizer", _FakeStabilizer)
    @patch("modules.devices.vision.camera_service.service.BehaviorPipeline", _FakeBehaviorPipeline)
    @patch("modules.devices.vision.camera_service.service.PerceptionPipeline", _FakePerceptionPipeline)
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

    @patch("modules.devices.vision.camera_service.service.VisionSessionTracker", _FakeSessionTracker)
    @patch("modules.devices.vision.camera_service.service.BehaviorStabilizer", _FakeStabilizer)
    @patch("modules.devices.vision.camera_service.service.BehaviorPipeline", _FakeBehaviorPipeline)
    @patch("modules.devices.vision.camera_service.service.PerceptionPipeline", _FakePerceptionPipeline)
    @patch("modules.devices.vision.camera_service.service.VisionCaptureReader", _FakeReader)
    def test_close_releases_reader_and_marks_service_closed(self) -> None:
        from modules.devices.vision.camera_service import CameraService

        service = CameraService(config={"enabled": True})
        service.close()

        self.assertTrue(service._reader.closed)
        self.assertTrue(service.status()["closed"])


    @patch("modules.devices.vision.camera_service.service.VisionSessionTracker", _FakeSessionTracker)
    @patch("modules.devices.vision.camera_service.service.BehaviorStabilizer", _FakeStabilizer)
    @patch("modules.devices.vision.camera_service.service.BehaviorPipeline", _FakeBehaviorPipeline)
    @patch(
        "modules.devices.vision.camera_service.service.PerceptionPipeline",
        _FakePerceptionPipelineWithClosableObject,
    )
    @patch("modules.devices.vision.camera_service.service.VisionCaptureReader", _FakeReader)
    def test_close_closes_object_detector_when_detector_exposes_close(self) -> None:
        from modules.devices.vision.camera_service import CameraService

        service = CameraService(config={"enabled": True})
        detector = service._perception.object_detector

        self.assertFalse(detector.closed)
        service.close()
        self.assertTrue(detector.closed)


if __name__ == "__main__":
    unittest.main()