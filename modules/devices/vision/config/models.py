from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
    face_detection_enabled: bool
    object_detection_enabled: bool
    scene_understanding_enabled: bool
    gesture_recognition_enabled: bool
    behavior_interpretation_enabled: bool

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> "VisionRuntimeConfig":
        payload = dict(raw or {})
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
            face_detection_enabled=bool(payload.get("face_detection_enabled", False)),
            object_detection_enabled=bool(payload.get("object_detection_enabled", False)),
            scene_understanding_enabled=bool(payload.get("scene_understanding_enabled", False)),
            gesture_recognition_enabled=bool(payload.get("gesture_recognition_enabled", False)),
            behavior_interpretation_enabled=bool(payload.get("behavior_interpretation_enabled", False)),
        )

    def capability_flags(self) -> dict[str, bool]:
        return {
            "face": self.face_detection_enabled,
            "object": self.object_detection_enabled,
            "scene": self.scene_understanding_enabled,
            "gesture": self.gesture_recognition_enabled,
            "behavior": self.behavior_interpretation_enabled,
        }