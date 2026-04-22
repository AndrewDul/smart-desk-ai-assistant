# modules/devices/vision/perception/objects/postprocess.py
from __future__ import annotations

from modules.devices.vision.perception.models import BoundingBox, ObjectDetection
from modules.devices.vision.perception.objects.coco_labels import (
    coco_label_for_index,
    is_desk_relevant_label,
)
from modules.devices.vision.perception.objects.hailo_runtime.models import (
    RawNmsDetection,
)
from modules.devices.vision.preprocessing import (
    LetterboxTransform,
    map_normalized_box_to_frame,
)


def postprocess_yolo_detections(
    raw_detections: tuple[RawNmsDetection, ...],
    *,
    transform: LetterboxTransform,
    score_threshold: float,
    max_detections: int,
    desk_relevant_only: bool = False,
) -> tuple[ObjectDetection, ...]:
    """
    Convert Hailo NMS_BY_CLASS raw detections into NeXa ObjectDetection tuples.

    Steps for each raw detection:
    1. Drop if score < score_threshold.
    2. Look up COCO class name for class_index.
    3. Optionally drop if label is not desk-relevant (E/F/G etapy use this).
    4. Map normalized box (letterboxed 640x640 coords) back to original
       camera frame pixel coords.
    5. Drop if box collapses to zero area after mapping (fully inside
       letterbox padding, or outside the frame).
    6. Build ObjectDetection with metadata suitable for diagnostics.

    After filtering, results are sorted by confidence descending and capped
    at max_detections.
    """
    if not raw_detections:
        return ()

    if score_threshold < 0.0:
        score_threshold = 0.0
    if max_detections <= 0:
        return ()

    converted: list[ObjectDetection] = []

    for raw in raw_detections:
        if raw.score < score_threshold:
            continue

        label = coco_label_for_index(raw.class_index)

        if desk_relevant_only and not is_desk_relevant_label(label):
            continue

        mapped = map_normalized_box_to_frame(
            y_min_norm=raw.y_min,
            x_min_norm=raw.x_min,
            y_max_norm=raw.y_max,
            x_max_norm=raw.x_max,
            transform=transform,
        )
        if mapped is None:
            continue

        left, top, right, bottom = mapped

        try:
            box = BoundingBox(left=left, top=top, right=right, bottom=bottom)
        except ValueError:
            # Defensive — degenerate box that slipped through rounding.
            continue

        converted.append(
            ObjectDetection(
                label=label,
                bounding_box=box,
                confidence=float(raw.score),
                metadata={
                    "detector": "hailo_yolov11",
                    "class_index": int(raw.class_index),
                    "normalized_box": {
                        "y_min": float(raw.y_min),
                        "x_min": float(raw.x_min),
                        "y_max": float(raw.y_max),
                        "x_max": float(raw.x_max),
                    },
                },
            )
        )

    converted.sort(key=lambda det: det.confidence, reverse=True)
    return tuple(converted[:max_detections])