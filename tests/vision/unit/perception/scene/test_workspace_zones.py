from __future__ import annotations

import unittest

from modules.devices.vision.perception.models import BoundingBox
from modules.devices.vision.perception.scene.workspace_zones import build_default_workspace_zone_layout


class WorkspaceZonesTests(unittest.TestCase):
    def test_default_desk_zone_contains_box_center_in_lower_middle_frame(self) -> None:
        layout = build_default_workspace_zone_layout()
        box = BoundingBox(left=500, top=420, right=780, bottom=700)

        result = layout.desk_zone.contains_box_center(box, frame_width=1280, frame_height=720)

        self.assertTrue(result)

    def test_default_screen_zone_rejects_box_center_in_bottom_corner(self) -> None:
        layout = build_default_workspace_zone_layout()
        box = BoundingBox(left=10, top=620, right=90, bottom=710)

        result = layout.screen_zone.contains_box_center(box, frame_width=1280, frame_height=720)

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()