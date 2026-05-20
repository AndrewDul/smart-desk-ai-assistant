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
    labels: tuple[str, ...] = (),
    face_count: int = 0,
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
        labels=labels,
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
            "perception": {
                "face_count": face_count,
                "people_count": 0,
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
    observation = _observation(
        presence=True,
        desk=True,
        computer=False,
        phone=True,
        study=True,
        face_count=1,
        labels=("object:cell phone",),
    )

    decision = FocusVisionDecisionEngine().decide(observation)

    assert decision.state == FocusVisionState.PHONE_DISTRACTION
    assert "hard_phone_evidence" in decision.reasons


def test_decision_ignores_behavior_phone_without_hard_visual_phone() -> None:
    observation = _observation(
        presence=True,
        desk=True,
        computer=False,
        phone=True,
        study=True,
        face_count=1,
    )

    decision = FocusVisionDecisionEngine().decide(observation)

    assert decision.state != FocusVisionState.PHONE_DISTRACTION


def test_decision_reports_absent_when_presence_and_desk_are_inactive() -> None:
    observation = _observation(presence=False, desk=False, computer=False, phone=False, study=False)

    decision = FocusVisionDecisionEngine().decide(observation)

    assert decision.state == FocusVisionState.ABSENT


def test_decision_does_not_let_face_label_block_absent_without_active_presence() -> None:
    # Face feature labels alone (no YOLO person, no perception counts) must not prevent ABSENT.
    observation = _observation(
        presence=False,
        desk=False,
        computer=False,
        phone=False,
        study=False,
        labels=("person_in_desk_zone", "face_in_engagement_zone", "face_detected"),
    )

    decision = FocusVisionDecisionEngine().decide(observation)

    assert decision.state == FocusVisionState.ABSENT
    assert "no_active_presence" in decision.reasons


def test_decision_yolo_person_label_produces_probably_present() -> None:
    # YOLO "object:person" bridges into people_count=1 when face/people counts are zero,
    # producing PROBABLY_PRESENT rather than ABSENT. This is the intended YOLO fallback behavior.
    observation = _observation(
        presence=False,
        desk=False,
        computer=False,
        phone=False,
        study=False,
        labels=("object:person", "person_in_desk_zone"),
    )

    decision = FocusVisionDecisionEngine().decide(observation)

    assert decision.state == FocusVisionState.PROBABLY_PRESENT
    assert "person_without_face" in decision.reasons


def test_decision_reports_absent_when_desk_activity_exists_but_no_face_or_presence() -> None:
    observation = _observation(
        presence=False,
        desk=True,
        computer=False,
        phone=False,
        study=False,
        labels=("person_in_desk_zone",),
    )

    decision = FocusVisionDecisionEngine().decide(observation)

    assert decision.state == FocusVisionState.ABSENT
    assert "no_active_presence" in decision.reasons



def test_decision_blocks_absent_only_when_face_and_active_presence_exist() -> None:
    observation = _observation(
        presence=True,
        desk=False,
        computer=False,
        phone=False,
        study=False,
        labels=("face_in_engagement_zone", "face_detected"),
    )

    decision = FocusVisionDecisionEngine().decide(observation)

    assert decision.state == FocusVisionState.UNCERTAIN
    assert "active_face_presence_blocks_absence" in decision.reasons


def test_decision_reports_uncertain_for_mixed_low_focus_evidence() -> None:
    observation = _observation(presence=True, desk=True, computer=False, phone=False, study=False)

    decision = FocusVisionDecisionEngine().decide(observation)

    assert decision.state == FocusVisionState.UNCERTAIN
