from __future__ import annotations

from modules.devices.vision.config import VisionRuntimeConfig
from modules.devices.vision.perception.face import FaceDetector, NullFaceDetector, OpenCvHaarFaceDetector
from modules.devices.vision.perception.objects import (
    HailoYoloObjectDetector,
    NullObjectDetector,
    ObjectDetector,
)
from modules.devices.vision.perception.people import (
    HybridFacePrimaryPeopleDetector,
    NullPeopleDetector,
    OpenCvHogPeopleDetector,
    PeopleDetector,
)


def _build_opencv_hog_detector(config: VisionRuntimeConfig) -> OpenCvHogPeopleDetector:
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


def _build_opencv_haar_face_detector(config: VisionRuntimeConfig) -> OpenCvHaarFaceDetector:
    return OpenCvHaarFaceDetector(
        min_area_ratio=config.face_detector_min_area_ratio,
        use_clahe=config.face_detector_use_clahe,
        roi_enabled=config.face_detector_roi_enabled,
    )


def build_people_detector(config: VisionRuntimeConfig) -> PeopleDetector:
    if not config.people_detector_is_active():
        return NullPeopleDetector()

    backend = config.people_detector_backend
    if backend == "opencv_hog":
        return _build_opencv_hog_detector(config)

    if backend == "hybrid_face_primary":
        # For the hybrid backend, we build our own internal face detector
        # so presence works even when face_detection_enabled is False at the
        # pipeline level. If face detection is enabled globally, the pipeline
        # face detector runs independently and both are fine.
        internal_face_detector: FaceDetector
        face_backend = config.face_detector_backend
        if face_backend == "opencv_haar":
            internal_face_detector = _build_opencv_haar_face_detector(config)
        else:
            internal_face_detector = NullFaceDetector()

        secondary_detector = None
        if config.people_detector_hybrid_use_hog_secondary:
            secondary_detector = _build_opencv_hog_detector(config)

        return HybridFacePrimaryPeopleDetector(
            face_detector=internal_face_detector,
            secondary_detector=secondary_detector,
            body_width_multiplier=config.people_detector_hybrid_body_width_multiplier,
            body_height_multiplier=config.people_detector_hybrid_body_height_multiplier,
        )

    raise ValueError(f"Unsupported people detector backend: {backend}")


def build_face_detector(config: VisionRuntimeConfig) -> FaceDetector:
    if not config.face_detector_is_active():
        return NullFaceDetector()

    backend = config.face_detector_backend
    if backend == "opencv_haar":
        return _build_opencv_haar_face_detector(config)

    raise ValueError(f"Unsupported face detector backend: {backend}")


def build_object_detector(config: VisionRuntimeConfig) -> ObjectDetector:
    if not config.object_detector_is_active():
        return NullObjectDetector()

    backend = config.object_detector_backend
    if backend == "hailo_yolov11":
        return HailoYoloObjectDetector(
            hef_path=config.object_detector_hailo_hef_path,
            score_threshold=config.object_detector_hailo_score_threshold,
            max_detections=config.object_detector_hailo_max_detections,
            desk_relevant_only=config.object_detector_hailo_desk_relevant_only,
            initial_cadence_hz=config.object_detector_hailo_initial_cadence_hz,
        )

    raise ValueError(f"Unsupported object detector backend: {backend}")