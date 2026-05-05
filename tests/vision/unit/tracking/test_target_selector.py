from __future__ import annotations

from modules.devices.vision.tracking import TrackingTargetSelector
from modules.runtime.contracts import VisionObservation


def _observation(perception: dict) -> VisionObservation:
    return VisionObservation(
        detected=True,
        metadata={
            "frame_width": 1280,
            "frame_height": 720,
            "perception": perception,
        },
    )


def test_selector_returns_none_without_perception() -> None:
    selector = TrackingTargetSelector()

    assert selector.select(VisionObservation()) is None


def test_selector_prefers_face_over_person_for_tracking() -> None:
    selector = TrackingTargetSelector()
    observation = _observation(
        {
            "faces": [
                {
                    "confidence": 0.82,
                    "bounding_box": {"left": 560, "top": 160, "right": 680, "bottom": 300},
                    "metadata": {"detector": "opencv_haar"},
                }
            ],
            "people": [
                {
                    "confidence": 0.90,
                    "bounding_box": {"left": 360, "top": 120, "right": 920, "bottom": 710},
                    "metadata": {"source": "face_projected"},
                }
            ],
        }
    )

    target = selector.select(observation)

    assert target is not None
    assert target.target_type == "face"
    assert target.source_index == 0
    assert target.metadata["detector"] == "opencv_haar"
    assert 0.45 < target.center_x_norm < 0.55


def test_selector_falls_back_to_person_when_face_is_missing() -> None:
    selector = TrackingTargetSelector()
    observation = _observation(
        {
            "faces": [],
            "people": [
                {
                    "confidence": 0.76,
                    "bounding_box": {"left": 900, "top": 180, "right": 1200, "bottom": 700},
                }
            ],
        }
    )

    target = selector.select(observation)

    assert target is not None
    assert target.target_type == "person"
    assert target.center_x_norm > 0.8
