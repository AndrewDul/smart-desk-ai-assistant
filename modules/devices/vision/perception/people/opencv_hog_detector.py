from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import Any

from modules.devices.vision.capture import FramePacket
from modules.devices.vision.perception.models import BoundingBox, PersonDetection
from modules.devices.vision.preprocessing import frame_to_bgr


def _normalize_detector_score(raw_weight: float) -> float:
    weight = max(0.0, float(raw_weight))
    return max(0.0, min(1.0, 1.0 - math.exp(-weight / 2.0)))


def _coerce_weights(raw_weights: Any) -> tuple[float, ...]:
    if raw_weights is None:
        return ()

    weights: list[float] = []
    for item in raw_weights:
        if isinstance(item, (list, tuple)):
            if not item:
                continue
            weights.append(float(item[0]))
            continue
        weights.append(float(item))
    return tuple(weights)


def _intersection_over_union(first: BoundingBox, second: BoundingBox) -> float:
    left = max(first.left, second.left)
    top = max(first.top, second.top)
    right = min(first.right, second.right)
    bottom = min(first.bottom, second.bottom)

    if right <= left or bottom <= top:
        return 0.0

    intersection_area = (right - left) * (bottom - top)
    first_area = first.width * first.height
    second_area = second.width * second.height
    union_area = first_area + second_area - intersection_area

    if union_area <= 0:
        return 0.0

    return intersection_area / union_area


@dataclass(frozen=True, slots=True)
class _DetectionCandidate:
    bounding_box: BoundingBox
    confidence: float
    raw_weight: float
    area_ratio: float


@dataclass(slots=True)
class OpenCvHogPeopleDetector:
    backend_label: str = "opencv_hog"
    min_confidence: float = 0.45
    min_area_ratio: float = 0.025
    nms_iou_threshold: float = 0.35
    win_stride: tuple[int, int] = (8, 8)
    padding: tuple[int, int] = (8, 8)
    scale: float = 1.05
    max_detections: int = 5
    hog: Any | None = field(default=None, repr=False)

    def detect_people(self, packet: FramePacket) -> tuple[PersonDetection, ...]:
        prepared_frame = self._prepare_bgr_frame(packet)
        hog = self._get_hog()

        boxes, raw_weights = hog.detectMultiScale(
            prepared_frame,
            winStride=self.win_stride,
            padding=self.padding,
            scale=self.scale,
        )

        weights = _coerce_weights(raw_weights)
        frame_area = max(1, int(packet.width) * int(packet.height))

        candidates: list[_DetectionCandidate] = []
        for box, raw_weight in zip_longest(boxes, weights, fillvalue=0.0):
            if box is None:
                continue

            x, y, width, height = [int(value) for value in box]
            if width <= 0 or height <= 0:
                continue

            area_ratio = (width * height) / frame_area
            if area_ratio < self.min_area_ratio:
                continue

            confidence = _normalize_detector_score(float(raw_weight))
            if confidence < self.min_confidence:
                continue

            candidates.append(
                _DetectionCandidate(
                    bounding_box=BoundingBox(
                        left=x,
                        top=y,
                        right=x + width,
                        bottom=y + height,
                    ),
                    confidence=confidence,
                    raw_weight=float(raw_weight),
                    area_ratio=area_ratio,
                )
            )

        selected = self._apply_non_max_suppression(candidates)

        return tuple(
            PersonDetection(
                bounding_box=item.bounding_box,
                confidence=item.confidence,
                label="person",
                metadata={
                    "detector": self.backend_label,
                    "raw_weight": round(item.raw_weight, 4),
                    "area_ratio": round(item.area_ratio, 5),
                },
            )
            for item in selected
        )

    def _prepare_bgr_frame(self, packet: FramePacket):
        return frame_to_bgr(packet)

    def _get_hog(self):
        if self.hog is None:
            import cv2

            hog = cv2.HOGDescriptor()
            hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
            self.hog = hog
        return self.hog

    def _apply_non_max_suppression(
        self,
        candidates: list[_DetectionCandidate],
    ) -> tuple[_DetectionCandidate, ...]:
        selected: list[_DetectionCandidate] = []

        for candidate in sorted(candidates, key=lambda item: item.confidence, reverse=True):
            if any(
                _intersection_over_union(candidate.bounding_box, kept.bounding_box) >= self.nms_iou_threshold
                for kept in selected
            ):
                continue

            selected.append(candidate)
            if len(selected) >= self.max_detections:
                break

        return tuple(selected)