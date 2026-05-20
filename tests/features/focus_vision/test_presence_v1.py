"""Tests for Focus Mode Desk Presence v1 — person-without-face detection and absence confirmation."""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from modules.features.focus_vision import (
    FocusVisionConfig,
    FocusVisionDecisionEngine,
    FocusVisionReminderKind,
    FocusVisionReminderPolicy,
    FocusVisionSentinelService,
    FocusVisionState,
    FocusVisionStateMachine,
    FocusVisionStateSnapshot,
)
from modules.features.focus_vision.models import FocusVisionDecision, FocusVisionEvidence
from modules.features.focus_vision.observation_reader import FocusVisionObservationReader
from modules.runtime.contracts import VisionObservation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signal(active: bool, confidence: float = 0.9) -> dict[str, object]:
    return {"active": active, "confidence": confidence, "reasons": [], "metadata": {}}


def _session(active: bool, seconds: float = 0.0) -> dict[str, object]:
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
    presence: bool = False,
    desk: bool = False,
    computer: bool = False,
    phone: bool = False,
    study: bool = False,
    face_count: int = 0,
    people_count: int = 0,
    captured_at: float = 10.0,
    labels: tuple[str, ...] = (),
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
                "presence": _signal(presence),
                "desk_activity": _signal(desk),
                "computer_work": _signal(computer),
                "phone_usage": _signal(phone),
                "study_activity": _signal(study),
            },
            "sessions": {
                "presence": _session(presence),
                "desk_activity": _session(desk),
                "computer_work": _session(computer),
                "phone_usage": _session(phone),
                "study_activity": _session(study),
            },
            "perception": {
                "face_count": face_count,
                "people_count": people_count,
            },
        },
    )


def _fast_config(**kwargs: Any) -> FocusVisionConfig:
    return FocusVisionConfig(
        enabled=True,
        dry_run=False,
        voice_warnings_enabled=True,
        startup_grace_seconds=0.0,
        absence_warning_after_seconds=kwargs.pop("absence_warning_after_seconds", 0.5),
        warning_cooldown_seconds=kwargs.pop("warning_cooldown_seconds", 1.0),
        absence_pending_scan_after_seconds=kwargs.pop("absence_pending_scan_after_seconds", 5.0),
        pan_tilt_scan_enabled=kwargs.pop("pan_tilt_scan_enabled", False),
        **kwargs,
    )


def _mock_vision_backend(observation: VisionObservation | None = None) -> MagicMock:
    backend = MagicMock()
    backend.latest_observation.return_value = observation
    return backend


def _tick_with_snapshot(
    service: FocusVisionSentinelService,
    snapshot_state: FocusVisionState,
    stable_seconds: float,
    now: float,
) -> FocusVisionStateSnapshot:
    snapshot = FocusVisionStateSnapshot(
        current_state=snapshot_state,
        stable_seconds=stable_seconds,
        state_started_at=now - stable_seconds,
        updated_at=now,
        decision=FocusVisionDecision(
            state=snapshot_state,
            confidence=0.75,
            reasons=("test",),
            observed_at=now,
            evidence=FocusVisionEvidence(),
        ),
    )
    return service._apply_derived_presence_states(snapshot, now)


# ---------------------------------------------------------------------------
# Tests 1–4: Decision engine new state paths
# ---------------------------------------------------------------------------

def test_face_and_presence_active_is_on_task() -> None:
    obs = _observation(presence=True, desk=True, computer=True, face_count=1, people_count=1)
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state == FocusVisionState.ON_TASK


def test_person_without_face_is_probably_present() -> None:
    obs = _observation(presence=False, desk=False, people_count=1, face_count=0)
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state == FocusVisionState.PROBABLY_PRESENT
    assert "person_without_face" in decision.reasons


def test_people_count_blocks_absent_state() -> None:
    obs = _observation(presence=False, desk=False, computer=False, phone=False, study=False, people_count=1, face_count=0)
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state != FocusVisionState.ABSENT, "ABSENT must not fire when people_count > 0"


def test_no_person_no_face_is_absent() -> None:
    obs = _observation(presence=False, desk=False, computer=False, phone=False, study=False, people_count=0, face_count=0)
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state == FocusVisionState.ABSENT
    assert "no_person_detected" in decision.reasons


