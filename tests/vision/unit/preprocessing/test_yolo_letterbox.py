# tests/vision/unit/preprocessing/test_yolo_letterbox.py
from __future__ import annotations

import unittest

import numpy as np

from modules.devices.vision.capture.frame_packet import FramePacket
from modules.devices.vision.preprocessing.yolo_letterbox import (
    LetterboxTransform,
    map_normalized_box_to_frame,
    preprocess_frame_for_yolo,
)


def _make_packet(width: int, height: int, fill: int = 200) -> FramePacket:
    pixels = np.full((height, width, 3), fill, dtype=np.uint8)
    return FramePacket(
        pixels=pixels,
        width=width,
        height=height,
        channels=3,
        backend_label="opencv",
    )


class PreprocessFrameForYoloTests(unittest.TestCase):

    def test_output_shape_is_target_size_square(self) -> None:
        packet = _make_packet(width=1280, height=720)
        tensor, _ = preprocess_frame_for_yolo(packet, target_size=640)
        self.assertEqual(tensor.shape, (640, 640, 3))
        self.assertEqual(tensor.dtype, np.uint8)

    def test_transform_reports_correct_scale_and_padding_for_16x9(self) -> None:
        packet = _make_packet(width=1280, height=720)
        _, transform = preprocess_frame_for_yolo(packet, target_size=640)

        # 1280/640 = 2.0, 720/640 = 1.125 -> scale is min = 0.5
        self.assertAlmostEqual(transform.scale, 640 / 1280, places=5)
        self.assertEqual(transform.scaled_width, 640)
        self.assertEqual(transform.scaled_height, 360)
        # Padding is vertical only (letterbox bars on top/bottom).
        self.assertEqual(transform.pad_left, 0)
        self.assertEqual(transform.pad_top, 140)

    def test_square_input_needs_no_padding(self) -> None:
        packet = _make_packet(width=640, height=640)
        _, transform = preprocess_frame_for_yolo(packet, target_size=640)

        self.assertEqual(transform.pad_left, 0)
        self.assertEqual(transform.pad_top, 0)
        self.assertAlmostEqual(transform.scale, 1.0, places=5)

    def test_portrait_input_produces_horizontal_padding(self) -> None:
        packet = _make_packet(width=480, height=640)
        _, transform = preprocess_frame_for_yolo(packet, target_size=640)

        self.assertEqual(transform.scaled_width, 480)
        self.assertEqual(transform.scaled_height, 640)
        self.assertEqual(transform.pad_top, 0)
        self.assertEqual(transform.pad_left, 80)

    def test_padding_uses_expected_pad_value(self) -> None:
        packet = _make_packet(width=1280, height=720)
        tensor, transform = preprocess_frame_for_yolo(
            packet,
            target_size=640,
            pad_value=114,
        )

        # A pixel inside the top padding band must be pad_value in all channels.
        top_pad_pixel = tensor[0, 100, :]
        self.assertEqual(list(top_pad_pixel), [114, 114, 114])

        # A pixel in the scaled content region must be the original fill (200),
        # after BGR->RGB reorder it is still 200 because we filled all channels.
        content_pixel = tensor[transform.pad_top + 5, 320, :]
        self.assertTrue(np.all(content_pixel == 200))

    def test_target_size_must_be_positive(self) -> None:
        packet = _make_packet(width=640, height=480)
        with self.assertRaises(ValueError):
            preprocess_frame_for_yolo(packet, target_size=0)


class MapNormalizedBoxToFrameTests(unittest.TestCase):

    def _transform_16x9(self) -> LetterboxTransform:
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

    def test_full_content_box_maps_back_to_full_original_frame(self) -> None:
        t = self._transform_16x9()
        # Box covering the entire content region of the letterboxed image.
        # Content region is y in [140/640, 500/640] after letterboxing.
        y_min_norm = 140 / 640
        y_max_norm = 500 / 640
        x_min_norm = 0.0
        x_max_norm = 1.0

        mapped = map_normalized_box_to_frame(
            y_min_norm=y_min_norm,
            x_min_norm=x_min_norm,
            y_max_norm=y_max_norm,
            x_max_norm=x_max_norm,
            transform=t,
        )

        self.assertIsNotNone(mapped)
        left, top, right, bottom = mapped
        self.assertEqual(left, 0)
        self.assertEqual(top, 0)
        self.assertEqual(right, 1280)
        self.assertEqual(bottom, 720)

    def test_box_inside_top_padding_returns_none(self) -> None:
        t = self._transform_16x9()
        # Box entirely within the top letterbox band (y < 140 in 640 space).
        mapped = map_normalized_box_to_frame(
            y_min_norm=0.05,
            x_min_norm=0.3,
            y_max_norm=0.15,
            x_max_norm=0.5,
            transform=t,
        )
        self.assertIsNone(mapped)

    def test_center_box_maps_to_center_of_frame(self) -> None:
        t = self._transform_16x9()
        # 0.4 .. 0.6 in normalized 640 space, both X and Y.
        mapped = map_normalized_box_to_frame(
            y_min_norm=0.4,
            x_min_norm=0.4,
            y_max_norm=0.6,
            x_max_norm=0.6,
            transform=t,
        )
        self.assertIsNotNone(mapped)
        left, top, right, bottom = mapped

        # Expected: x in 640-letterbox = [256, 384]. With scale=0.5 and
        # pad_left=0 -> original x = [512, 768]. Center at 640 in 1280.
        self.assertEqual(left, 512)
        self.assertEqual(right, 768)
        # y in 640-letterbox = [256, 384]. pad_top=140 -> scaled y = [116, 244].
        # Unscaled (x2) -> original y = [232, 488]. Center around 360.
        self.assertEqual(top, 232)
        self.assertEqual(bottom, 488)

    def test_zero_scale_returns_none(self) -> None:
        bad = LetterboxTransform(
            target_width=640,
            target_height=640,
            original_width=1280,
            original_height=720,
            scale=0.0,
            pad_left=0,
            pad_top=140,
            scaled_width=640,
            scaled_height=360,
        )
        mapped = map_normalized_box_to_frame(
            y_min_norm=0.2,
            x_min_norm=0.2,
            y_max_norm=0.8,
            x_max_norm=0.8,
            transform=bad,
        )
        self.assertIsNone(mapped)


if __name__ == "__main__":
    unittest.main()