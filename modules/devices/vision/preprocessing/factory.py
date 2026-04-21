from __future__ import annotations

from modules.devices.vision.config import VisionRuntimeConfig
from modules.devices.vision.perception.objects import NullObjectDetector, ObjectDetector
from modules.devices.vision.perception.people import (
    NullPeopleDetector,
    OpenCvHogPeopleDetector,
    PeopleDetector,
)


def build_people_detector(config: VisionRuntimeConfig) -> PeopleDetector:
    if not config.people_detector_is_active():
        return NullPeopleDetector()

    backend = config.people_detector_backend
    if backend == "opencv_hog":
        return OpenCvHogPeopleDetector(
            min_confidence=config.people_detector_min_confidence,
            min_area_ratio=config.people_detector_min_area_ratio,
        )

    raise ValueError(f"Unsupported people detector backend: {backend}")


def build_object_detector(config: VisionRuntimeConfig) -> ObjectDetector:
    if not config.object_detector_is_active():
        return NullObjectDetector()

    backend = config.object_detector_backend
    raise ValueError(f"Unsupported object detector backend: {backend}")