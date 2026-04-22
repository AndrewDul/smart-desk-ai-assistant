from __future__ import annotations

from modules.devices.vision.config import VisionRuntimeConfig
from modules.devices.vision.perception.face import FaceDetector, NullFaceDetector, OpenCvHaarFaceDetector
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
            min_height_ratio=config.people_detector_min_height_ratio,
            max_width_ratio=config.people_detector_max_width_ratio,
            use_clahe=config.people_detector_use_clahe,
            upscale_factor=config.people_detector_upscale_factor,
            desk_roi_enabled=config.people_detector_desk_roi_enabled,
            desk_roi_bounds=(
                config.people_detector_roi_x_min,
                config.people_detector_roi_y_min,
                config.people_detector_roi_x_max,
                config.people_detector_roi_y_max,
            ),
        )

    raise ValueError(f"Unsupported people detector backend: {backend}")


def build_face_detector(config: VisionRuntimeConfig) -> FaceDetector:
    if not config.face_detector_is_active():
        return NullFaceDetector()

    backend = config.face_detector_backend
    if backend == "opencv_haar":
        return OpenCvHaarFaceDetector(
            min_area_ratio=config.face_detector_min_area_ratio,
            use_clahe=config.face_detector_use_clahe,
            roi_enabled=config.face_detector_roi_enabled,
        )

    raise ValueError(f"Unsupported face detector backend: {backend}")


def build_object_detector(config: VisionRuntimeConfig) -> ObjectDetector:
    if not config.object_detector_is_active():
        return NullObjectDetector()

    backend = config.object_detector_backend
    raise ValueError(f"Unsupported object detector backend: {backend}")