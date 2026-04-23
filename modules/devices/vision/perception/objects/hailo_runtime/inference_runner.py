# modules/devices/vision/perception/objects/hailo_runtime/inference_runner.py
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

import numpy as np

from modules.shared.logging.logger import get_logger

from .device_manager import HailoDeviceManager
from .errors import HailoRuntimeError, HailoUnavailableError
from .models import HailoInferenceResult, RawNmsDetection

LOGGER = get_logger(__name__)


class HefInferenceRunner:
    """
    Manages a single HEF model loaded on the shared HailoDeviceManager VDevice.

    Lifecycle:
        runner = HefInferenceRunner(manager, hef_path)
        runner.load()
        result = runner.infer(preprocessed_tensor)
        runner.unload()

    Responsibilities:
    - Load HEF and configure InferModel on the shared VDevice.
    - Serialize inference calls via the device manager inference_lock.
    - Parse HAILO_NMS_BY_CLASS output into RawNmsDetection tuples.
    - Track per-call timing for diagnostics.

    This runner is model-agnostic regarding class labels.
    """

    def __init__(
        self,
        device_manager: HailoDeviceManager,
        hef_path: str | Path,
        *,
        hailo_platform_module: Any | None = None,
    ) -> None:
        self._device_manager = device_manager
        self._hef_path = Path(hef_path)
        self._hailo_platform = hailo_platform_module

        self._lifecycle_lock = threading.RLock()
        self._loaded = False
        self._hef: Any | None = None
        self._infer_model: Any | None = None
        self._configured_infer_model: Any | None = None
        self._configure_context: Any | None = None
        self._input_vstream_info: Any | None = None
        self._output_vstream_info: Any | None = None
        self._input_shape: tuple[int, int, int] | None = None
        self._last_error: str | None = None

    def load(self) -> None:
        """Load and configure the HEF on the shared VDevice."""
        with self._lifecycle_lock:
            if self._loaded:
                return

            if not self._hef_path.exists():
                raise HailoRuntimeError(f"HEF file not found: {self._hef_path}")

            if not self._device_manager.is_ready():
                raise HailoUnavailableError(
                    "HailoDeviceManager is not ready. Call open() before loading HEF."
                )

            hp = self._resolve_hailo_platform()
            vdevice = self._device_manager.vdevice()

            try:
                self._hef = hp.HEF(str(self._hef_path))
                self._infer_model = vdevice.create_infer_model(str(self._hef_path))
                self._configure_context = self._infer_model.configure()
                self._configured_infer_model = self._configure_context.__enter__()

                input_infos = self._hef.get_input_vstream_infos()
                output_infos = self._hef.get_output_vstream_infos()
                if not input_infos or not output_infos:
                    raise HailoRuntimeError("HEF has no input or output vstreams.")

                self._input_vstream_info = input_infos[0]
                self._output_vstream_info = output_infos[0]
                self._input_shape = tuple(self._input_vstream_info.shape)

                self._loaded = True
                self._last_error = None
                LOGGER.info(
                    "HefInferenceRunner: loaded HEF %s, input_shape=%s, output=%s",
                    self._hef_path.name,
                    self._input_shape,
                    getattr(self._output_vstream_info, "name", "unknown"),
                )
            except HailoRuntimeError:
                raise
            except Exception as error:
                self._last_error = f"{error.__class__.__name__}: {error}"
                raise HailoRuntimeError(
                    f"Failed to load HEF {self._hef_path}: {error}"
                ) from error

    def unload(self) -> None:
        """Release references to the HEF and configured infer model."""
        with self._lifecycle_lock:
            if self._configure_context is not None:
                try:
                    self._configure_context.__exit__(None, None, None)
                except Exception as error:
                    LOGGER.warning(
                        "HefInferenceRunner: error during configured model release. %s",
                        error,
                    )

            self._configure_context = None
            self._configured_infer_model = None
            self._infer_model = None
            self._input_vstream_info = None
            self._output_vstream_info = None
            self._input_shape = None
            self._hef = None
            self._loaded = False
            LOGGER.info("HefInferenceRunner: unloaded HEF %s.", self._hef_path.name)

    def is_loaded(self) -> bool:
        with self._lifecycle_lock:
            return self._loaded

    def input_shape(self) -> tuple[int, int, int]:
        """Return (height, width, channels) of the HEF input."""
        with self._lifecycle_lock:
            if self._input_shape is None:
                raise HailoRuntimeError("Runner not loaded — input_shape is unavailable.")
            return self._input_shape

    def infer(self, preprocessed_tensor: Any) -> HailoInferenceResult:
        """
        Run a single inference pass.

        preprocessed_tensor must match the HEF input shape exactly
        (HxWxC UINT8 for YOLOv11m_h10).

        Returns a HailoInferenceResult with parsed NMS detections.
        """
        with self._lifecycle_lock:
            if (
                not self._loaded
                or self._configured_infer_model is None
                or self._infer_model is None
            ):
                raise HailoRuntimeError("HefInferenceRunner.infer() called before load().")

        inference_lock = self._device_manager.inference_lock()
        raw_output = None
        inference_start = time.perf_counter()

        with inference_lock:
            try:
                output_name = self._output_vstream_info.name
                output_buffers = {
                    output_name: np.empty(
                        self._infer_model.output(output_name).shape,
                        dtype=self._resolve_output_numpy_dtype(),
                    )
                }

                bindings = self._configured_infer_model.create_bindings(
                    output_buffers=output_buffers
                )
                bindings.input().set_buffer(np.asarray(preprocessed_tensor))
                self._configured_infer_model.run([bindings], 10000)
                raw_output = self._binding_output_buffer(bindings, output_name)
            except Exception as error:
                self._last_error = f"{error.__class__.__name__}: {error}"
                raise HailoRuntimeError(f"Inference failed: {error}") from error

        inference_ms = (time.perf_counter() - inference_start) * 1000.0

        postprocess_start = time.perf_counter()
        detections = self._parse_nms_by_class_output(raw_output)
        postprocess_ms = (time.perf_counter() - postprocess_start) * 1000.0

        return HailoInferenceResult(
            detections=detections,
            inference_ms=inference_ms,
            postprocess_ms=postprocess_ms,
            metadata={
                "hef_name": self._hef_path.name,
                "input_shape": list(self._input_shape) if self._input_shape else [],
            },
        )

    def status(self) -> dict[str, Any]:
        with self._lifecycle_lock:
            return {
                "hef_path": str(self._hef_path),
                "loaded": self._loaded,
                "input_shape": list(self._input_shape) if self._input_shape else [],
                "last_error": self._last_error,
            }

    def _parse_nms_by_class_output(self, raw_output: Any) -> tuple[RawNmsDetection, ...]:
        """
        Parse HAILO_NMS_BY_CLASS output into a flat tuple of RawNmsDetection.
        """
        if raw_output is None:
            return ()

        detections: list[RawNmsDetection] = []
        per_class_arrays = self._unwrap_nms_output(raw_output)

        for class_index, class_rows in enumerate(per_class_arrays):
            if class_rows is None:
                continue

            for row in class_rows:
                if len(row) < 5:
                    continue

                y_min = float(row[0])
                x_min = float(row[1])
                y_max = float(row[2])
                x_max = float(row[3])
                score = float(row[4])

                if score <= 0.0:
                    continue
                if x_max <= x_min or y_max <= y_min:
                    continue

                detections.append(
                    RawNmsDetection(
                        class_index=int(class_index),
                        score=score,
                        y_min=y_min,
                        x_min=x_min,
                        y_max=y_max,
                        x_max=x_max,
                    )
                )

        return tuple(detections)

    @staticmethod
    def _unwrap_nms_output(raw_output: Any) -> list[Any]:
        """
        Normalize the HAILO_NMS_BY_CLASS output into a list indexed by class.
        """
        if isinstance(raw_output, list):
            return list(raw_output)

        shape = getattr(raw_output, "shape", None)
        if shape is not None:
            if len(shape) == 2 and shape[0] == 1:
                return [raw_output[0, i] for i in range(shape[1])]
            if len(shape) == 1:
                return [raw_output[i] for i in range(shape[0])]

        try:
            return list(raw_output)
        except TypeError:
            return []

    def _binding_output_buffer(self, bindings: Any, output_name: str) -> Any:
        output_method = getattr(bindings, "output")
        try:
            return output_method(output_name).get_buffer()
        except TypeError:
            return output_method().get_buffer()

    def _resolve_output_numpy_dtype(self) -> Any:
        output_format = getattr(getattr(self._output_vstream_info, "format", None), "type", None)
        output_format_name = str(output_format).split(".")[-1].upper()
        mapping = {
            "UINT8": np.uint8,
            "UINT16": np.uint16,
            "FLOAT32": np.float32,
        }
        return mapping.get(output_format_name, np.float32)

    def _resolve_hailo_platform(self) -> Any:
        if self._hailo_platform is not None:
            return self._hailo_platform

        try:
            import hailo_platform as hp
        except ImportError as error:
            raise HailoUnavailableError(
                "hailo_platform Python module is not installed."
            ) from error

        self._hailo_platform = hp
        return hp