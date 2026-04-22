# tests/vision/unit/perception/objects/test_hailo_yolo_detector.py
from __future__ import annotations

import threading
import time
import unittest

import numpy as np

from modules.devices.vision.capture.frame_packet import FramePacket
from modules.devices.vision.perception.models import BoundingBox, ObjectDetection
from modules.devices.vision.perception.objects.hailo_runtime.errors import (
    HailoRuntimeError,
    HailoUnavailableError,
)
from modules.devices.vision.perception.objects.hailo_runtime.models import (
    HailoInferenceResult,
    RawNmsDetection,
)
from modules.devices.vision.perception.objects.hailo_yolo_detector import (
    HailoYoloObjectDetector,
)
from modules.devices.vision.preprocessing.yolo_letterbox import LetterboxTransform


def _make_packet(width: int = 1280, height: int = 720) -> FramePacket:
    pixels = np.full((height, width, 3), 180, dtype=np.uint8)
    return FramePacket(
        pixels=pixels,
        width=width,
        height=height,
        channels=3,
        backend_label="opencv",
    )


def _stub_preprocess(packet: FramePacket, *, target_size: int = 640):
    # Return a minimal valid tensor shape + a matching letterbox transform.
    tensor = np.zeros((target_size, target_size, 3), dtype=np.uint8)
    transform = LetterboxTransform(
        target_width=target_size,
        target_height=target_size,
        original_width=packet.width,
        original_height=packet.height,
        scale=target_size / max(packet.width, packet.height),
        pad_left=0,
        pad_top=(target_size - int(round(packet.height * target_size / packet.width))) // 2,
        scaled_width=target_size,
        scaled_height=int(round(packet.height * target_size / packet.width)),
    )
    return tensor, transform


class _FakeDeviceManager:
    def __init__(self, *, ready: bool = True, open_raises: Exception | None = None) -> None:
        self._ready = ready
        self._open_raises = open_raises
        self.open_calls = 0

    def is_ready(self) -> bool:
        return self._ready

    def open(self) -> None:
        self.open_calls += 1
        if self._open_raises is not None:
            raise self._open_raises
        self._ready = True

    def vdevice(self):
        return object()

    def inference_lock(self) -> threading.Lock:
        return threading.Lock()


class _FakeInferenceRunner:
    """Stand-in for HefInferenceRunner with scripted inference results."""

    def __init__(
        self,
        scripted_results: list[HailoInferenceResult] | None = None,
        *,
        load_raises: Exception | None = None,
        infer_raises: Exception | None = None,
    ) -> None:
        self._scripted = scripted_results or []
        self._load_raises = load_raises
        self._infer_raises = infer_raises
        self.load_calls = 0
        self.infer_calls = 0
        self.unload_calls = 0
        self._loaded = False

    def load(self) -> None:
        self.load_calls += 1
        if self._load_raises is not None:
            raise self._load_raises
        self._loaded = True

    def unload(self) -> None:
        self.unload_calls += 1
        self._loaded = False

    def is_loaded(self) -> bool:
        return self._loaded

    def infer(self, tensor) -> HailoInferenceResult:
        del tensor
        self.infer_calls += 1
        if self._infer_raises is not None:
            raise self._infer_raises
        if self._scripted:
            return self._scripted.pop(0)
        return HailoInferenceResult()


def _result_with_one_person() -> HailoInferenceResult:
    return HailoInferenceResult(
        detections=(
            RawNmsDetection(
                class_index=0,  # person
                score=0.91,
                y_min=0.4, x_min=0.4, y_max=0.6, x_max=0.6,
            ),
        ),
        inference_ms=12.5,
    )


def _result_with_laptop() -> HailoInferenceResult:
    return HailoInferenceResult(
        detections=(
            RawNmsDetection(
                class_index=63,  # laptop
                score=0.77,
                y_min=0.45, x_min=0.3, y_max=0.75, x_max=0.7,
            ),
        ),
        inference_ms=14.1,
    )


