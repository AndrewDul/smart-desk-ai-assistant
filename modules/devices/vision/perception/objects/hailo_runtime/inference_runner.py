# modules/devices/vision/perception/objects/hailo_runtime/inference_runner.py
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any

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
        result = runner.infer(preprocessed_tensor)   # called repeatedly
        runner.unload()

    Responsibilities:
    - Load HEF, configure inference model, prepare input/output streams.
    - Serialize inference calls via the device manager inference_lock.
    - Parse HAILO_NMS_BY_CLASS output into RawNmsDetection tuples.
    - Track per-call timing for diagnostics.

    This runner is model-agnostic regarding class labels — it returns
    class indices as emitted by the HEF. Class-index-to-name mapping is
    the job of the higher-level object detector.
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
        self._network_group: Any | None = None
        self._network_group_params: Any | None = None
        self._input_vstream_info: Any | None = None
        self._output_vstream_info: Any | None = None
        self._input_shape: tuple[int, int, int] | None = None
        self._last_error: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
                configure_params = hp.ConfigureParams.create_from_hef(
                    hef=self._hef,
                    interface=hp.HailoStreamInterface.PCIe,
                )
                network_groups = vdevice.configure(self._hef, configure_params)
                if not network_groups:
                    raise HailoRuntimeError("No network groups returned from configure().")
                self._network_group = network_groups[0]
                self._network_group_params = self._network_group.create_params()

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
        """Release references to the HEF and network group."""
        with self._lifecycle_lock:
            self._network_group = None
            self._network_group_params = None
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
        (HxWxC UINT8 for YOLOv11m_h10). The runner serializes the call behind
        the device inference_lock.

        Returns a HailoInferenceResult with parsed NMS detections.
        """
        with self._lifecycle_lock:
            if not self._loaded:
                raise HailoRuntimeError("HefInferenceRunner.infer() called before load().")

        inference_lock = self._device_manager.inference_lock()
        hp = self._resolve_hailo_platform()

        raw_output = None
        inference_start = time.perf_counter()

        with inference_lock:
            try:
                input_name = self._input_vstream_info.name
                input_dict = {input_name: preprocessed_tensor}

                input_params = hp.InputVStreamParams.make_from_network_group(
                    self._network_group
                )
                output_params = hp.OutputVStreamParams.make_from_network_group(
                    self._network_group
                )

                with self._network_group.activate(self._network_group_params):
                    with hp.InferVStreams(
                        self._network_group,
                        input_params,
                        output_params,
                    ) as infer_pipeline:
                        output_dict = infer_pipeline.infer(input_dict)

                output_name = self._output_vstream_info.name
                raw_output = output_dict.get(output_name)
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

    # ------------------------------------------------------------------
    # NMS_BY_CLASS parser
    # ------------------------------------------------------------------

    def _parse_nms_by_class_output(self, raw_output: Any) -> tuple[RawNmsDetection, ...]:
        """
        Parse HAILO_NMS_BY_CLASS output into a flat tuple of RawNmsDetection.

        The output is structured as a list (or numpy array) with one entry per
        class. Each entry contains zero or more rows of shape [5] representing
        [y_min, x_min, y_max, x_max, score] in normalized [0.0, 1.0] coords.

        This layout is the HailoRT contract for HAILO_NMS_BY_CLASS and is
        documented in the HailoRT user guide.
        """
        if raw_output is None:
            return ()

        detections: list[RawNmsDetection] = []

        # HailoRT returns a list of per-class numpy arrays, one per class index.
        # In some builds it's a batch-dim wrapped structure — handle both cases.
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

        Handles two shapes we've observed in HailoRT:
        - list[class_index] -> np.ndarray with shape (N, 5)
        - np.ndarray with shape (1, num_classes) where dtype is object
          and each cell holds the per-class ndarray.
        """
        # Plain Python list already indexed by class.
        if isinstance(raw_output, list):
            return list(raw_output)

        # Numpy object array — batch wrapper.
        shape = getattr(raw_output, "shape", None)
        if shape is not None:
            if len(shape) == 2 and shape[0] == 1:
                return [raw_output[0, i] for i in range(shape[1])]
            if len(shape) == 1:
                return [raw_output[i] for i in range(shape[0])]

        # Fallback: try to iterate once.
        try:
            return list(raw_output)
        except TypeError:
            return []

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

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