from __future__ import annotations

import threading
import unittest
from pathlib import Path

import numpy as np

from modules.devices.vision.perception.objects.hailo_runtime.errors import (
    HailoRuntimeError,
    HailoUnavailableError,
)
from modules.devices.vision.perception.objects.hailo_runtime.inference_runner import (
    HefInferenceRunner,
)


class _FakeConfiguredInferModel:
    def __init__(self, output_name: str, output_tensor) -> None:
        self.output_name = output_name
        self.output_tensor = output_tensor
        self.run_calls = 0

    def create_bindings(self, output_buffers=None):
        del output_buffers
        return _FakeBindings(self.output_name, self.output_tensor)

    def run(self, bindings_list, timeout_ms):
        del timeout_ms
        self.run_calls += 1
        return bindings_list


class _FakeConfigureContext:
    def __init__(self, configured_model: _FakeConfiguredInferModel) -> None:
        self._configured_model = configured_model

    def __enter__(self):
        return self._configured_model

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeInferModelIO:
    def __init__(self, shape=(640, 640, 3)) -> None:
        self.shape = shape


class _FakeInferModel:
    def __init__(self, output_name: str, output_tensor) -> None:
        self._configured_model = _FakeConfiguredInferModel(output_name, output_tensor)
        self._input = _FakeInferModelIO(shape=(640, 640, 3))
        self._output = _FakeInferModelIO(shape=(80,))

    def configure(self):
        return _FakeConfigureContext(self._configured_model)

    def input(self):
        return self._input

    def output(self, name=None):
        del name
        return self._output


class _FakeVDevice:
    def __init__(self, output_name: str, output_tensor) -> None:
        self.create_infer_model_calls = 0
        self._output_name = output_name
        self._output_tensor = output_tensor

    def create_infer_model(self, hef_path: str):
        del hef_path
        self.create_infer_model_calls += 1
        return _FakeInferModel(self._output_name, self._output_tensor)


class _FakeBufferHolder:
    def __init__(self, output_tensor) -> None:
        self._output_tensor = output_tensor
        self.input_buffer = None

    def set_buffer(self, buffer):
        self.input_buffer = buffer

    def get_buffer(self):
        return self._output_tensor


class _FakeBindings:
    def __init__(self, output_name: str, output_tensor) -> None:
        self._input_holder = _FakeBufferHolder(output_tensor)
        self._output_holders = {
            output_name: _FakeBufferHolder(output_tensor)
        }

    def input(self):
        return self._input_holder

    def output(self, name=None):
        if name is None:
            return next(iter(self._output_holders.values()))
        return self._output_holders[name]


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


def _build_fake_hailo_platform_for_runner(output_tensor):
    class _FakeFormat:
        type = "FLOAT32"

    class _FakeInfo:
        def __init__(self, name, shape):
            self.name = name
            self.shape = shape
            self.format = _FakeFormat()

    class _FakeHef:
        def get_input_vstream_infos(self):
            return [_FakeInfo("yolov11m/input_layer1", (640, 640, 3))]

        def get_output_vstream_infos(self):
            return [_FakeInfo("yolov11m/yolov8_nms_postprocess", (80,))]

    class _FakeHp:
        def HEF(self, path):
            del path
            return _FakeHef()

    fake_hp = _FakeHp()
    fake_vdevice = _FakeVDevice("yolov11m/yolov8_nms_postprocess", output_tensor)
    return fake_hp, fake_vdevice


class HefInferenceRunnerTests(unittest.TestCase):
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

    def _setup_loaded_runner(self, output_tensor):
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".hef", delete=False)
        tmp.write(b"fake hef bytes")
        tmp.close()
        tmp_path = Path(tmp.name)

        fake_hp, fake_vdevice = _build_fake_hailo_platform_for_runner(output_tensor)
        mgr = _FakeDeviceManager(vdevice=fake_vdevice, ready=True)

        runner = HefInferenceRunner(
            mgr,
            hef_path=tmp_path,
            hailo_platform_module=fake_hp,
        )
        runner.load()
        return runner, tmp_path, fake_vdevice

    def test_load_reads_input_shape(self) -> None:
        runner, tmp_path, _ = self._setup_loaded_runner(output_tensor=[])
        try:
            self.assertEqual(runner.input_shape(), (640, 640, 3))
            self.assertTrue(runner.is_loaded())
        finally:
            runner.unload()
            tmp_path.unlink(missing_ok=True)

    def test_infer_parses_list_of_per_class_arrays(self) -> None:
        output_list = [np.zeros((0, 5), dtype=np.float32) for _ in range(80)]
        output_list[0] = np.array([[0.1, 0.2, 0.5, 0.6, 0.91]], dtype=np.float32)
        output_list[63] = np.array(
            [
                [0.3, 0.4, 0.7, 0.8, 0.82],
                [0.05, 0.05, 0.15, 0.15, 0.55],
            ],
            dtype=np.float32,
        )

        runner, tmp_path, fake_vdevice = self._setup_loaded_runner(output_tensor=output_list)
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

            self.assertEqual(fake_vdevice.create_infer_model_calls, 1)
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