class HailoYoloObjectDetectorCadenceTests(unittest.TestCase):

    def test_default_cadence_from_initial_value(self) -> None:
        detector = HailoYoloObjectDetector(initial_cadence_hz=3.0)
        self.assertAlmostEqual(detector.current_cadence_hz(), 3.0, places=3)
        self.assertFalse(detector.is_paused())

    def test_pause_sets_cadence_to_zero(self) -> None:
        detector = HailoYoloObjectDetector(initial_cadence_hz=5.0)
        detector.pause()
        self.assertTrue(detector.is_paused())
        self.assertEqual(detector.current_cadence_hz(), 0.0)

    def test_resume_restores_initial_cadence_by_default(self) -> None:
        detector = HailoYoloObjectDetector(initial_cadence_hz=4.0)
        detector.pause()
        detector.resume()
        self.assertAlmostEqual(detector.current_cadence_hz(), 4.0, places=3)
        self.assertFalse(detector.is_paused())

    def test_resume_with_explicit_hz(self) -> None:
        detector = HailoYoloObjectDetector(initial_cadence_hz=2.0)
        detector.pause()
        detector.resume(hz=10.0)
        self.assertAlmostEqual(detector.current_cadence_hz(), 10.0, places=3)

    def test_set_cadence_clamps_negative_to_zero(self) -> None:
        detector = HailoYoloObjectDetector()
        detector.set_inference_cadence_hz(-1.0)
        self.assertEqual(detector.current_cadence_hz(), 0.0)


