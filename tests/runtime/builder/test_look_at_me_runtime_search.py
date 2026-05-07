from __future__ import annotations

import time
from typing import Any

from modules.devices.vision.tracking import TrackingMotionPlan
from modules.runtime.builder.look_at_me_mixin import LookAtMeSession


class _NoTargetTrackingService:
    def __init__(self) -> None:
        self.force_refresh_values: list[bool] = []

    def plan_once(self, *, force_refresh: bool = False) -> TrackingMotionPlan:
        self.force_refresh_values.append(force_refresh)
        return TrackingMotionPlan(has_target=False, target=None, reason="no_target")

    def latest_execution_result(self) -> dict[str, Any]:
        return {"has_target": False}

    def latest_pan_tilt_adapter_result(self) -> dict[str, Any]:
        return {"has_target": False}

    def status(self) -> dict[str, Any]:
        return {"ok": True}


class _SearchPanTiltBackend:
    def __init__(self) -> None:
        self.pan = 0.0
        self.tilt = -2.0
        self.move_calls: list[dict[str, float]] = []

    def status(self) -> dict[str, Any]:
        return {
            "pan_angle": self.pan,
            "tilt_angle": self.tilt,
            "safe_limits": {
                "pan_min_degrees": -10.0,
                "pan_center_degrees": 0.0,
                "pan_max_degrees": 10.0,
                "tilt_min_degrees": -6.0,
                "tilt_center_degrees": 0.0,
                "tilt_max_degrees": 8.0,
            },
        }

    def move_delta(self, *, pan_delta_degrees: float, tilt_delta_degrees: float) -> dict[str, Any]:
        self.pan += float(pan_delta_degrees)
        self.tilt += float(tilt_delta_degrees)
        self.move_calls.append(
            {
                "pan_delta_degrees": float(pan_delta_degrees),
                "tilt_delta_degrees": float(tilt_delta_degrees),
            }
        )
        return {
            "ok": True,
            "movement_executed": True,
            "pan_angle": self.pan,
            "tilt_angle": self.tilt,
        }


class _VisionBackend:
    def start(self) -> None:
        return None


def test_look_at_me_search_sweeps_pan_and_never_scans_tilt_down() -> None:
    tracking = _NoTargetTrackingService()
    pan_tilt = _SearchPanTiltBackend()
    session = LookAtMeSession(
        settings={
            "look_at_me": {
                "enabled": True,
                "runtime_pan_tilt_execution_enabled": False,
                "runtime_hardware_execution_enabled": False,
                "physical_movement_confirmed": False,
                "search_when_no_face": True,
                "search_after_no_face_seconds": 0.05,
                "search_interval_seconds": 0.05,
                "search_step_degrees": 0.4,
                "search_tilt_levels_degrees": [4.0, 8.0, 12.0],
                "max_runtime_step_degrees": 0.4,
                "force_refresh_during_tracking": False,
            },
            "pan_tilt": {},
            "vision_tracking": {},
        },
        vision_backend=_VisionBackend(),
        pan_tilt_backend=pan_tilt,
        vision_tracking_service=tracking,
    )
    session._started_at = time.monotonic() - 1.0
    session._last_target_seen_at = time.monotonic() - 1.0

    result = session._run_once(min_delta=0.0)

    assert result["search_active"] is True
    assert result["movement_executed"] is True
    assert tracking.force_refresh_values == [False]
    assert pan_tilt.move_calls
    assert pan_tilt.move_calls[-1]["pan_delta_degrees"] < 0.0
    assert pan_tilt.move_calls[-1]["tilt_delta_degrees"] >= 0.0
    assert result["search"]["tilt_upper_only"] is True