# ---------------------------------------------------------------------------
# Test 5: Desk objects alone (person=0) → ABSENT, not PROBABLY_PRESENT
# ---------------------------------------------------------------------------

def test_desk_objects_without_person_is_absent() -> None:
    obs = _observation(presence=False, desk=True, study=False, computer=False, people_count=0, face_count=0)
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state == FocusVisionState.ABSENT


# ---------------------------------------------------------------------------
# Tests 6–9: Service-layer derived states
# ---------------------------------------------------------------------------

def test_absent_below_threshold_stays_absent() -> None:
    service = FocusVisionSentinelService(
        vision_backend=_mock_vision_backend(),
        config=_fast_config(absence_pending_scan_after_seconds=10.0),
    )
    result = _tick_with_snapshot(service, FocusVisionState.ABSENT, stable_seconds=5.0, now=100.0)
    assert result.current_state == FocusVisionState.ABSENT


def test_absent_over_threshold_without_pan_tilt_stays_away_pending_not_confirmed() -> None:
    service = FocusVisionSentinelService(
        vision_backend=_mock_vision_backend(),
        config=_fast_config(absence_pending_scan_after_seconds=5.0, pan_tilt_scan_enabled=False),
    )
    result = _tick_with_snapshot(service, FocusVisionState.ABSENT, stable_seconds=10.0, now=100.0)
    assert result.current_state == FocusVisionState.AWAY_PENDING_SCAN, (
        "blocked scan must stay AWAY_PENDING_SCAN, never AWAY_CONFIRMED"
    )


def test_absent_over_threshold_with_pan_tilt_becomes_away_pending_scan() -> None:
    pan_tilt = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=_mock_vision_backend(),
        config=_fast_config(absence_pending_scan_after_seconds=5.0, pan_tilt_scan_enabled=True),
        pan_tilt_backend=pan_tilt,
    )
    result = _tick_with_snapshot(service, FocusVisionState.ABSENT, stable_seconds=10.0, now=100.0)
    assert result.current_state == FocusVisionState.AWAY_PENDING_SCAN


def test_scan_not_found_produces_away_confirmed() -> None:
    service = FocusVisionSentinelService(
        vision_backend=_mock_vision_backend(),
        config=_fast_config(absence_pending_scan_after_seconds=5.0, pan_tilt_scan_enabled=False),
    )
    service._micro_scan_state = "not_found"
    result = _tick_with_snapshot(service, FocusVisionState.ABSENT, stable_seconds=10.0, now=100.0)
    assert result.current_state == FocusVisionState.AWAY_CONFIRMED


# ---------------------------------------------------------------------------
# Test 10: Non-ABSENT state resets scan state
# ---------------------------------------------------------------------------

def test_non_absent_state_resets_scan_state() -> None:
    service = FocusVisionSentinelService(
        vision_backend=_mock_vision_backend(),
        config=_fast_config(),
    )
    service._micro_scan_state = "scanning"
    result = _tick_with_snapshot(service, FocusVisionState.PROBABLY_PRESENT, stable_seconds=3.0, now=100.0)
    assert result.current_state == FocusVisionState.PROBABLY_PRESENT
    assert service._micro_scan_state == "idle"


# ---------------------------------------------------------------------------
# Tests 11–12: Reminder policy
# ---------------------------------------------------------------------------

def test_away_confirmed_triggers_absence_reminder() -> None:
    config = _fast_config()
    policy = FocusVisionReminderPolicy(config=config)
    policy.start_session(started_at=0.0)
    now = 100.0
    snapshot = FocusVisionStateSnapshot(
        current_state=FocusVisionState.AWAY_CONFIRMED,
        stable_seconds=3.0,
        state_started_at=now - 3.0,
        updated_at=now,
        decision=FocusVisionDecision(FocusVisionState.AWAY_CONFIRMED, 0.9, ("test",), now, FocusVisionEvidence()),
    )
    reminder = policy.evaluate(snapshot, language="en", now=now)
    assert reminder is not None
    assert reminder.kind.value == "absence"


