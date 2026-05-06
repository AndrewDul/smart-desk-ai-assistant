"""
Look-at-me smoke test — runs without real Pi hardware.

This test simulates a vision backend that always returns a face at a moving
position, plus a fake pan/tilt backend that records every move_delta call.
It then runs the LookAtMeSession for ~1 second and asserts that:

  - the worker thread starts
  - it picked up faces
  - it issued at least one tracking move
  - it stops cleanly when stop() is called
  - it centers pan/tilt on stop

If you run this on a Pi with real hardware connected, NOTHING will move —
this test never touches CameraService or PanTiltService directly. It uses
fakes from the standard library only.
"""
from __future__ import annotations

import threading
import time
import unittest
from typing import Any
from unittest.mock import MagicMock

from modules.devices.vision.look_at_me.session import LookAtMeSession


class _FakeVisionBackend:
    """Minimal stand-in for CameraService — returns synthetic observations."""

    def __init__(self, *, frame_width: int = 1280, frame_height: int = 720) -> None:
        self.frame_width = frame_width
        self.frame_height = frame_height
        self._tick = 0
        self._lock = threading.Lock()
        self.calls = 0

    def latest_observation(self, *, force_refresh: bool = False) -> Any:
        del force_refresh
        with self._lock:
            self.calls += 1
            self._tick += 1
            tick = self._tick

        # Simulate a face that drifts from left to right of frame across
        # the first 30 ticks, then disappears so the scan path runs.
        if tick <= 30:
            x_ratio = 0.10 + (tick / 30.0) * 0.80
            y_ratio = 0.45
            box_size = int(self.frame_width * 0.08)
            cx = int(x_ratio * self.frame_width)
            cy = int(y_ratio * self.frame_height)
            face_box = {
                "left": max(0, cx - box_size // 2),
                "top": max(0, cy - box_size // 2),
                "right": min(self.frame_width - 1, cx + box_size // 2),
                "bottom": min(self.frame_height - 1, cy + box_size // 2),
            }
            faces = [
                {
                    "bounding_box": face_box,
                    "confidence": 0.92,
                }
            ]
        else:
            faces = []

        observation = MagicMock()
        observation.metadata = {
            "frame_width": self.frame_width,
            "frame_height": self.frame_height,
            "perception": {
                "faces": faces,
            },
        }
        return observation


class _FakePanTiltBackend:
    """Minimal stand-in for the WaveshareSerialPanTiltBackend.

    Records every move_delta and center call. Reports pan/tilt angles back
    via the result dict, just like the real backend.
    """

    def __init__(self) -> None:
        self.pan = 0.0
        self.tilt = 0.0
        self.move_calls: list[tuple[float, float]] = []
        self.center_calls = 0

    def move_delta(self, *, pan_delta_degrees: float, tilt_delta_degrees: float) -> dict[str, Any]:
        # Clamp like the real backend does (±15° pan, ±8° tilt by default).
        new_pan = max(-15.0, min(15.0, self.pan + pan_delta_degrees))
        new_tilt = max(-8.0, min(8.0, self.tilt + tilt_delta_degrees))
        self.pan = new_pan
        self.tilt = new_tilt
        self.move_calls.append((pan_delta_degrees, tilt_delta_degrees))
        return {
            "ok": True,
            "movement_executed": True,
            "pan_angle": self.pan,
            "tilt_angle": self.tilt,
        }

    def center(self) -> dict[str, Any]:
        self.center_calls += 1
        self.pan = 0.0
        self.tilt = 0.0
        return {"ok": True, "movement_executed": True, "pan_angle": 0.0, "tilt_angle": 0.0}


class LookAtMeSessionSmokeTests(unittest.TestCase):
    def test_full_lifecycle_with_fakes(self) -> None:
        vision = _FakeVisionBackend()
        pan_tilt = _FakePanTiltBackend()

        # Configure tight intervals so the test runs in well under a second.
        session = LookAtMeSession(
            vision_backend=vision,
            pan_tilt_backend=pan_tilt,
            config={
                "enabled": True,
                "target_fps": 100.0,  # very fast tick for the test
                "scan_after_no_face_frames": 3,
                "scan_interval_seconds": 0.01,
                "return_to_center_on_stop": True,
                "max_runtime_seconds": 5.0,
                "tracking": {
                    "pan_gain_degrees": 20.0,
                    "tilt_gain_degrees": 20.0,
                    "max_step_degrees": 1.4,
                    "hold_zone_x": 0.005,
                    "hold_zone_y": 0.005,
                },
                "scan": {
                    "pan_limit_degrees": 14.0,
                    "pan_step_degrees": 4.0,
                    "tilt_levels_degrees": [0.0, 4.0, 7.0],
                },
            },
        )

        result = session.start(language="en")
        self.assertTrue(result["started"], result)
        self.assertEqual(result["language"], "en")
        self.assertTrue(session.is_active())

        # Let the worker run for ~0.6 seconds.
        time.sleep(0.6)

        status_during = session.status()
        self.assertTrue(status_during["active"])

        stop_result = session.stop()
        self.assertTrue(stop_result["stopped"])
        self.assertFalse(session.is_active())

        # We expect at LEAST one tracking move and at least one camera read.
        self.assertGreater(vision.calls, 5, "vision backend was not polled enough")
        self.assertGreater(
            len(pan_tilt.move_calls),
            0,
            "pan/tilt was never moved during tracking",
        )
        # And the center-on-stop should have fired exactly once.
        self.assertEqual(pan_tilt.center_calls, 1)

    def test_disabled_session_refuses_to_start(self) -> None:
        vision = _FakeVisionBackend()
        pan_tilt = _FakePanTiltBackend()
        session = LookAtMeSession(
            vision_backend=vision,
            pan_tilt_backend=pan_tilt,
            config={"enabled": False},
        )
        result = session.start()
        self.assertFalse(result["started"])
        self.assertEqual(result["reason"], "disabled_by_config")
        self.assertFalse(session.is_active())
        self.assertEqual(pan_tilt.move_calls, [])

    def test_double_start_is_noop(self) -> None:
        vision = _FakeVisionBackend()
        pan_tilt = _FakePanTiltBackend()
        session = LookAtMeSession(
            vision_backend=vision,
            pan_tilt_backend=pan_tilt,
            config={"target_fps": 50.0, "max_runtime_seconds": 5.0},
        )
        first = session.start()
        self.assertTrue(first["started"])
        try:
            second = session.start()
            self.assertFalse(second["started"])
            self.assertEqual(second["reason"], "already_active")
        finally:
            session.stop()


if __name__ == "__main__":
    unittest.main()
