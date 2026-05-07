from __future__ import annotations

from modules.devices.vision.tracking import VisionTrackingService
from modules.runtime.contracts import VisionObservation


class _FastObservationBackend:
    def __init__(self) -> None:
        self.fast_calls = []
        self.latest_calls = []

    def latest_tracking_observation(self, *, force_refresh: bool) -> VisionObservation:
        self.fast_calls.append(force_refresh)
        return VisionObservation(
            detected=True,
            confidence=0.9,
            metadata={
                "frame_width": 640,
                "frame_height": 360,
                "perception": {
                    "faces": [
                        {
                            "confidence": 0.9,
                            "bounding_box": {
                                "left": 360,
                                "top": 110,
                                "right": 450,
                                "bottom": 220,
                            },
                            "metadata": {"source": "unit_test"},
                        }
                    ],
                    "people": [],
                },
            },
        )

    def latest_observation(self, *, force_refresh: bool) -> VisionObservation | None:
        self.latest_calls.append(force_refresh)
        return None


class _PanTiltBackend:
    def status(self) -> dict[str, object]:
        return {
            "pan_angle": 0.0,
            "tilt_angle": 0.0,
            "safe_limits": {
                "pan_min_degrees": -35.0,
                "pan_max_degrees": 35.0,
                "tilt_min_degrees": -12.0,
                "tilt_max_degrees": 12.0,
            },
        }


def test_tracking_service_prefers_face_only_observation_for_look_at_me() -> None:
    backend = _FastObservationBackend()
    service = VisionTrackingService(
        vision_backend=backend,
        pan_tilt_backend=_PanTiltBackend(),
        config={
            "prefer_face_only_observation": True,
            "persist_status": False,
            "policy": {
                "dead_zone_x": 0.0,
                "dead_zone_y": 0.0,
                "target_activation_hits": 1,
                "min_target_confidence": 0.5,
                "min_face_area_norm": 0.001,
            },
        },
    )

    plan = service.plan_once(force_refresh=True)

    assert backend.fast_calls == [True]
    assert backend.latest_calls == []
    assert plan.has_target is True
    assert plan.reason == "recenter_target"
