from __future__ import annotations

import unittest

import numpy as np

from modules.devices.vision.diagnostics import render_diagnostics_overlay


class OverlayRendererTests(unittest.TestCase):
    def test_renders_boxes_zones_and_signal_panel_on_bgr_frame(self) -> None:
        frame = np.zeros((200, 300, 3), dtype=np.uint8)
        diagnostics = {
            "detections": {
                "people": [
                    {
                        "label": "person",
                        "confidence": 0.92,
                        "bounding_box": {
                            "left": 20,
                            "top": 20,
                            "right": 80,
                            "bottom": 150,
                        },
                    }
                ],
                "faces": [
                    {
                        "label": "face",
                        "confidence": 0.81,
                        "bounding_box": {
                            "left": 120,
                            "top": 30,
                            "right": 170,
                            "bottom": 90,
                        },
                    }
                ],
                "objects": [
                    {
                        "label": "phone",
                        "confidence": 0.77,
                        "bounding_box": {
                            "left": 210,
                            "top": 100,
                            "right": 260,
                            "bottom": 170,
                        },
                    }
                ],
            },
            "scene": {
                "metadata": {
                    "zone_layout": {
                        "desk_zone": {"x_min": 0.10, "y_min": 0.50, "x_max": 0.90, "y_max": 0.95},
                        "face_zone": {"x_min": 0.20, "y_min": 0.05, "x_max": 0.80, "y_max": 0.45},
                    }
                }
            },
            "signals": {
                "presence": {
                    "raw_active": True,
                    "stable_active": True,
                    "raw_confidence": 0.84,
                    "stable_confidence": 0.84,
                },
                "desk_activity": {
                    "raw_active": True,
                    "stable_active": True,
                    "raw_confidence": 0.73,
                    "stable_confidence": 0.73,
                },
            },
            "sessions": {
                "presence": {"current_active_seconds": 8.5},
                "desk_activity": {"current_active_seconds": 7.0},
            },
            "summary": {
                "user_present": True,
                "desk_active": True,
                "studying_likely": False,
                "people_count": 1,
                "face_count": 1,
                "object_count": 1,
            },
        }

        output = render_diagnostics_overlay(frame, diagnostics)

        self.assertEqual(output.shape, frame.shape)
        self.assertGreater(int(output.sum()), 0)
        self.assertTrue((output[20, 20] != 0).any())
        self.assertTrue((output[100, 30] != 0).any())
        self.assertTrue((output[10:40, 10:120] != 0).any())

    def test_converts_grayscale_input_to_bgr_output(self) -> None:
        frame = np.zeros((120, 160), dtype=np.uint8)
        diagnostics = {
            "detections": {},
            "scene": {},
            "signals": {},
            "sessions": {},
            "summary": {},
        }

        output = render_diagnostics_overlay(frame, diagnostics)

        self.assertEqual(output.shape, (120, 160, 3))
        self.assertEqual(output.dtype, frame.dtype)


if __name__ == "__main__":
    unittest.main()