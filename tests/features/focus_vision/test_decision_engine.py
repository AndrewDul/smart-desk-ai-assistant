from __future__ import annotations

from modules.features.focus_vision import FocusVisionDecisionEngine, FocusVisionState
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


def _observation(
    *,
    presence: bool,
    desk: bool,
    computer: bool,
    phone: bool,
    study: bool,
    captured_at: float = 10.0,
) -> VisionObservation:
    return VisionObservation(
        detected=True,
        user_present=presence,
        desk_active=desk,
        computer_work_likely=computer,
        on_phone_likely=phone,
        studying_likely=study,
        confidence=0.9,
        captured_at=captured_at,
        metadata={
            "behavior": {
                "presence": _signal(presence, 0.9),
                "desk_activity": _signal(desk, 0.8),
                "computer_work": _signal(computer, 0.8),
                "phone_usage": _signal(phone, 0.7),
                "study_activity": _signal(study, 0.75),
            },
            "sessions": {
                "presence": _session(presence, 12.0),
                "desk_activity": _session(desk, 12.0),
                "computer_work": _session(computer, 12.0),
                "phone_usage": _session(phone, 12.0),
                "study_activity": _session(study, 12.0),
            },
        },
    )


def test_decision_reports_no_observation_when_camera_result_missing() -> None:
    decision = FocusVisionDecisionEngine().decide(None, observed_at=1.0)

    assert decision.state == FocusVisionState.NO_OBSERVATION
    assert decision.reasons == ("no_vision_observation",)


def test_decision_reports_on_task_when_user_is_at_desk_and_working() -> None:
    observation = _observation(presence=True, desk=True, computer=True, phone=False, study=False)

    decision = FocusVisionDecisionEngine().decide(observation)

    assert decision.state == FocusVisionState.ON_TASK
    assert "computer_work_active" in decision.reasons
    assert "phone_usage_inactive" in decision.reasons


def test_decision_reports_phone_distraction_before_on_task() -> None:
    observation = _observation(presence=True, desk=True, computer=False, phone=True, study=True)

    decision = FocusVisionDecisionEngine().decide(observation)

    assert decision.state == FocusVisionState.PHONE_DISTRACTION
    assert "phone_usage_active" in decision.reasons


def test_decision_reports_absent_when_presence_and_desk_are_inactive() -> None:
    observation = _observation(presence=False, desk=False, computer=False, phone=False, study=False)

    decision = FocusVisionDecisionEngine().decide(observation)

    assert decision.state == FocusVisionState.ABSENT


def test_decision_reports_uncertain_for_mixed_low_focus_evidence() -> None:
    observation = _observation(presence=True, desk=True, computer=False, phone=False, study=False)

    decision = FocusVisionDecisionEngine().decide(observation)

    assert decision.state == FocusVisionState.UNCERTAIN
