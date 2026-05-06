"""Pure-logic tests for the look-at-me planners.

These deliberately do NOT touch the camera or the pan/tilt hardware. The
session worker is integration-tested in tests/vision/integration/ once you
have hardware available.
"""
from __future__ import annotations

import unittest

from modules.devices.vision.look_at_me.scan_planner import ScanPlanner
from modules.devices.vision.look_at_me.tracking_planner import TrackingPlanner


class TrackingPlannerTests(unittest.TestCase):
    def test_centered_face_produces_hold_zone_command(self) -> None:
        planner = TrackingPlanner(hold_zone_x=0.02, hold_zone_y=0.02)
        command = planner.plan(face_x_norm=0.5, face_y_norm=0.5)
        self.assertTrue(command.in_hold_zone)
        self.assertEqual(command.pan_delta_degrees, 0.0)
        self.assertEqual(command.tilt_delta_degrees, 0.0)
        self.assertEqual(command.reason, "face_centered")

    def test_face_on_left_pans_left(self) -> None:
        planner = TrackingPlanner(pan_gain_degrees=20.0, max_step_degrees=10.0)
        command = planner.plan(face_x_norm=0.30, face_y_norm=0.5)
        self.assertFalse(command.in_hold_zone)
        # offset_x = 0.30 - 0.5 = -0.2, so pan_delta should be NEGATIVE
        self.assertLess(command.pan_delta_degrees, 0.0)

    def test_face_on_right_pans_right(self) -> None:
        planner = TrackingPlanner(pan_gain_degrees=20.0, max_step_degrees=10.0)
        command = planner.plan(face_x_norm=0.70, face_y_norm=0.5)
        self.assertGreater(command.pan_delta_degrees, 0.0)

    def test_face_above_center_tilts_up(self) -> None:
        planner = TrackingPlanner(tilt_gain_degrees=20.0, max_step_degrees=10.0)
        command = planner.plan(face_x_norm=0.5, face_y_norm=0.30)
        # face above center -> tilt UP -> positive tilt_delta in normal config
        self.assertGreater(command.tilt_delta_degrees, 0.0)

    def test_max_step_is_respected(self) -> None:
        planner = TrackingPlanner(
            pan_gain_degrees=999.0,
            tilt_gain_degrees=999.0,
            max_step_degrees=1.5,
        )
        command = planner.plan(face_x_norm=0.0, face_y_norm=1.0)
        self.assertLessEqual(abs(command.pan_delta_degrees), 1.5 + 1e-6)
        self.assertLessEqual(abs(command.tilt_delta_degrees), 1.5 + 1e-6)

    def test_invert_tilt_flips_sign(self) -> None:
        normal = TrackingPlanner(invert_tilt=False, tilt_gain_degrees=20.0, max_step_degrees=10.0)
        inverted = TrackingPlanner(invert_tilt=True, tilt_gain_degrees=20.0, max_step_degrees=10.0)
        normal_cmd = normal.plan(face_x_norm=0.5, face_y_norm=0.30)
        inverted_cmd = inverted.plan(face_x_norm=0.5, face_y_norm=0.30)
        self.assertAlmostEqual(
            normal_cmd.tilt_delta_degrees,
            -inverted_cmd.tilt_delta_degrees,
            places=4,
        )


class ScanPlannerTests(unittest.TestCase):
    def test_first_target_is_left_edge_lowest_tilt(self) -> None:
        scanner = ScanPlanner(
            pan_limit_degrees=40.0,
            pan_step_degrees=10.0,
            tilt_levels_degrees=(0.0, 6.0, 10.0),
        )
        first = scanner.next_target()
        self.assertAlmostEqual(first.target_pan_degrees, -40.0)
        self.assertAlmostEqual(first.target_tilt_degrees, 0.0)
        self.assertEqual(first.direction, "right")  # sweeping right initially

    def test_sweep_then_reverse_then_advance_tilt(self) -> None:
        scanner = ScanPlanner(
            pan_limit_degrees=10.0,
            pan_step_degrees=5.0,
            tilt_levels_degrees=(0.0, 5.0),
        )
        seen_pans: list[float] = []
        seen_tilts: list[float] = []
        for _ in range(12):
            t = scanner.next_target()
            seen_pans.append(t.target_pan_degrees)
            seen_tilts.append(t.target_tilt_degrees)
        # Should cover both directions and at least both tilt levels.
        self.assertIn(-10.0, seen_pans)
        self.assertIn(10.0, seen_pans)
        self.assertIn(0.0, seen_tilts)
        self.assertIn(5.0, seen_tilts)

    def test_reset_returns_to_left_edge_lowest_tilt(self) -> None:
        scanner = ScanPlanner(
            pan_limit_degrees=10.0,
            pan_step_degrees=2.0,
            tilt_levels_degrees=(0.0, 5.0, 10.0),
        )
        for _ in range(20):
            scanner.next_target()
        scanner.reset()
        first = scanner.next_target()
        self.assertAlmostEqual(first.target_pan_degrees, -10.0)
        self.assertAlmostEqual(first.target_tilt_degrees, 0.0)


if __name__ == "__main__":
    unittest.main()
