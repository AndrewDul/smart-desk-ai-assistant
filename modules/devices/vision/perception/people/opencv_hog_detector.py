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
class _DetectionPass:
    name: str
    image: Any
    x_offset: int
    y_offset: int
    scale_x: float
    scale_y: float


@dataclass(frozen=True, slots=True)
class _DetectionCandidate:
    bounding_box: BoundingBox
    confidence: float
    raw_weight: float
    area_ratio: float
    height_ratio: float
    width_ratio: float
    pass_name: str


@dataclass(slots=True)
class OpenCvHogPeopleDetector:
    backend_label: str = "opencv_hog"
    min_confidence: float = 0.45
    min_area_ratio: float = 0.025
    min_height_ratio: float = 0.18
    max_width_ratio: float = 0.85
    nms_iou_threshold: float = 0.35
    win_stride: tuple[int, int] = (8, 8)
    padding: tuple[int, int] = (8, 8)
    scale: float = 1.05
    max_detections: int = 5
    use_clahe: bool = True
    upscale_factor: float = 1.35
    desk_roi_enabled: bool = True
    desk_roi_bounds: tuple[float, float, float, float] = (0.10, 0.08, 0.90, 0.98)
    hog: Any | None = field(default=None, repr=False)

    def detect_people(self, packet: FramePacket) -> tuple[PersonDetection, ...]:
        detection_passes = self._build_detection_passes(packet)
        hog = self._get_hog()
        frame_area = max(1, int(packet.width) * int(packet.height))

        candidates: list[_DetectionCandidate] = []

        for detection_pass in detection_passes:
            boxes, raw_weights = hog.detectMultiScale(
                detection_pass.image,
                winStride=self.win_stride,
                padding=self.padding,
                scale=self.scale,
            )

            weights = _coerce_weights(raw_weights)
            for box, raw_weight in zip_longest(boxes, weights, fillvalue=0.0):
                if box is None:
                    continue

                mapped_box = self._map_box_to_frame(packet, detection_pass, box)
                if mapped_box is None:
                    continue

                area_ratio = (mapped_box.width * mapped_box.height) / frame_area
                if area_ratio < self.min_area_ratio:
                    continue

                height_ratio = mapped_box.height / max(1, packet.height)
                if height_ratio < self.min_height_ratio:
                    continue

                width_ratio = mapped_box.width / max(1, packet.width)
                if width_ratio > self.max_width_ratio:
                    continue

                confidence = _normalize_detector_score(float(raw_weight))
                if confidence < self.min_confidence:
                    continue

                candidates.append(
                    _DetectionCandidate(
                        bounding_box=mapped_box,
                        confidence=confidence,
                        raw_weight=float(raw_weight),
                        area_ratio=area_ratio,
                        height_ratio=height_ratio,
                        width_ratio=width_ratio,
                        pass_name=detection_pass.name,
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
                    "pass_name": item.pass_name,
                    "raw_weight": round(item.raw_weight, 4),
                    "area_ratio": round(item.area_ratio, 5),
                    "height_ratio": round(item.height_ratio, 5),
                    "width_ratio": round(item.width_ratio, 5),
                },
            )
            for item in selected
        )

    def _build_detection_passes(self, packet: FramePacket) -> tuple[_DetectionPass, ...]:
        import cv2

        base_frame = frame_to_bgr(packet)
        prepared_full = self._prepare_for_detection(base_frame)

        passes: list[_DetectionPass] = [
            _DetectionPass(
                name="full_frame",
                image=prepared_full,
                x_offset=0,
                y_offset=0,
                scale_x=1.0,
                scale_y=1.0,
            )
        ]

        if self.desk_roi_enabled:
            roi_x_min, roi_y_min, roi_x_max, roi_y_max = self.desk_roi_bounds
            x1 = max(0, min(packet.width - 1, int(round(packet.width * roi_x_min))))
            y1 = max(0, min(packet.height - 1, int(round(packet.height * roi_y_min))))
            x2 = max(x1 + 1, min(packet.width, int(round(packet.width * roi_x_max))))
            y2 = max(y1 + 1, min(packet.height, int(round(packet.height * roi_y_max))))

            roi = base_frame[y1:y2, x1:x2]
            if roi.size > 0:
                prepared_roi = self._prepare_for_detection(roi)
                passes.append(
                    _DetectionPass(
                        name="desk_roi",
                        image=prepared_roi,
                        x_offset=x1,
                        y_offset=y1,
                        scale_x=1.0,
                        scale_y=1.0,
                    )
                )

                if self.upscale_factor > 1.0:
                    upscaled = cv2.resize(
                        prepared_roi,
                        None,
                        fx=self.upscale_factor,
                        fy=self.upscale_factor,
                        interpolation=cv2.INTER_LINEAR,
                    )
                    passes.append(
                        _DetectionPass(
                            name="desk_roi_upscaled",
                            image=upscaled,
                            x_offset=x1,
                            y_offset=y1,
                            scale_x=self.upscale_factor,
                            scale_y=self.upscale_factor,
                        )
                    )

        return tuple(passes)

    def _prepare_for_detection(self, bgr_frame):
        if not self.use_clahe:
            return bgr_frame

        import cv2

        lab = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_channel = clahe.apply(l_channel)
        merged = cv2.merge((l_channel, a_channel, b_channel))
        return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)

    def _map_box_to_frame(
        self,
        packet: FramePacket,
        detection_pass: _DetectionPass,
        box: Any,
    ) -> BoundingBox | None:
        x, y, width, height = [int(value) for value in box]
        if width <= 0 or height <= 0:
            return None

        left = detection_pass.x_offset + int(round(x / detection_pass.scale_x))
        top = detection_pass.y_offset + int(round(y / detection_pass.scale_y))
        right = detection_pass.x_offset + int(round((x + width) / detection_pass.scale_x))
        bottom = detection_pass.y_offset + int(round((y + height) / detection_pass.scale_y))

        left = max(0, min(packet.width - 1, left))
        top = max(0, min(packet.height - 1, top))
        right = max(left + 1, min(packet.width, right))
        bottom = max(top + 1, min(packet.height, bottom))

        if right <= left or bottom <= top:
            return None

        return BoundingBox(left=left, top=top, right=right, bottom=bottom)

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