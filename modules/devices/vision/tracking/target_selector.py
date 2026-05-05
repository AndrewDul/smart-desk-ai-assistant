from __future__ import annotations

from typing import Any

from modules.runtime.contracts import VisionObservation

from .models import TrackingTarget


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _box_from_detection(detection: dict[str, Any]) -> dict[str, int] | None:
    box = detection.get("bounding_box")
    if not isinstance(box, dict):
        return None

    try:
        left = int(box["left"])
        top = int(box["top"])
        right = int(box["right"])
        bottom = int(box["bottom"])
    except (KeyError, TypeError, ValueError):
        return None

    if right <= left or bottom <= top:
        return None

    return {"left": left, "top": top, "right": right, "bottom": bottom}


def _target_from_detection(
    *,
    detection: dict[str, Any],
    target_type: str,
    source_index: int,
    frame_width: int,
    frame_height: int,
) -> TrackingTarget | None:
    box = _box_from_detection(detection)
    if box is None:
        return None

    width = box["right"] - box["left"]
    height = box["bottom"] - box["top"]
    area_norm = (width * height) / float(frame_width * frame_height)

    return TrackingTarget(
        target_type=target_type,
        confidence=_as_float(detection.get("confidence"), 0.0),
        box=box,
        center_x_norm=(box["left"] + (width / 2.0)) / float(frame_width),
        center_y_norm=(box["top"] + (height / 2.0)) / float(frame_height),
        area_norm=area_norm,
        source_index=source_index,
        metadata=dict(detection.get("metadata", {}) or {}),
    )


def _score_target(target: TrackingTarget) -> float:
    center_offset = abs(target.center_x_norm - 0.5) + abs(target.center_y_norm - 0.5)
    center_score = max(0.0, 1.0 - center_offset)
    type_bonus = 0.25 if target.target_type == "face" else 0.0
    return (target.confidence * 0.65) + (target.area_norm * 0.20) + (center_score * 0.15) + type_bonus


class TrackingTargetSelector:
    """Select the best low-latency tracking target from VisionObservation metadata."""

    def select(self, observation: VisionObservation | None) -> TrackingTarget | None:
        if observation is None:
            return None

        metadata = dict(observation.metadata or {})
        perception = metadata.get("perception")
        if not isinstance(perception, dict):
            return None

        frame_width = int(metadata.get("frame_width") or perception.get("frame_width") or 0)
        frame_height = int(metadata.get("frame_height") or perception.get("frame_height") or 0)
        if frame_width <= 0 or frame_height <= 0:
            return None

        candidates: list[TrackingTarget] = []
        for target_type, key in (("face", "faces"), ("person", "people")):
            detections = perception.get(key, [])
            if not isinstance(detections, list):
                continue
            for index, detection in enumerate(detections):
                if not isinstance(detection, dict):
                    continue
                target = _target_from_detection(
                    detection=detection,
                    target_type=target_type,
                    source_index=index,
                    frame_width=frame_width,
                    frame_height=frame_height,
                )
                if target is not None:
                    candidates.append(target)

        if not candidates:
            return None

        return max(candidates, key=_score_target)