class HailoYoloObjectDetectorInferenceTests(unittest.TestCase):

    def _build_detector(
        self,
        *,
        runner: _FakeInferenceRunner | None = None,
        manager: _FakeDeviceManager | None = None,
        cadence_hz: float = 100.0,
    ) -> HailoYoloObjectDetector:
        return HailoYoloObjectDetector(
            hef_path="/fake/model.hef",
            score_threshold=0.3,
            max_detections=30,
            initial_cadence_hz=cadence_hz,
            device_manager=manager or _FakeDeviceManager(),
            inference_runner=runner or _FakeInferenceRunner(
                scripted_results=[_result_with_one_person()],
            ),
            preprocess_fn=_stub_preprocess,
        )

    def test_first_call_runs_inference_and_returns_detections(self) -> None:
        runner = _FakeInferenceRunner(scripted_results=[_result_with_one_person()])
        detector = self._build_detector(runner=runner)

        result = detector.detect_objects(_make_packet())

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].label, "person")
        self.assertIsInstance(result[0], ObjectDetection)
        self.assertIsInstance(result[0].bounding_box, BoundingBox)
        self.assertEqual(runner.infer_calls, 1)

    def test_paused_detector_returns_empty_without_inference(self) -> None:
        runner = _FakeInferenceRunner(scripted_results=[_result_with_one_person()])
        detector = self._build_detector(runner=runner, cadence_hz=0.0)

        result = detector.detect_objects(_make_packet())

        self.assertEqual(result, ())
        self.assertEqual(runner.infer_calls, 0)

    def test_paused_after_successful_call_returns_last_detections(self) -> None:
        runner = _FakeInferenceRunner(
            scripted_results=[_result_with_one_person(), _result_with_laptop()],
        )
        detector = self._build_detector(runner=runner, cadence_hz=100.0)

        first = detector.detect_objects(_make_packet())
        detector.pause()
        second = detector.detect_objects(_make_packet())

        self.assertEqual(first, second)
        self.assertEqual(runner.infer_calls, 1)  # second call did not infer

    def test_cadence_throttles_inference_rate(self) -> None:
        runner = _FakeInferenceRunner(
            scripted_results=[
                _result_with_one_person(),
                _result_with_laptop(),
                _result_with_one_person(),
            ],
        )
        # 10 Hz cadence -> 100 ms between allowed inferences.
        detector = self._build_detector(runner=runner, cadence_hz=10.0)

        detector.detect_objects(_make_packet())
        # Second call immediately — should be throttled, reuse last result.
        detector.detect_objects(_make_packet())
        self.assertEqual(runner.infer_calls, 1)

        # Wait past the cadence interval.
        time.sleep(0.12)
        detector.detect_objects(_make_packet())
        self.assertEqual(runner.infer_calls, 2)

    def test_lazy_initialization_loads_runner_on_first_call(self) -> None:
        runner = _FakeInferenceRunner(scripted_results=[_result_with_one_person()])
        detector = self._build_detector(runner=runner)

        self.assertEqual(runner.load_calls, 0)
        detector.detect_objects(_make_packet())
        self.assertEqual(runner.load_calls, 1)

    def test_initialize_explicit_returns_true_on_success(self) -> None:
        runner = _FakeInferenceRunner(scripted_results=[_result_with_one_person()])
        detector = self._build_detector(runner=runner)

        ok = detector.initialize()
        self.assertTrue(ok)
        self.assertEqual(runner.load_calls, 1)

    def test_initialize_returns_false_when_device_unavailable(self) -> None:
        manager = _FakeDeviceManager(
            ready=False,
            open_raises=HailoUnavailableError("no device"),
        )
        detector = HailoYoloObjectDetector(
            device_manager=manager,
            preprocess_fn=_stub_preprocess,
        )

        ok = detector.initialize()
        self.assertFalse(ok)

        status = detector.status()
        self.assertIn("hailo_unavailable", status["unavailable_reason"])

    def test_detect_returns_empty_when_hailo_unavailable(self) -> None:
        manager = _FakeDeviceManager(
            ready=False,
            open_raises=HailoUnavailableError("no device"),
        )
        detector = HailoYoloObjectDetector(
            device_manager=manager,
            preprocess_fn=_stub_preprocess,
        )

        result = detector.detect_objects(_make_packet())
        self.assertEqual(result, ())

    def test_transient_inference_error_returns_last_known_detections(self) -> None:
        runner = _FakeInferenceRunner(scripted_results=[_result_with_one_person()])
        detector = self._build_detector(runner=runner)

        first = detector.detect_objects(_make_packet())
        self.assertEqual(len(first), 1)

        # Now inject a runtime error on the next inference.
        runner._infer_raises = HailoRuntimeError("boom")
        # Force throttle bypass by setting a very high cadence and pre-advancing time.
        detector.set_inference_cadence_hz(1000.0)
        time.sleep(0.01)

        second = detector.detect_objects(_make_packet())
        # Detector keeps last-known detections on transient error.
        self.assertEqual(second, first)

    def test_close_unloads_runner(self) -> None:
        runner = _FakeInferenceRunner(scripted_results=[_result_with_one_person()])
        detector = self._build_detector(runner=runner)
        detector.detect_objects(_make_packet())

        self.assertEqual(runner.unload_calls, 0)
        detector.close()
        self.assertEqual(runner.unload_calls, 1)

    def test_status_reports_backend_and_config(self) -> None:
        detector = HailoYoloObjectDetector(
            hef_path="/fake/model.hef",
            score_threshold=0.4,
            max_detections=25,
            desk_relevant_only=True,
            initial_cadence_hz=3.0,
            device_manager=_FakeDeviceManager(),
            inference_runner=_FakeInferenceRunner(),
            preprocess_fn=_stub_preprocess,
        )
        status = detector.status()

        self.assertEqual(status["backend"], "hailo_yolov11")
        self.assertEqual(status["hef_path"], "/fake/model.hef")
        self.assertAlmostEqual(status["score_threshold"], 0.4, places=3)
        self.assertEqual(status["max_detections"], 25)
        self.assertTrue(status["desk_relevant_only"])
        self.assertAlmostEqual(status["cadence_hz"], 3.0, places=3)
        self.assertFalse(status["paused"])


if __name__ == "__main__":
    unittest.main()