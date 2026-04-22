from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _clamp_float(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


@dataclass(frozen=True, slots=True)
class VisionRuntimeConfig:
    enabled: bool
    backend: str
    fallback_backend: str
    camera_index: int
    frame_width: int
    frame_height: int
    warmup_seconds: float
    capture_timeout_seconds: float
    lazy_start: bool
    hflip: bool
    vflip: bool
    people_detection_enabled: bool
    people_detector_backend: str
    people_detector_min_confidence: float
    people_detector_min_area_ratio: float
    people_detector_min_height_ratio: float
    people_detector_max_width_ratio: float
    people_detector_use_clahe: bool
    people_detector_upscale_factor: float
    people_detector_desk_roi_enabled: bool
    people_detector_roi_x_min: float
    people_detector_roi_y_min: float
    people_detector_roi_x_max: float
    people_detector_roi_y_max: float
    face_detection_enabled: bool
    face_detector_backend: str
    face_detector_min_area_ratio: float
    face_detector_use_clahe: bool
    face_detector_roi_enabled: bool
    object_detection_enabled: bool
    object_detector_backend: str
    scene_understanding_enabled: bool
    gesture_recognition_enabled: bool
    behavior_interpretation_enabled: bool
    temporal_stabilization_enabled: bool
    temporal_stabilization_activation_hits: int
    temporal_stabilization_deactivation_hits: int
    temporal_stabilization_hold_seconds: float
    continuous_capture_enabled: bool
    continuous_capture_target_fps: float
    continuous_capture_error_backoff_seconds: float
    continuous_capture_stop_timeout_seconds: float
    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> "VisionRuntimeConfig":
        payload = dict(raw or {})
        roi_x_min = _clamp_float(payload.get("people_detector_roi_x_min", 0.10), 0.0, 1.0)
        roi_y_min = _clamp_float(payload.get("people_detector_roi_y_min", 0.08), 0.0, 1.0)
        roi_x_max = _clamp_float(payload.get("people_detector_roi_x_max", 0.90), 0.0, 1.0)
        roi_y_max = _clamp_float(payload.get("people_detector_roi_y_max", 0.98), 0.0, 1.0)

        if roi_x_max <= roi_x_min:
            roi_x_min, roi_x_max = 0.10, 0.90
        if roi_y_max <= roi_y_min:
            roi_y_min, roi_y_max = 0.08, 0.98

        return cls(
            enabled=bool(payload.get("enabled", False)),
            backend=str(payload.get("backend", "picamera2") or "picamera2").strip().lower(),
            fallback_backend=str(payload.get("fallback_backend", "opencv") or "opencv").strip().lower(),
            camera_index=max(0, int(payload.get("camera_index", 0))),
            frame_width=max(160, int(payload.get("frame_width", 1280))),
            frame_height=max(120, int(payload.get("frame_height", 720))),
            warmup_seconds=max(0.0, float(payload.get("warmup_seconds", 0.35))),
            capture_timeout_seconds=max(0.05, float(payload.get("capture_timeout_seconds", 2.0))),
            lazy_start=bool(payload.get("lazy_start", True)),
            hflip=bool(payload.get("hflip", False)),
            vflip=bool(payload.get("vflip", False)),
            people_detection_enabled=bool(payload.get("people_detection_enabled", False)),
            people_detector_backend=str(payload.get("people_detector_backend", "opencv_hog") or "opencv_hog").strip().lower(),
            people_detector_min_confidence=_clamp_float(payload.get("people_detector_min_confidence", 0.45), 0.0, 1.0),
            people_detector_min_area_ratio=_clamp_float(payload.get("people_detector_min_area_ratio", 0.025), 0.0, 1.0),
            people_detector_min_height_ratio=_clamp_float(payload.get("people_detector_min_height_ratio", 0.18), 0.0, 1.0),
            people_detector_max_width_ratio=_clamp_float(payload.get("people_detector_max_width_ratio", 0.85), 0.0, 1.0),
            people_detector_use_clahe=bool(payload.get("people_detector_use_clahe", True)),
            people_detector_upscale_factor=max(1.0, float(payload.get("people_detector_upscale_factor", 1.35))),
            people_detector_desk_roi_enabled=bool(payload.get("people_detector_desk_roi_enabled", True)),
            people_detector_roi_x_min=roi_x_min,
            people_detector_roi_y_min=roi_y_min,
            people_detector_roi_x_max=roi_x_max,
            people_detector_roi_y_max=roi_y_max,
            face_detection_enabled=bool(payload.get("face_detection_enabled", False)),
            face_detector_backend=str(payload.get("face_detector_backend", "opencv_haar") or "opencv_haar").strip().lower(),
            face_detector_min_area_ratio=_clamp_float(payload.get("face_detector_min_area_ratio", 0.002), 0.0, 1.0),
            face_detector_use_clahe=bool(payload.get("face_detector_use_clahe", True)),
            face_detector_roi_enabled=bool(payload.get("face_detector_roi_enabled", True)),
            object_detection_enabled=bool(payload.get("object_detection_enabled", False)),
            object_detector_backend=str(payload.get("object_detector_backend", "null") or "null").strip().lower(),
            scene_understanding_enabled=bool(payload.get("scene_understanding_enabled", False)),
            gesture_recognition_enabled=bool(payload.get("gesture_recognition_enabled", False)),
            behavior_interpretation_enabled=bool(payload.get("behavior_interpretation_enabled", False)),
            temporal_stabilization_enabled=bool(payload.get("temporal_stabilization_enabled", True)),
            temporal_stabilization_activation_hits=max(1, int(payload.get("temporal_stabilization_activation_hits", 2))),
            temporal_stabilization_deactivation_hits=max(1, int(payload.get("temporal_stabilization_deactivation_hits", 2))),
            temporal_stabilization_hold_seconds=max(0.0, float(payload.get("temporal_stabilization_hold_seconds", 1.25))),
            continuous_capture_enabled=bool(payload.get("continuous_capture_enabled", False)),
            continuous_capture_target_fps=max(1.0, float(payload.get("continuous_capture_target_fps", 10.0))),
            continuous_capture_error_backoff_seconds=max(0.1, float(payload.get("continuous_capture_error_backoff_seconds", 0.5))),
            continuous_capture_stop_timeout_seconds=max(0.5, float(payload.get("continuous_capture_stop_timeout_seconds", 2.0))),
        )

    def people_detector_is_active(self) -> bool:
        return self.people_detection_enabled and self.people_detector_backend not in {"", "none", "null"}

    def face_detector_is_active(self) -> bool:
        return self.face_detection_enabled and self.face_detector_backend not in {"", "none", "null"}

    def object_detector_is_active(self) -> bool:
        return self.object_detection_enabled and self.object_detector_backend not in {"", "none", "null"}

    def capability_flags(self) -> dict[str, bool]:
        return {
            "people": self.people_detector_is_active(),
            "face": self.face_detector_is_active(),
            "object": self.object_detector_is_active(),
            "scene": self.scene_understanding_enabled,
            "gesture": self.gesture_recognition_enabled,
            "behavior": self.behavior_interpretation_enabled,
        }

    def selected_detector_backends(self) -> dict[str, str]:
        return {
            "people": self.people_detector_backend if self.people_detector_is_active() else "null",
            "face": self.face_detector_backend if self.face_detector_is_active() else "null",
            "objects": self.object_detector_backend if self.object_detector_is_active() else "null",
            "scene": "zone_rules",
        }