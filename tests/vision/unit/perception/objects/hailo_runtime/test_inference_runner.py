# tests/vision/unit/perception/objects/hailo_runtime/test_inference_runner.py
from __future__ import annotations

import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np

from modules.devices.vision.perception.objects.hailo_runtime.device_manager import (
    HailoDeviceManager,
)
from modules.devices.vision.perception.objects.hailo_runtime.errors import (
    HailoRuntimeError,
    HailoUnavailableError,
)
from modules.devices.vision.perception.objects.hailo_runtime.inference_runner import (
    HefInferenceRunner,
)


def _build_fake_hailo_platform_for_runner(output_tensor):
    fake = MagicMock(name="hailo_platform_for_runner")
    fake.HailoStreamInterface.PCIe = "PCIe"

    # HEF
    fake_hef = MagicMock(name="fake_hef")
    input_info = MagicMock(name="input_info")
    input_info.name = "yolov11m/input_layer1"
    input_info.shape = (640, 640, 3)
    output_info = MagicMock(name="output_info")
    output_info.name = "yolov11m/yolov8_nms_postprocess"
    fake_hef.get_input_vstream_infos.return_value = [input_info]
    fake_hef.get_output_vstream_infos.return_value = [output_info]
    fake.HEF.return_value = fake_hef

    fake.ConfigureParams.create_from_hef.return_value = "configure_params_obj"

    # Network group + activation + infer
    fake_network_group = MagicMock(name="fake_network_group")
    fake_network_group.create_params.return_value = "network_group_params_obj"

    activation_context = MagicMock(name="activation_context")
    activation_context.__enter__ = MagicMock(return_value=None)
    activation_context.__exit__ = MagicMock(return_value=False)
    fake_network_group.activate.return_value = activation_context

    # InferVStreams context
    fake_infer_pipeline = MagicMock(name="infer_pipeline")
    fake_infer_pipeline.infer.return_value = {
        output_info.name: output_tensor
    }
    infer_context = MagicMock(name="infer_context")
    infer_context.__enter__ = MagicMock(return_value=fake_infer_pipeline)
    infer_context.__exit__ = MagicMock(return_value=False)
    fake.InferVStreams.return_value = infer_context

    fake.InputVStreamParams.make_from_network_group.return_value = "input_params"
    fake.OutputVStreamParams.make_from_network_group.return_value = "output_params"

    return fake, fake_network_group, fake_infer_pipeline


class _FakeVDevice:
    def __init__(self, network_groups):
        self._network_groups = network_groups
        self.configure_calls = 0

    def configure(self, hef, params):
        del hef, params
        self.configure_calls += 1
        return self._network_groups


class _FakeDeviceManager:
    """Minimal HailoDeviceManager stand-in for runner tests."""

    def __init__(self, vdevice, ready: bool = True):
        self._vdevice = vdevice
        self._ready = ready
        self._lock = threading.Lock()

    def is_ready(self):
        return self._ready

    def vdevice(self):
        if not self._ready:
            raise HailoUnavailableError("not ready")
        return self._vdevice

    def inference_lock(self):
        return self._lock


