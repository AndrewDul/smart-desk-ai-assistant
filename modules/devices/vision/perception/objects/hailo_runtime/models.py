# modules/devices/vision/perception/objects/hailo_runtime/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class RawNmsDetection:
    """
    A single detection as returned by Hailo NMS_BY_CLASS output.

    Coordinates are normalized to [0.0, 1.0] in the model input space
    (i.e. the 640x640 square the chip processed). Downstream code is
    responsible for mapping these back to the original camera frame.
    """

    class_index: int
    score: float
    y_min: float
    x_min: float
    y_max: float
    x_max: float


@dataclass(frozen=True, slots=True)
class HailoInferenceResult:
    """Structured result of a single Hailo inference call."""

    detections: tuple[RawNmsDetection, ...] = ()
    inference_ms: float = 0.0
    preprocess_ms: float = 0.0
    postprocess_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)