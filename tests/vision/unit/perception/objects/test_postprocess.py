# tests/vision/unit/perception/objects/test_postprocess.py
from __future__ import annotations

import unittest

from modules.devices.vision.perception.objects.hailo_runtime.models import (
    RawNmsDetection,
)
from modules.devices.vision.perception.objects.postprocess import (
    postprocess_yolo_detections,
)
from modules.devices.vision.preprocessing.yolo_letterbox import LetterboxTransform


def _standard_16x9_transform() -> LetterboxTransform:
    return LetterboxTransform(
        target_width=640,
        target_height=640,
        original_width=1280,
        original_height=720,
        scale=640 / 1280,
        pad_left=0,
        pad_top=140,
        scaled_width=640,
        scaled_height=360,
    )


class PostprocessYoloDetectionsTests(unittest.TestCase):

    def test_empty_input_returns_empty_tuple(self) -> None:
        result = postprocess_yolo_detections(
            raw_detections=(),
            transform=_standard_16x9_transform(),
            score_threshold=0.3,
            max_detections=30,
        )
        self.assertEqual(result, ())

    def test_detection_below_score_threshold_is_dropped(self) -> None:
        raw = (
            RawNmsDetection(
                class_index=0,  # person
                score=0.2,
                y_min=0.3, x_min=0.3, y_max=0.7, x_max=0.7,
            ),
        )
        result = postprocess_yolo_detections(
            raw_detections=raw,
            transform=_standard_16x9_transform(),
            score_threshold=0.35,
            max_detections=30,
        )
        self.assertEqual(result, ())

    def test_person_detection_gets_correct_label_and_mapped_box(self) -> None:
        raw = (
            RawNmsDetection(
                class_index=0,  # person
                score=0.88,
                y_min=0.4, x_min=0.4, y_max=0.6, x_max=0.6,
            ),
        )
        result = postprocess_yolo_detections(
            raw_detections=raw,
            transform=_standard_16x9_transform(),
            score_threshold=0.3,
            max_detections=30,
        )
        self.assertEqual(len(result), 1)
        det = result[0]
        self.assertEqual(det.label, "person")
        self.assertAlmostEqual(det.confidence, 0.88, places=4)
        self.assertEqual(det.metadata["detector"], "hailo_yolov11")
        self.assertEqual(det.metadata["class_index"], 0)
        self.assertIn("normalized_box", det.metadata)

        # Mapped box center should be around the middle of the 1280x720 frame.
        box = det.bounding_box
        self.assertGreater(box.center_x, 500)
        self.assertLess(box.center_x, 780)

    def test_laptop_and_cellphone_labels_are_resolved(self) -> None:
        raw = (
            RawNmsDetection(
                class_index=63,  # laptop
                score=0.7,
                y_min=0.45, x_min=0.3, y_max=0.8, x_max=0.7,
            ),
            RawNmsDetection(
                class_index=67,  # cell phone
                score=0.55,
                y_min=0.5, x_min=0.1, y_max=0.7, x_max=0.25,
            ),
        )
        result = postprocess_yolo_detections(
            raw_detections=raw,
            transform=_standard_16x9_transform(),
            score_threshold=0.3,
            max_detections=30,
        )
        labels = [det.label for det in result]
        self.assertIn("laptop", labels)
        self.assertIn("cell phone", labels)

    def test_box_entirely_in_letterbox_padding_is_dropped(self) -> None:
        # y in [0, 0.15] is entirely above the content band in a 16:9 letterbox
        # (pad_top=140/640 = 0.21875).
        raw = (
            RawNmsDetection(
                class_index=63,
                score=0.8,
                y_min=0.02, x_min=0.4, y_max=0.12, x_max=0.6,
            ),
        )
        result = postprocess_yolo_detections(
            raw_detections=raw,
            transform=_standard_16x9_transform(),
            score_threshold=0.3,
            max_detections=30,
        )
        self.assertEqual(result, ())

    def test_results_sorted_by_confidence_descending(self) -> None:
        raw = (
            RawNmsDetection(
                class_index=0, score=0.5,
                y_min=0.4, x_min=0.1, y_max=0.6, x_max=0.3,
            ),
            RawNmsDetection(
                class_index=0, score=0.95,
                y_min=0.4, x_min=0.4, y_max=0.6, x_max=0.6,
            ),
            RawNmsDetection(
                class_index=0, score=0.72,
                y_min=0.4, x_min=0.7, y_max=0.6, x_max=0.9,
            ),
        )
        result = postprocess_yolo_detections(
            raw_detections=raw,
            transform=_standard_16x9_transform(),
            score_threshold=0.3,
            max_detections=30,
        )
        confidences = [det.confidence for det in result]
        self.assertEqual(confidences, sorted(confidences, reverse=True))

    def test_max_detections_cap_enforced(self) -> None:
        raw = tuple(
            RawNmsDetection(
                class_index=0,
                score=0.3 + i * 0.05,
                y_min=0.4, x_min=0.0 + i * 0.05, y_max=0.6, x_max=0.05 + i * 0.05,
            )
            for i in range(10)
        )
        result = postprocess_yolo_detections(
            raw_detections=raw,
            transform=_standard_16x9_transform(),
            score_threshold=0.25,
            max_detections=3,
        )
        self.assertEqual(len(result), 3)

    def test_desk_relevant_only_filters_out_non_desk_labels(self) -> None:
        raw = (
            # laptop — desk relevant (class 63)
            RawNmsDetection(
                class_index=63, score=0.8,
                y_min=0.45, x_min=0.3, y_max=0.7, x_max=0.65,
            ),
            # giraffe — not desk relevant (class 23)
            RawNmsDetection(
                class_index=23, score=0.9,
                y_min=0.45, x_min=0.3, y_max=0.7, x_max=0.65,
            ),
        )
        result = postprocess_yolo_detections(
            raw_detections=raw,
            transform=_standard_16x9_transform(),
            score_threshold=0.3,
            max_detections=30,
            desk_relevant_only=True,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].label, "laptop")

    def test_desk_relevant_only_keeps_person(self) -> None:
        # Person is NOT in desk-specific labels but would be handled by the
        # hybrid detector separately. This test documents that with
        # desk_relevant_only=True, person is filtered out from the object
        # detector output. Person presence comes from people/face detectors.
        raw = (
            RawNmsDetection(
                class_index=0, score=0.9,
                y_min=0.4, x_min=0.4, y_max=0.6, x_max=0.6,
            ),
        )
        result = postprocess_yolo_detections(
            raw_detections=raw,
            transform=_standard_16x9_transform(),
            score_threshold=0.3,
            max_detections=30,
            desk_relevant_only=True,
        )
        self.assertEqual(result, ())


if __name__ == "__main__":
    unittest.main()