def test_probably_present_does_not_trigger_reminder() -> None:
    config = _fast_config()
    policy = FocusVisionReminderPolicy(config=config)
    policy.start_session(started_at=0.0)
    now = 100.0
    snapshot = FocusVisionStateSnapshot(
        current_state=FocusVisionState.PROBABLY_PRESENT,
        stable_seconds=30.0,
        state_started_at=now - 30.0,
        updated_at=now,
        decision=FocusVisionDecision(FocusVisionState.PROBABLY_PRESENT, 0.5, ("person_without_face",), now, FocusVisionEvidence()),
    )
    reminder = policy.evaluate(snapshot, language="en", now=now)
    assert reminder is None


# ---------------------------------------------------------------------------
# Test 13: Evidence extraction — face_count and people_count from perception
# ---------------------------------------------------------------------------

def test_evidence_extracts_face_count_from_perception() -> None:
    obs = _observation(face_count=2, people_count=2)
    evidence = FocusVisionObservationReader().read(obs)
    assert evidence.face_count == 2
    assert evidence.people_count == 2
    assert evidence.person_without_face is False


def test_evidence_extracts_people_count_list_fallback() -> None:
    obs = VisionObservation(
        detected=True,
        user_present=False,
        desk_active=False,
        computer_work_likely=False,
        on_phone_likely=False,
        studying_likely=False,
        confidence=0.5,
        captured_at=1.0,
        labels=(),
        metadata={
            "perception": {
                "faces": [],
                "people": [{"id": 1}, {"id": 2}],
            }
        },
    )
    evidence = FocusVisionObservationReader().read(obs)
    assert evidence.people_count == 2
    assert evidence.face_count == 0
    assert evidence.person_without_face is True


# ---------------------------------------------------------------------------
# New tests per safety review
# ---------------------------------------------------------------------------

def test_blocked_scan_stays_away_pending_scan_not_confirmed() -> None:
    service = FocusVisionSentinelService(
        vision_backend=_mock_vision_backend(),
        config=_fast_config(absence_pending_scan_after_seconds=5.0, pan_tilt_scan_enabled=False),
    )
    service._micro_scan_state = "blocked"
    result = _tick_with_snapshot(service, FocusVisionState.ABSENT, stable_seconds=15.0, now=100.0)
    assert result.current_state == FocusVisionState.AWAY_PENDING_SCAN, (
        "blocked scan must never become away_confirmed"
    )


def test_missing_pan_tilt_backend_stays_away_pending_scan() -> None:
    service = FocusVisionSentinelService(
        vision_backend=_mock_vision_backend(),
        config=_fast_config(absence_pending_scan_after_seconds=5.0, pan_tilt_scan_enabled=True),
        pan_tilt_backend=None,
    )
    result = _tick_with_snapshot(service, FocusVisionState.ABSENT, stable_seconds=15.0, now=100.0)
    assert result.current_state == FocusVisionState.AWAY_PENDING_SCAN
    assert service._micro_scan_blocked_reason == "pan_tilt_backend_missing"


def test_completed_scan_not_found_becomes_away_confirmed() -> None:
    service = FocusVisionSentinelService(
        vision_backend=_mock_vision_backend(),
        config=_fast_config(absence_pending_scan_after_seconds=5.0),
    )
    service._micro_scan_state = "not_found"
    result = _tick_with_snapshot(service, FocusVisionState.ABSENT, stable_seconds=15.0, now=100.0)
    assert result.current_state == FocusVisionState.AWAY_CONFIRMED


def test_completed_scan_found_reverts_to_absent() -> None:
    service = FocusVisionSentinelService(
        vision_backend=_mock_vision_backend(),
        config=_fast_config(absence_pending_scan_after_seconds=5.0),
    )
    service._micro_scan_state = "found"
    result = _tick_with_snapshot(service, FocusVisionState.ABSENT, stable_seconds=15.0, now=100.0)
    assert result.current_state == FocusVisionState.ABSENT
    assert service._micro_scan_state == "idle"


def test_reminder_does_not_fire_for_away_pending_scan() -> None:
    config = _fast_config()
    policy = FocusVisionReminderPolicy(config=config)
    policy.start_session(started_at=0.0)
    now = 100.0
    snapshot = FocusVisionStateSnapshot(
        current_state=FocusVisionState.AWAY_PENDING_SCAN,
        stable_seconds=5.0,
        state_started_at=now - 5.0,
        updated_at=now,
        decision=FocusVisionDecision(FocusVisionState.AWAY_PENDING_SCAN, 0.8, ("test",), now, FocusVisionEvidence()),
    )
    reminder = policy.evaluate(snapshot, language="en", now=now)
    assert reminder is None, "reminder must not fire when scan is pending/blocked"


