from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from modules.features.focus_vision import FocusVisionConfig, FocusVisionSentinelService
from modules.runtime.contracts import VisionObservation


def _signal(active: bool) -> dict[str, object]:
    return {"active": active, "confidence": 0.9, "reasons": [], "metadata": {}}


def _observation(
    *,
    face_box: dict[str, int] | None = None,
    person_box: dict[str, int] | None = None,
    captured_at: float = 100.0,
) -> VisionObservation:
    faces = []
    if face_box is not None:
        faces.append({"bounding_box": dict(face_box), "confidence": 0.9})
    objects = []
    labels = []
    if face_box is not None:
        labels.append("face_detected")
    if person_box is not None:
        labels.append("object:person")
        objects.append({"label": "person", "bounding_box": dict(person_box), "confidence": 0.9})
    return VisionObservation(
        detected=True,
        user_present=bool(face_box),
        confidence=0.9,
        captured_at=captured_at,
        labels=labels,
        metadata={
            "frame_width": 640,
            "frame_height": 480,
            "behavior": {
                "presence": _signal(bool(face_box)),
                "desk_activity": _signal(False),
                "computer_work": _signal(False),
                "phone_usage": _signal(False),
                "study_activity": _signal(False),
            },
            "sessions": {},
            "perception": {
                "frame_width": 640,
                "frame_height": 480,
                "face_count": len(faces),
                "people_count": 0,
                "faces": faces,
                "people": [],
                "objects": objects,
            },
        },
    )


def _service(
    *,
    backend: Any,
    pan_tilt: Any,
    **config_overrides: Any,
) -> FocusVisionSentinelService:
    config = FocusVisionConfig(
        enabled=True,
        dry_run=False,
        voice_warnings_enabled=True,
        continuous_tracking_enabled=True,
        startup_grace_seconds=0.0,
        warning_cooldown_seconds=0.0,
        **config_overrides,
    )
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=config,
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )
    service._running = True
    return service


def test_tracking_worker_cancels_scan_when_face_reappears() -> None:
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(
        face_box={"left": 400, "top": 180, "right": 500, "bottom": 280},
        captured_at=100.0,
    )
    pan_tilt = MagicMock()
    pan_tilt.status.return_value = {"tilt_angle": 2.0}
    pan_tilt.move_delta.return_value = {"movement_executed": True}
    service = _service(backend=backend, pan_tilt=pan_tilt)
    service._focus_scan_running = True
    service._focus_scan_started_at = 99.0
    service._active_focus_scan_id = "away_recheck_99.000"
    service._active_focus_scan_type = "away_recheck"

    status = service._tracking_worker_step(current_time=100.0)

    assert status["scan_cancelled"] is True
    assert status["tracking_target_type"] == "face"
    assert status["tracking_move_executed"] is True
    assert service._focus_scan_running is False
    assert service._active_focus_scan_id == ""


def test_tracking_worker_does_not_cancel_scan_for_person_without_face() -> None:
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(
        person_box={"left": 260, "top": 100, "right": 380, "bottom": 420},
        captured_at=100.0,
    )
    pan_tilt = MagicMock()
    service = _service(backend=backend, pan_tilt=pan_tilt)
    service._focus_scan_running = True
    service._focus_scan_started_at = 99.0
    service._active_focus_scan_id = "away_recheck_99.000"
    service._active_focus_scan_type = "away_recheck"

    status = service._tracking_worker_step(current_time=100.0)

    assert status["tracking_reason"] == "paused_for_focus_scan"
    assert status.get("scan_cancelled") is not True
    assert service._focus_scan_running is True
    pan_tilt.move_delta.assert_not_called()


def test_person_without_face_never_becomes_tracking_target() -> None:
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(
        person_box={"left": 260, "top": 100, "right": 380, "bottom": 420},
        captured_at=100.0,
    )
    pan_tilt = MagicMock()
    service = _service(backend=backend, pan_tilt=pan_tilt, face_lost_debounce_seconds=0.0)

    status = service._tracking_worker_step(current_time=100.0)

    assert status["tracking_target_type"] == "none"
    assert status["tracking_state"] == "face_reacquire"
    assert status["immediate_away_scan_started"] is True
    pan_tilt.move_delta.assert_not_called()


def test_tracking_worker_emits_stage_latency_and_target_center() -> None:
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(
        face_box={"left": 400, "top": 120, "right": 500, "bottom": 220},
        captured_at=100.0,
    )
    pan_tilt = MagicMock()
    pan_tilt.status.return_value = {"tilt_angle": 4.0}
    pan_tilt.move_delta.return_value = {
        "movement_executed": True,
        "latest_telemetry": {"pan": 1.0, "tilt": 4.5},
    }
    service = _service(backend=backend, pan_tilt=pan_tilt)

    status = service._tracking_worker_step(current_time=100.0)

    assert status["latest_observation_seconds"] >= 0.0
    assert status["evidence_read_seconds"] >= 0.0
    assert status["target_selection_seconds"] >= 0.0
    assert status["planning_seconds"] >= 0.0
    assert status["pan_tilt_move_delta_seconds"] >= 0.0
    assert status["tracking_target"]["target_type"] == "face"
    assert 0.0 < status["tracking_target"]["center_y_norm"] < 1.0
    assert status["tracking_backend_response"]["latest_telemetry"]["tilt"] == 4.5


def test_tracking_worker_never_commands_tilt_below_center() -> None:
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(
        face_box={"left": 270, "top": 350, "right": 370, "bottom": 450},
        captured_at=100.0,
    )
    pan_tilt = MagicMock()
    pan_tilt.status.return_value = {"tilt_angle": 0.0}
    pan_tilt.move_delta.return_value = {"movement_executed": True}
    service = _service(backend=backend, pan_tilt=pan_tilt)

    status = service._tracking_worker_step(current_time=100.0)

    pan_tilt.move_delta.assert_not_called()
    assert status["tilt_clamped_to_center"] is True
    assert status["tracking_move_degrees"]["tilt_delta_degrees"] == 0.0
    assert status["tracking_reason"] == "target_centered"


def test_tracking_worker_never_commands_negative_tilt_when_above_center() -> None:
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(
        face_box={"left": 270, "top": 350, "right": 370, "bottom": 450},
        captured_at=100.0,
    )
    pan_tilt = MagicMock()
    pan_tilt.status.return_value = {"tilt_angle": 6.0}
    pan_tilt.move_delta.return_value = {"movement_executed": True}
    service = _service(backend=backend, pan_tilt=pan_tilt)

    status = service._tracking_worker_step(current_time=100.0)

    pan_tilt.move_delta.assert_not_called()
    assert status["raw_tilt_delta_degrees"] < 0.0
    assert status["final_tilt_delta_degrees"] == 0.0
    assert status["tracking_move_degrees"]["tilt_delta_degrees"] == 0.0
