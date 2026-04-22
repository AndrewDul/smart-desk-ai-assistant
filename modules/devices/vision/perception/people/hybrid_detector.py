# modules/devices/vision/perception/people/hybrid_detector.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from modules.devices.vision.capture import FramePacket
from modules.devices.vision.perception.face import FaceDetector
from modules.devices.vision.perception.models import BoundingBox, PersonDetection


def _intersection_over_union(first: BoundingBox, second: BoundingBox) -> float:
    """Axis-aligned IoU used to merge HOG and face-projected person boxes."""
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


@dataclass(slots=True)
class HybridFacePrimaryPeopleDetector:
    """
    Face-primary people detector for desk-facing cameras.

    Strategy:
    - Run the face detector first. Each detected face is projected into a
      full-body person bounding box using seated-at-desk proportions.
    - Optionally run the HOG secondary path and merge results via IoU dedupe.
      HOG hits that overlap a face-projected box are folded into the same
      PersonDetection with elevated confidence. HOG-only hits are kept.
    - Returns PersonDetection tuples that look identical to any other people
      detector output, so the PerceptionPipeline and PresenceInterpreter work
      unchanged.

    Rationale:
    - On desk cameras, HOG alone typically returns people_count = 0 because
      only the head and shoulders are visible. This detector makes presence
      detection robust by treating a detected face as proof of a person.
    """

    backend_label: str = "hybrid_face_primary"
    face_detector: FaceDetector | None = None
    secondary_detector: Any | None = None

    # Projection tuning — how a face box maps to a full-body person box.
    # Values are fractions of face box dimensions.
    body_width_multiplier: float = 2.6
    body_height_multiplier: float = 5.5
    face_vertical_offset_ratio: float = 0.1

    # Confidence policy.
    face_only_confidence_floor: float = 0.65
    merged_confidence_boost: float = 0.15
    merge_iou_threshold: float = 0.35
    max_detections: int = 5

    # ------------------------------------------------------------------
    # Public API — PeopleDetector protocol
    # ------------------------------------------------------------------

    def detect_people(self, packet: FramePacket) -> tuple[PersonDetection, ...]:
        face_projected = self._project_faces_to_people(packet)
        secondary_people = self._run_secondary_detector(packet)

        merged = self._merge_detections(face_projected, secondary_people)
        if not merged:
            return ()

        merged.sort(key=lambda item: item.confidence, reverse=True)
        return tuple(merged[: self.max_detections])

    # ------------------------------------------------------------------
    # Face projection
    # ------------------------------------------------------------------

    def _project_faces_to_people(self, packet: FramePacket) -> list[PersonDetection]:
        if self.face_detector is None:
            return []

        faces = tuple(self.face_detector.detect_faces(packet))
        if not faces:
            return []

        projected: list[PersonDetection] = []
        for face in faces:
            person_box = self._expand_face_to_body_box(
                face.bounding_box,
                packet.width,
                packet.height,
            )
            if person_box is None:
                continue

            confidence = max(face.confidence, self.face_only_confidence_floor)
            projected.append(
                PersonDetection(
                    bounding_box=person_box,
                    confidence=confidence,
                    label="person",
                    metadata={
                        "detector": self.backend_label,
                        "source": "face_projected",
                        "face_confidence": round(float(face.confidence), 4),
                        "face_box": {
                            "left": face.bounding_box.left,
                            "top": face.bounding_box.top,
                            "right": face.bounding_box.right,
                            "bottom": face.bounding_box.bottom,
                        },
                    },
                )
            )

        return projected

    def _expand_face_to_body_box(
        self,
        face_box: BoundingBox,
        frame_width: int,
        frame_height: int,
    ) -> BoundingBox | None:
        """
        Expand a face box into a plausible seated-at-desk body box.

        Horizontal: centered on the face, width = face.width * body_width_multiplier.
        Vertical: body starts slightly above the face (hair/head),
                  extends down by face.height * body_height_multiplier.
        """
        face_width = face_box.width
        face_height = face_box.height
        if face_width <= 0 or face_height <= 0:
            return None

        target_width = face_width * self.body_width_multiplier
        target_height = face_height * self.body_height_multiplier

        face_center_x = face_box.center_x
        vertical_offset = face_height * self.face_vertical_offset_ratio

        raw_left = face_center_x - (target_width / 2.0)
        raw_right = face_center_x + (target_width / 2.0)
        raw_top = face_box.top - vertical_offset
        raw_bottom = raw_top + target_height

        left = max(0, int(round(raw_left)))
        top = max(0, int(round(raw_top)))
        right = min(frame_width, int(round(raw_right)))
        bottom = min(frame_height, int(round(raw_bottom)))

        if right <= left or bottom <= top:
            return None

        return BoundingBox(left=left, top=top, right=right, bottom=bottom)

    # ------------------------------------------------------------------
    # Secondary detector integration
    # ------------------------------------------------------------------

    def _run_secondary_detector(self, packet: FramePacket) -> list[PersonDetection]:
        if self.secondary_detector is None:
            return []

        detect_method = getattr(self.secondary_detector, "detect_people", None)
        if not callable(detect_method):
            return []

        try:
            secondary_results = tuple(detect_method(packet))
        except Exception:
            # Secondary detector failures must never break the primary face path.
            return []

        results: list[PersonDetection] = []
        for detection in secondary_results:
            metadata = dict(detection.metadata)
            metadata.setdefault("source", "hog")
            results.append(
                PersonDetection(
                    bounding_box=detection.bounding_box,
                    confidence=detection.confidence,
                    label=detection.label,
                    metadata=metadata,
                )
            )
        return results

    # ------------------------------------------------------------------
    # Merging face-projected and secondary detections
    # ------------------------------------------------------------------

    def _merge_detections(
        self,
        face_projected: list[PersonDetection],
        secondary: list[PersonDetection],
    ) -> list[PersonDetection]:
        if not secondary:
            return list(face_projected)

        if not face_projected:
            return list(secondary)

        merged: list[PersonDetection] = []
        secondary_consumed: set[int] = set()

        for face_person in face_projected:
            best_index: int | None = None
            best_iou: float = 0.0

            for index, secondary_person in enumerate(secondary):
                if index in secondary_consumed:
                    continue
                iou = _intersection_over_union(
                    face_person.bounding_box,
                    secondary_person.bounding_box,
                )
                if iou > best_iou:
                    best_iou = iou
                    best_index = index

            if best_index is not None and best_iou >= self.merge_iou_threshold:
                secondary_person = secondary[best_index]
                secondary_consumed.add(best_index)
                merged.append(self._combine_face_and_secondary(face_person, secondary_person, best_iou))
            else:
                merged.append(face_person)

        for index, secondary_person in enumerate(secondary):
            if index in secondary_consumed:
                continue
            merged.append(secondary_person)

        return merged

    def _combine_face_and_secondary(
        self,
        face_person: PersonDetection,
        secondary_person: PersonDetection,
        iou: float,
    ) -> PersonDetection:
        """
        Combine a face-projected box with an overlapping secondary box.
        The secondary box wins geometry (better body shape), the merged
        confidence gets a boost because two independent signals agree.
        """
        combined_confidence = min(
            1.0,
            max(face_person.confidence, secondary_person.confidence) + self.merged_confidence_boost,
        )

        combined_metadata = dict(secondary_person.metadata)
        combined_metadata.update(
            {
                "detector": self.backend_label,
                "source": "hog+face",
                "merge_iou": round(float(iou), 4),
                "face_projected_box": {
                    "left": face_person.bounding_box.left,
                    "top": face_person.bounding_box.top,
                    "right": face_person.bounding_box.right,
                    "bottom": face_person.bounding_box.bottom,
                },
                "face_confidence": face_person.metadata.get("face_confidence"),
            }
        )

        return PersonDetection(
            bounding_box=secondary_person.bounding_box,
            confidence=combined_confidence,
            label="person",
            metadata=combined_metadata,
        )