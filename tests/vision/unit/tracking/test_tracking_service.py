from __future__ import annotations

from modules.devices.vision.tracking import VisionTrackingService
from modules.runtime.contracts import VisionObservation


class _FakeVisionBackend:
    def __init__(self, observation: VisionObservation | None) -> None:
        self.observation = observation
        self.force_refresh_values: list[bool] = []

    def latest_observation(self, *, force_refresh: bool = True) -> VisionObservation | None:
        self.force_refresh_values.append(force_refresh)
        return self.observation


class _FakePanTiltBackend:
    def __init__(self, *, pan_angle: float = 0.0, tilt_angle: float = 0.0) -> None:
        self.pan_angle = pan_angle
        self.tilt_angle = tilt_angle
        self.move_calls: list[str] = []

    def status(self) -> dict:
        return {
            "pan_angle": self.pan_angle,
            "tilt_angle": self.tilt_angle,
            "safe_limits": {
                "pan_min_degrees": -15.0,
                "pan_center_degrees": 0.0,
                "pan_max_degrees": 15.0,
                "tilt_min_degrees": -8.0,
                "tilt_center_degrees": 0.0,
                "tilt_max_degrees": 8.0,
            },
        }

    def move_direction(self, direction: str) -> dict:
        self.move_calls.append(direction)
        return {"ok": True}


def _observation(center_left: int, center_right: int) -> VisionObservation:
    return VisionObservation(
        detected=True,
        metadata={
            "frame_width": 1280,
            "frame_height": 720,
            "perception": {
                "faces": [
                    {
                        "confidence": 0.9,
                        "bounding_box": {
                            "left": center_left,
                            "top": 180,
                            "right": center_right,
                            "bottom": 360,
                        },
                    }
                ],
                "people": [],
            },
        },
    )


def test_tracking_service_uses_cached_observation_by_default_and_never_moves_hardware() -> None:
    vision = _FakeVisionBackend(_observation(930, 1130))
    pan_tilt = _FakePanTiltBackend(pan_angle=0.0)
    service = VisionTrackingService(vision_backend=vision, pan_tilt_backend=pan_tilt)

    plan = service.plan_once()

    assert vision.force_refresh_values == [False]
    assert pan_tilt.move_calls == []
    assert plan.has_target is True
    assert plan.reason == "recenter_target"
    assert plan.pan_delta_degrees == 2.0
    assert service.status()["dry_run"] is True
    assert service.status()["movement_execution_enabled"] is False


def test_tracking_service_marks_required_base_yaw_assist_near_pan_limit() -> None:
    vision = _FakeVisionBackend(_observation(1100, 1260))
    pan_tilt = _FakePanTiltBackend(pan_angle=14.5)
    service = VisionTrackingService(vision_backend=vision, pan_tilt_backend=pan_tilt)

    plan = service.plan_once()

    assert plan.pan_at_limit is True
    assert plan.base_yaw_assist_required is True
    assert plan.base_yaw_direction == "right"
    assert plan.base_forward_velocity == 0.0
    assert plan.base_backward_velocity == 0.0
    assert plan.mobile_assist_recommended is True
    assert plan.reason == "pan_limit_base_yaw_assist_required"


def test_tracking_service_returns_no_target_plan_without_observation() -> None:
    service = VisionTrackingService(vision_backend=_FakeVisionBackend(None))

    plan = service.plan_once()

    assert plan.has_target is False
    assert plan.reason == "no_target"
    assert service.status()["ok"] is True
