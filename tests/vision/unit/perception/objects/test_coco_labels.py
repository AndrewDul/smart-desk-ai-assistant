# tests/vision/unit/perception/objects/test_coco_labels.py
from __future__ import annotations

import unittest

from modules.devices.vision.perception.objects.coco_labels import (
    COCO_CLASS_NAMES,
    COMPUTER_WORK_LABELS,
    DESK_SCENE_LABELS,
    PHONE_LABELS,
    STUDY_LABELS,
    coco_label_for_index,
    is_desk_relevant_label,
)


class CocoLabelsTests(unittest.TestCase):

    def test_coco_has_80_classes(self) -> None:
        self.assertEqual(len(COCO_CLASS_NAMES), 80)

    def test_canonical_indices_for_key_classes(self) -> None:
        # These specific indices are contractual — downstream behavior
        # interpreters depend on them matching the HEF output.
        self.assertEqual(COCO_CLASS_NAMES[0], "person")
        self.assertEqual(COCO_CLASS_NAMES[62], "tv")
        self.assertEqual(COCO_CLASS_NAMES[63], "laptop")
        self.assertEqual(COCO_CLASS_NAMES[66], "keyboard")
        self.assertEqual(COCO_CLASS_NAMES[67], "cell phone")
        self.assertEqual(COCO_CLASS_NAMES[73], "book")

    def test_coco_label_for_index_returns_name_in_range(self) -> None:
        self.assertEqual(coco_label_for_index(67), "cell phone")

    def test_coco_label_for_index_handles_out_of_range(self) -> None:
        self.assertEqual(coco_label_for_index(999), "class_999")
        self.assertEqual(coco_label_for_index(-1), "class_-1")

    def test_desk_relevant_labels_are_recognized(self) -> None:
        self.assertTrue(is_desk_relevant_label("laptop"))
        self.assertTrue(is_desk_relevant_label("cell phone"))
        self.assertTrue(is_desk_relevant_label("book"))
        self.assertTrue(is_desk_relevant_label("cup"))

    def test_non_desk_labels_are_rejected(self) -> None:
        self.assertFalse(is_desk_relevant_label("giraffe"))
        self.assertFalse(is_desk_relevant_label("airplane"))
        self.assertFalse(is_desk_relevant_label("person"))
        self.assertFalse(is_desk_relevant_label(""))

    def test_label_subsets_are_disjoint_and_non_empty(self) -> None:
        self.assertGreater(len(COMPUTER_WORK_LABELS), 0)
        self.assertGreater(len(PHONE_LABELS), 0)
        self.assertGreater(len(STUDY_LABELS), 0)
        self.assertGreater(len(DESK_SCENE_LABELS), 0)

        self.assertTrue(COMPUTER_WORK_LABELS.isdisjoint(PHONE_LABELS))
        self.assertTrue(COMPUTER_WORK_LABELS.isdisjoint(STUDY_LABELS))
        self.assertTrue(PHONE_LABELS.isdisjoint(STUDY_LABELS))


if __name__ == "__main__":
    unittest.main()