def test_absent_state_alone_does_not_trigger_reminder() -> None:
    config = _fast_config()
    policy = FocusVisionReminderPolicy(config=config)
    policy.start_session(started_at=0.0)
    now = 100.0
    snapshot = FocusVisionStateSnapshot(
        current_state=FocusVisionState.ABSENT,
        stable_seconds=30.0,
        state_started_at=now - 30.0,
        updated_at=now,
        decision=FocusVisionDecision(FocusVisionState.ABSENT, 0.75, ("no_active_presence",), now, FocusVisionEvidence()),
    )
    reminder = policy.evaluate(snapshot, language="en", now=now)
    assert reminder is None, "ABSENT alone must not trigger reminder — only AWAY_CONFIRMED after real scan"


def test_run_micro_scan_blocked_when_no_movement_executed() -> None:
    pan_tilt = MagicMock()
    pan_tilt.move_delta.return_value = {"movement_executed": False, "ok": False}
    pan_tilt.center.return_value = {"ok": True}
    backend = _mock_vision_backend(_observation(people_count=0, face_count=0))
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_fast_config(pan_tilt_scan_enabled=True),
        pan_tilt_backend=pan_tilt,
    )
    service._run_micro_scan()
    assert service._micro_scan_result == "blocked", (
        "scan result must be blocked when hardware did not execute movement"
    )


def test_study_activity_without_person_does_not_mark_present() -> None:
    obs = _observation(presence=False, desk=True, study=True, computer=True, people_count=0, face_count=0)
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state != FocusVisionState.ON_TASK
    assert decision.state != FocusVisionState.PROBABLY_PRESENT


# ---------------------------------------------------------------------------
# Tests: YOLO person fallback and phone bridge (10 new tests)
# ---------------------------------------------------------------------------

def test_yolo_person_fallback_evidence_fields() -> None:
    obs = _observation(face_count=0, people_count=0, labels=("object:person",))
    evidence = FocusVisionObservationReader().read(obs)
    assert evidence.people_count == 1
    assert evidence.face_count == 0
    assert evidence.person_without_face is True
    assert evidence.yolo_person_count == 1
    assert evidence.people_count_source == "yolo_person_fallback"


def test_yolo_person_fallback_produces_probably_present() -> None:
    obs = _observation(face_count=0, people_count=0, labels=("object:person",))
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state == FocusVisionState.PROBABLY_PRESENT, (
        f"Expected PROBABLY_PRESENT, got {decision.state} — YOLO person must bridge into people_count"
    )
    assert "person_without_face" in decision.reasons


def test_bottle_only_not_probably_present() -> None:
    obs = _observation(face_count=0, people_count=0, labels=("object:bottle",))
    evidence = FocusVisionObservationReader().read(obs)
    assert evidence.people_count == 0
    assert evidence.yolo_person_count == 0
    assert evidence.person_without_face is False
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state != FocusVisionState.PROBABLY_PRESENT


def test_desk_objects_without_yolo_person_is_absent() -> None:
    obs = _observation(
        presence=False, desk=False, computer=False, study=False,
        face_count=0, people_count=0,
        labels=("object:laptop", "object:keyboard", "object:cup"),
    )
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state == FocusVisionState.ABSENT, (
        f"Expected ABSENT when only desk objects detected (no person), got {decision.state}"
    )


def test_yolo_phone_and_person_is_phone_distraction() -> None:
    obs = _observation(
        presence=False, phone=False,
        face_count=0, people_count=0,
        labels=("object:person", "object:cell phone"),
    )
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state == FocusVisionState.PHONE_DISTRACTION, (
        f"Expected PHONE_DISTRACTION, got {decision.state} — YOLO phone+person must bridge"
    )
    assert "hard_phone_evidence" in decision.reasons


def test_yolo_phone_without_person_is_not_phone_distraction() -> None:
    obs = _observation(
        presence=False, phone=False,
        face_count=0, people_count=0,
        labels=("object:cell phone",),
    )
    evidence = FocusVisionObservationReader().read(obs)
    assert evidence.phone_object_detected is False, (
        "phone_object_detected must be False when no person evidence is present"
    )
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state != FocusVisionState.PHONE_DISTRACTION


