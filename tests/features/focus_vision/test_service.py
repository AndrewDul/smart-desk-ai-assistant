from __future__ import annotations

import json

from modules.features.focus_vision import FocusVisionConfig, FocusVisionSentinelService, FocusVisionState
from modules.runtime.contracts import VisionObservation


def _signal(active: bool, confidence: float) -> dict[str, object]:
    return {"active": active, "confidence": confidence, "reasons": [], "metadata": {}}


def _session(active: bool, seconds: float) -> dict[str, object]:
    return {
        "active": active,
        "state": "active" if active else "inactive",
        "current_active_seconds": seconds,
        "last_active_streak_seconds": 0.0,
        "total_active_seconds": seconds,
        "activations": 1 if active else 0,
        "last_started_at": 1.0 if active else None,
        "last_ended_at": None,
        "metadata": {},
    }


class _VisionBackend:
    def __init__(self, observation: VisionObservation | None) -> None:
        self.observation = observation
        self.calls: list[bool] = []

    def latest_observation(self, *, force_refresh: bool = True):
        self.calls.append(force_refresh)
        return self.observation


def _phone_observation(captured_at: float) -> VisionObservation:
    return VisionObservation(
        detected=True,
        user_present=True,
        desk_active=True,
        computer_work_likely=False,
        on_phone_likely=True,
        studying_likely=False,
        confidence=0.9,
        captured_at=captured_at,
        metadata={
            "behavior": {
                "presence": _signal(True, 0.9),
                "desk_activity": _signal(True, 0.8),
                "computer_work": _signal(False, 0.0),
                "phone_usage": _signal(True, 0.8),
                "study_activity": _signal(False, 0.0),
            },
            "sessions": {
                "presence": _session(True, 20.0),
                "desk_activity": _session(True, 20.0),
                "computer_work": _session(False, 0.0),
                "phone_usage": _session(True, 20.0),
                "study_activity": _session(False, 0.0),
            },
        },
    )


def test_tick_writes_telemetry_and_returns_reminder_candidate(tmp_path) -> None:
    telemetry_path = tmp_path / "focus_vision.jsonl"
    backend = _VisionBackend(_phone_observation(captured_at=20.0))
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=FocusVisionConfig(
            enabled=True,
            dry_run=True,
            startup_grace_seconds=0.0,
            phone_warning_after_seconds=1.0,
            telemetry_path=str(telemetry_path),
        ),
    )
    assert service.reminder_policy is not None
    service.reminder_policy.start_session(started_at=0.0)

    first = service.tick(now=20.0)
    backend.observation = _phone_observation(captured_at=22.0)
    second = service.tick(now=22.0)

    assert first.snapshot is not None
    assert first.snapshot.current_state == FocusVisionState.PHONE_DISTRACTION
    assert second.reminder is not None
    assert second.reminder.dry_run is True
    assert backend.calls == [True, True]

    lines = telemetry_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[-1])["snapshot"]["current_state"] == "phone_distraction"


def test_tick_delivers_reminder_when_voice_warnings_are_enabled(tmp_path) -> None:
    telemetry_path = tmp_path / "focus_vision_delivery.jsonl"
    backend = _VisionBackend(_phone_observation(captured_at=20.0))
    delivered = []
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=FocusVisionConfig(
            enabled=True,
            dry_run=False,
            voice_warnings_enabled=True,
            startup_grace_seconds=0.0,
            phone_warning_after_seconds=1.0,
            warning_cooldown_seconds=0.0,
            telemetry_path=str(telemetry_path),
        ),
    )
    service.set_reminder_handler(delivered.append)
    assert service.reminder_policy is not None
    service.reminder_policy.start_session(started_at=0.0)

    service.tick(now=20.0)
    backend.observation = _phone_observation(captured_at=22.0)
    result = service.tick(now=22.0)

    assert result.reminder is not None
    assert result.reminder.dry_run is False
    assert result.reminder_delivered is True
    assert result.reminder_delivery_error is None
    assert delivered == [result.reminder]
    status = service.status()
    assert status["delivered_reminder_count"] == 1
    assert status["reminder_handler_attached"] is True

    last_event = json.loads(telemetry_path.read_text(encoding="utf-8").splitlines()[-1])
    assert last_event["reminder_delivered"] is True
    assert last_event["reminder_delivery_error"] is None


def test_tick_records_missing_handler_when_voice_warning_delivery_is_active(tmp_path) -> None:
    backend = _VisionBackend(_phone_observation(captured_at=20.0))
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=FocusVisionConfig(
            enabled=True,
            dry_run=False,
            voice_warnings_enabled=True,
            startup_grace_seconds=0.0,
            phone_warning_after_seconds=1.0,
            warning_cooldown_seconds=0.0,
            telemetry_path=str(tmp_path / "focus_vision_missing_handler.jsonl"),
        ),
    )
    assert service.reminder_policy is not None
    service.reminder_policy.start_session(started_at=0.0)

    service.tick(now=20.0)
    backend.observation = _phone_observation(captured_at=22.0)
    result = service.tick(now=22.0)

    assert result.reminder is not None
    assert result.reminder_delivered is False
    assert result.reminder_delivery_error == "no_reminder_handler"
    assert service.status()["last_delivery_error"] == "no_reminder_handler"