class HefInferenceRunnerTests(unittest.TestCase):

    # ------------------------------------------------------------------
    # HEF path validation
    # ------------------------------------------------------------------

    def test_load_raises_when_hef_missing(self) -> None:
        mgr = _FakeDeviceManager(vdevice=None, ready=True)
        runner = HefInferenceRunner(
            mgr,
            hef_path=Path("/tmp/does_not_exist.hef"),
        )
        with self.assertRaises(HailoRuntimeError):
            runner.load()

    def test_load_raises_when_device_not_ready(self, tmp_hef_path: Path | None = None) -> None:
        mgr = _FakeDeviceManager(vdevice=None, ready=False)

        # Use a real temp file so we pass the existence check
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".hef", delete=False) as tmp:
            tmp.write(b"fake hef bytes")
            tmp_path = Path(tmp.name)

        try:
            runner = HefInferenceRunner(mgr, hef_path=tmp_path)
            with self.assertRaises(HailoUnavailableError):
                runner.load()
        finally:
            tmp_path.unlink(missing_ok=True)

    # ------------------------------------------------------------------
    # End-to-end inference with fakes
    # ------------------------------------------------------------------

    def _setup_loaded_runner(self, output_tensor):
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".hef", delete=False)
        tmp.write(b"fake hef bytes")
        tmp.close()
        tmp_path = Path(tmp.name)

        fake_hp, fake_network_group, fake_infer_pipeline = _build_fake_hailo_platform_for_runner(output_tensor)
        fake_vdevice = _FakeVDevice(network_groups=[fake_network_group])
        mgr = _FakeDeviceManager(vdevice=fake_vdevice, ready=True)

        runner = HefInferenceRunner(
            mgr,
            hef_path=tmp_path,
            hailo_platform_module=fake_hp,
        )
        runner.load()
        return runner, tmp_path, fake_infer_pipeline

    def test_load_reads_input_shape(self) -> None:
        runner, tmp_path, _ = self._setup_loaded_runner(output_tensor=[])
        try:
            self.assertEqual(runner.input_shape(), (640, 640, 3))
            self.assertTrue(runner.is_loaded())
        finally:
            runner.unload()
            tmp_path.unlink(missing_ok=True)

    def test_infer_parses_list_of_per_class_arrays(self) -> None:
        # Simulate HAILO_NMS_BY_CLASS output: list of 80 per-class arrays.
        output_list = [np.zeros((0, 5), dtype=np.float32) for _ in range(80)]
        # Class 0 (person) — one detection
        output_list[0] = np.array([[0.1, 0.2, 0.5, 0.6, 0.91]], dtype=np.float32)
        # Class 63 (laptop in COCO) — two detections
        output_list[63] = np.array(
            [
                [0.3, 0.4, 0.7, 0.8, 0.82],
                [0.05, 0.05, 0.15, 0.15, 0.55],
            ],
            dtype=np.float32,
        )

        runner, tmp_path, fake_infer_pipeline = self._setup_loaded_runner(output_tensor=output_list)
        try:
            dummy_input = np.zeros((640, 640, 3), dtype=np.uint8)
            result = runner.infer(dummy_input)

            self.assertEqual(len(result.detections), 3)

            person_hits = [d for d in result.detections if d.class_index == 0]
            laptop_hits = [d for d in result.detections if d.class_index == 63]
            self.assertEqual(len(person_hits), 1)
            self.assertEqual(len(laptop_hits), 2)

            person = person_hits[0]
            self.assertAlmostEqual(person.y_min, 0.1, places=4)
            self.assertAlmostEqual(person.x_min, 0.2, places=4)
            self.assertAlmostEqual(person.y_max, 0.5, places=4)
            self.assertAlmostEqual(person.x_max, 0.6, places=4)
            self.assertAlmostEqual(person.score, 0.91, places=4)

            # Infer was called with our tensor
            fake_infer_pipeline.infer.assert_called_once()
            self.assertGreaterEqual(result.inference_ms, 0.0)
        finally:
            runner.unload()
            tmp_path.unlink(missing_ok=True)

    def test_infer_handles_empty_output(self) -> None:
        output_list = [np.zeros((0, 5), dtype=np.float32) for _ in range(80)]
        runner, tmp_path, _ = self._setup_loaded_runner(output_tensor=output_list)
        try:
            dummy_input = np.zeros((640, 640, 3), dtype=np.uint8)
            result = runner.infer(dummy_input)
            self.assertEqual(result.detections, ())
        finally:
            runner.unload()
            tmp_path.unlink(missing_ok=True)

    def test_infer_rejects_zero_area_boxes(self) -> None:
        output_list = [np.zeros((0, 5), dtype=np.float32) for _ in range(80)]
        # Degenerate box where x_max == x_min — should be rejected
        output_list[0] = np.array([[0.1, 0.2, 0.5, 0.2, 0.9]], dtype=np.float32)

        runner, tmp_path, _ = self._setup_loaded_runner(output_tensor=output_list)
        try:
            dummy_input = np.zeros((640, 640, 3), dtype=np.uint8)
            result = runner.infer(dummy_input)
            self.assertEqual(result.detections, ())
        finally:
            runner.unload()
            tmp_path.unlink(missing_ok=True)

    def test_infer_rejects_zero_score_boxes(self) -> None:
        output_list = [np.zeros((0, 5), dtype=np.float32) for _ in range(80)]
        output_list[0] = np.array([[0.1, 0.2, 0.5, 0.6, 0.0]], dtype=np.float32)

        runner, tmp_path, _ = self._setup_loaded_runner(output_tensor=output_list)
        try:
            dummy_input = np.zeros((640, 640, 3), dtype=np.uint8)
            result = runner.infer(dummy_input)
            self.assertEqual(result.detections, ())
        finally:
            runner.unload()
            tmp_path.unlink(missing_ok=True)

    def test_infer_before_load_raises(self) -> None:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".hef", delete=False)
        tmp.write(b"x")
        tmp.close()
        tmp_path = Path(tmp.name)

        try:
            mgr = _FakeDeviceManager(vdevice=None, ready=True)
            runner = HefInferenceRunner(mgr, hef_path=tmp_path)

            with self.assertRaises(HailoRuntimeError):
                runner.infer(np.zeros((640, 640, 3), dtype=np.uint8))
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_unload_resets_state(self) -> None:
        output_list = [np.zeros((0, 5), dtype=np.float32) for _ in range(80)]
        runner, tmp_path, _ = self._setup_loaded_runner(output_tensor=output_list)
        try:
            self.assertTrue(runner.is_loaded())
            runner.unload()
            self.assertFalse(runner.is_loaded())
            with self.assertRaises(HailoRuntimeError):
                runner.input_shape()
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()