def test_yolo_person_evidence_people_count_source() -> None:
    obs = _observation(face_count=0, people_count=0, labels=("object:person", "object:bottle"))
    evidence = FocusVisionObservationReader().read(obs)
    assert evidence.people_count_source == "yolo_person_fallback"
    assert evidence.yolo_person_count == 1


def test_raw_face_path_people_count_source_is_raw() -> None:
    obs = _observation(face_count=2, people_count=2, labels=())
    evidence = FocusVisionObservationReader().read(obs)
    assert evidence.people_count_source == "raw_people"
    assert evidence.people_count == 2
    assert evidence.yolo_person_count == 0


def test_yolo_fallback_skipped_when_raw_face_present() -> None:
    obs = _observation(face_count=1, people_count=1, labels=("object:person",))
    evidence = FocusVisionObservationReader().read(obs)
    assert evidence.people_count_source == "raw_people", (
        "YOLO fallback must not activate when raw face/people are already present"
    )
    assert evidence.people_count == 1
    assert evidence.yolo_person_count == 1


def test_phone_object_detected_false_when_no_person() -> None:
    obs = _observation(face_count=0, people_count=0, labels=("object:cell phone", "object:laptop"))
    evidence = FocusVisionObservationReader().read(obs)
    assert evidence.phone_object_detected is False


# ---------------------------------------------------------------------------
# Tests: Phone and away-soft reminder timing (11 new tests)
# ---------------------------------------------------------------------------

def _reminder_policy(config: FocusVisionConfig | None = None, started_at: float = 0.0) -> FocusVisionReminderPolicy:
    policy = FocusVisionReminderPolicy(config=config or _fast_config())
    policy.start_session(started_at=started_at)
    return policy


def _snapshot_in_state(state: FocusVisionState, stable_seconds: float, now: float = 100.0) -> FocusVisionStateSnapshot:
    return FocusVisionStateSnapshot(
        current_state=state,
        stable_seconds=stable_seconds,
        state_started_at=now - stable_seconds,
        updated_at=now,
        decision=FocusVisionDecision(state, 0.8, ("test",), now, FocusVisionEvidence()),
    )


def test_phone_distraction_state_fires_without_timer_delay() -> None:
    config = _fast_config(phone_warning_after_seconds=30.0)
    policy = _reminder_policy(config)
    snap = _snapshot_in_state(FocusVisionState.PHONE_DISTRACTION, stable_seconds=0.0)
    reminder = policy.evaluate(snap, language="en", now=100.0)
    assert reminder is not None
    assert reminder.kind == FocusVisionReminderKind.PHONE_DISTRACTION


def test_phone_distraction_at_threshold_fires_reminder() -> None:
    config = _fast_config(phone_warning_after_seconds=30.0)
    policy = _reminder_policy(config)
    snap = _snapshot_in_state(FocusVisionState.PHONE_DISTRACTION, stable_seconds=30.0)
    reminder = policy.evaluate(snap, language="en", now=100.0)
    assert reminder is not None
    assert reminder.kind == FocusVisionReminderKind.PHONE_DISTRACTION


def test_phone_reminder_cooldown_prevents_second_reminder() -> None:
    config = _fast_config(phone_warning_after_seconds=5.0, warning_cooldown_seconds=120.0)
    policy = _reminder_policy(config)
    snap = _snapshot_in_state(FocusVisionState.PHONE_DISTRACTION, stable_seconds=10.0, now=100.0)
    first = policy.evaluate(snap, language="en", now=100.0)
    assert first is not None
    # Second attempt 60 seconds later — still within 120s cooldown
    snap2 = _snapshot_in_state(FocusVisionState.PHONE_DISTRACTION, stable_seconds=70.0, now=160.0)
    second = policy.evaluate(snap2, language="en", now=160.0)
    assert second is None, "cooldown must prevent second phone reminder within 120 seconds"


def test_away_pending_scan_under_threshold_no_reminder() -> None:
    config = _fast_config(away_soft_reminder_after_seconds=60.0)
    policy = _reminder_policy(config)
    snap = _snapshot_in_state(FocusVisionState.AWAY_PENDING_SCAN, stable_seconds=50.0)
    assert policy.evaluate(snap, language="en", now=100.0) is None


def test_away_pending_scan_over_threshold_fires_soft_reminder() -> None:
    config = _fast_config(away_soft_reminder_after_seconds=60.0)
    policy = _reminder_policy(config)
    snap = _snapshot_in_state(FocusVisionState.AWAY_PENDING_SCAN, stable_seconds=65.0)
    reminder = policy.evaluate(snap, language="en", now=100.0)
    assert reminder is not None
    assert reminder.kind == FocusVisionReminderKind.AWAY_SOFT
    assert "come back" in reminder.text.lower() or "wróć" in reminder.text.lower()


def test_away_soft_reminder_text_is_uncertainty_aware() -> None:
    config = _fast_config(away_soft_reminder_after_seconds=60.0)
    policy = _reminder_policy(config)
    snap = _snapshot_in_state(FocusVisionState.AWAY_PENDING_SCAN, stable_seconds=65.0)
    reminder_en = policy.evaluate(snap, language="en", now=100.0)
    assert reminder_en is not None
    assert "please" in reminder_en.text.lower() or "when you can" in reminder_en.text.lower(), (
        "away_soft text must be gentle/uncertain, not commanding"
    )
    policy2 = _reminder_policy(config)
    reminder_pl = policy2.evaluate(snap, language="pl", now=100.0)
    assert reminder_pl is not None
    assert "proszę" in reminder_pl.text.lower() or "kiedy możesz" in reminder_pl.text.lower()


def test_away_soft_reminder_does_not_set_away_confirmed() -> None:
    service = FocusVisionSentinelService(
        vision_backend=_mock_vision_backend(),
        config=_fast_config(absence_pending_scan_after_seconds=5.0, pan_tilt_scan_enabled=False),
    )
    result = _tick_with_snapshot(service, FocusVisionState.ABSENT, stable_seconds=30.0, now=100.0)
    assert result.current_state != FocusVisionState.AWAY_CONFIRMED, (
        "away_soft path must never produce AWAY_CONFIRMED without a completed scan"
    )
    assert result.current_state == FocusVisionState.AWAY_PENDING_SCAN


def test_yolo_person_present_means_no_away_pending_state() -> None:
    obs = _observation(face_count=0, people_count=0, labels=("object:person",))
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state == FocusVisionState.PROBABLY_PRESENT, (
        "YOLO person → PROBABLY_PRESENT, never ABSENT/AWAY_PENDING_SCAN → no away reminder"
    )
    assert decision.state != FocusVisionState.ABSENT
    assert decision.state != FocusVisionState.AWAY_PENDING_SCAN


def test_face_hidden_yolo_person_visible_no_away_state() -> None:
    obs = _observation(
        presence=False, desk=False,
        face_count=0, people_count=0,
        labels=("object:person",),
    )
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state not in (FocusVisionState.ABSENT, FocusVisionState.AWAY_PENDING_SCAN), (
        "face hidden but YOLO person visible → PROBABLY_PRESENT, not an away state"
    )


def test_phone_object_alone_no_phone_distraction_state() -> None:
    obs = _observation(
        presence=False, phone=False,
        face_count=0, people_count=0,
        labels=("object:cell phone",),
    )
    decision = FocusVisionDecisionEngine().decide(obs)
    assert decision.state != FocusVisionState.PHONE_DISTRACTION, (
        "phone object on empty desk (no person evidence) must not trigger PHONE_DISTRACTION"
    )


def test_away_confirmed_path_unchanged() -> None:
    config = _fast_config(absence_warning_after_seconds=5.0)
    policy = _reminder_policy(config)
    snap = _snapshot_in_state(FocusVisionState.AWAY_CONFIRMED, stable_seconds=10.0)
    reminder = policy.evaluate(snap, language="en", now=100.0)
    assert reminder is not None
    assert reminder.kind == FocusVisionReminderKind.ABSENCE


def test_no_pan_tilt_movement_in_away_soft_path() -> None:
    pan_tilt = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=_mock_vision_backend(),
        config=_fast_config(
            absence_pending_scan_after_seconds=5.0,
            pan_tilt_scan_enabled=False,
            away_soft_reminder_after_seconds=60.0,
        ),
        pan_tilt_backend=pan_tilt,
    )
    _tick_with_snapshot(service, FocusVisionState.ABSENT, stable_seconds=80.0, now=100.0)
    pan_tilt.move_delta.assert_not_called()
    pan_tilt.center.assert_not_called()
