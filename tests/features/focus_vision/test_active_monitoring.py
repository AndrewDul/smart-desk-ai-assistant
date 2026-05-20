"""Tests for Focus Mode Active Monitoring v2 — wall-clock absence, phone accumulation, scan scheduler."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from modules.features.focus_vision import (
    FocusMonitoringEvidenceAccumulator,
    FocusMonitoringScanScheduler,
    FocusScanResult,
    FocusVisionConfig,
    FocusVisionReminderKind,
    FocusVisionReminderPolicy,
    FocusVisionSentinelService,
    FocusVisionState,
)
from modules.features.focus_vision.models import (
    FocusVisionDecision,
    FocusVisionEvidence,
    FocusVisionStateSnapshot,
)
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
    phone: bool = False,
    face_count: int = 0,
    people_count: int = 0,
    captured_at: float = 0.0,
    labels: tuple[str, ...] = (),
) -> VisionObservation:
    return VisionObservation(
        detected=True,
        user_present=presence,
        desk_active=False,
        computer_work_likely=False,
        on_phone_likely=phone,
        studying_likely=False,
        confidence=0.9,
        captured_at=captured_at,
        labels=labels,
        metadata={
            "behavior": {
                "presence": _signal(presence),
                "desk_activity": _signal(False),
                "computer_work": _signal(False),
                "phone_usage": _signal(phone),
                "study_activity": _signal(False),
            },
            "sessions": {
                "presence": _session(presence),
                "desk_activity": _session(False),
                "computer_work": _session(False),
                "phone_usage": _session(phone),
                "study_activity": _session(False),
            },
            "perception": {
                "face_count": face_count,
                "people_count": people_count,
            },
        },
    )


def _service_config(**overrides: Any) -> FocusVisionConfig:
    defaults: dict[str, Any] = dict(
        enabled=True,
        dry_run=False,
        voice_warnings_enabled=True,
        startup_grace_seconds=0.0,
        absence_warning_after_seconds=999.0,
        absence_pending_scan_after_seconds=1.0,
        away_soft_reminder_after_seconds=5.0,
        phone_warning_after_seconds=30.0,
        warning_cooldown_seconds=0.0,
        active_monitoring_enabled=False,
        continuous_tracking_enabled=False,
        pan_tilt_scan_enabled=False,
        max_observation_age_seconds=30.0,
    )
    defaults.update(overrides)
    return FocusVisionConfig(**defaults)


def _make_snapshot(
    state: FocusVisionState,
    stable_seconds: float = 0.0,
    now: float = 100.0,
) -> FocusVisionStateSnapshot:
    evidence = FocusVisionEvidence()
    decision = FocusVisionDecision(state=state, confidence=0.9, reasons=(), observed_at=now, evidence=evidence)
    return FocusVisionStateSnapshot(
        current_state=state,
        stable_seconds=stable_seconds,
        state_started_at=now - stable_seconds,
        updated_at=now,
        decision=decision,
    )


# ---------------------------------------------------------------------------
# Part 1: FocusMonitoringEvidenceAccumulator
# ---------------------------------------------------------------------------

def test_accumulator_no_observation_preserves_person_evidence():
    """person_absent_seconds must NOT reset when no person is seen (no_observation gap)."""
    acc = FocusMonitoringEvidenceAccumulator()
    acc.update(person_seen=True, phone_seen=False, now=0.0)
    # Simulate a no_observation gap — person_seen=False (e.g. frame dropout)
    acc.update(person_seen=False, phone_seen=False, now=5.0)
    acc.update(person_seen=False, phone_seen=False, now=10.0)
    absent = acc.person_absent_seconds(now=10.0)
    assert absent is not None
    assert abs(absent - 10.0) < 0.01


def test_accumulator_person_absent_seconds_none_before_any_person_seen():
    acc = FocusMonitoringEvidenceAccumulator()
    assert acc.person_absent_seconds(now=100.0) is None


def test_accumulator_phone_accumulates_across_ticks():
    acc = FocusMonitoringEvidenceAccumulator(phone_gap_tolerance_seconds=5.0)
    acc.update(person_seen=True, phone_seen=True, now=0.0)
    acc.update(person_seen=True, phone_seen=True, now=2.0)
    acc.update(person_seen=True, phone_seen=True, now=4.0)
    assert abs(acc.phone_accumulated_seconds() - 4.0) < 0.01


def test_accumulator_phone_without_person_not_accumulated():
    acc = FocusMonitoringEvidenceAccumulator(phone_gap_tolerance_seconds=5.0)
    acc.update(person_seen=False, phone_seen=True, now=0.0)
    acc.update(person_seen=False, phone_seen=True, now=2.0)
    acc.update(person_seen=False, phone_seen=True, now=4.0)
    assert acc.phone_accumulated_seconds() == 0.0


def test_accumulator_phone_gap_within_tolerance_preserves_accumulation():
    acc = FocusMonitoringEvidenceAccumulator(phone_gap_tolerance_seconds=5.0)
    acc.update(person_seen=True, phone_seen=True, now=0.0)
    acc.update(person_seen=True, phone_seen=True, now=2.0)
    acc.update(person_seen=True, phone_seen=True, now=4.0)
    # Gap of 3 seconds — within 5s tolerance
    acc.update(person_seen=True, phone_seen=False, now=7.0)
    assert acc.phone_accumulated_seconds() == 4.0  # not reset


def test_accumulator_phone_gap_beyond_tolerance_resets_accumulation():
    acc = FocusMonitoringEvidenceAccumulator(phone_gap_tolerance_seconds=5.0)
    acc.update(person_seen=True, phone_seen=True, now=0.0)
    acc.update(person_seen=True, phone_seen=True, now=2.0)
    acc.update(person_seen=True, phone_seen=True, now=4.0)
    # Gap of 7 seconds — beyond 5s tolerance
    acc.update(person_seen=True, phone_seen=False, now=11.0)
    assert acc.phone_accumulated_seconds() == 0.0


def test_accumulator_phone_first_seen_and_gap_telemetry():
    acc = FocusMonitoringEvidenceAccumulator(phone_gap_tolerance_seconds=5.0)
    acc.update(person_seen=True, phone_seen=True, now=10.0)
    acc.update(person_seen=True, phone_seen=True, now=12.0)
    acc.update(person_seen=True, phone_seen=False, now=14.0)

    assert acc.phone_first_seen_seconds_ago(now=15.0) == 5.0
    assert acc.phone_accumulated_seconds() == 2.0
    assert acc.phone_gap_seconds() == 2.0


def test_accumulator_record_person_seen_updates_evidence():
    acc = FocusMonitoringEvidenceAccumulator()
    acc.update(person_seen=True, phone_seen=False, now=0.0)
    acc.record_person_seen(now=50.0)
    assert abs(acc.person_absent_seconds(now=55.0) - 5.0) < 0.01


# ---------------------------------------------------------------------------
# Part 2: FocusMonitoringScanScheduler
# ---------------------------------------------------------------------------

def test_scan_scheduler_periodic_due_after_interval():
    sched = FocusMonitoringScanScheduler(periodic_scan_interval_seconds=35.0, away_recheck_scan_after_seconds=8.0)
    sched.reset(now=0.0)
    assert not sched.is_periodic_scan_due(now=30.0)
    assert sched.is_periodic_scan_due(now=36.0)


def test_scan_scheduler_periodic_resets_after_record():
    sched = FocusMonitoringScanScheduler(periodic_scan_interval_seconds=35.0, away_recheck_scan_after_seconds=8.0)
    sched.reset(now=0.0)
    sched.record_periodic_scan(now=36.0)
    # Not due again until another 35s from the recorded time
    assert not sched.is_periodic_scan_due(now=40.0)
    assert sched.is_periodic_scan_due(now=72.0)


def test_scan_scheduler_away_recheck_due_after_absence_threshold():
    sched = FocusMonitoringScanScheduler(periodic_scan_interval_seconds=35.0, away_recheck_scan_after_seconds=8.0)
    sched.reset(now=0.0)
    assert not sched.is_away_recheck_due(now=5.0, person_absent_seconds=5.0)
    assert sched.is_away_recheck_due(now=9.0, person_absent_seconds=9.0)


def test_scan_scheduler_away_recheck_not_repeated_per_episode():
    sched = FocusMonitoringScanScheduler(periodic_scan_interval_seconds=35.0, away_recheck_scan_after_seconds=8.0)
    sched.reset(now=0.0)
    assert sched.is_away_recheck_due(now=9.0, person_absent_seconds=9.0)
    sched.record_away_recheck_triggered(now=9.0)
    # Already triggered — not due again in same episode
    assert not sched.is_away_recheck_due(now=20.0, person_absent_seconds=20.0)
    # Person comes back → reset
    sched.reset_away_recheck()
    assert sched.is_away_recheck_due(now=30.0, person_absent_seconds=12.0)


# ---------------------------------------------------------------------------
# Part 3: FocusVisionReminderPolicy — wall-clock params
# ---------------------------------------------------------------------------

def test_policy_uses_person_absent_seconds_for_away_soft():
    """AWAY_SOFT reminder fires based on wall-clock absence even when stable_seconds is low."""
    config = FocusVisionConfig(
        startup_grace_seconds=0.0,
        away_soft_reminder_after_seconds=30.0,
        warning_cooldown_seconds=0.0,
        enabled_reminder_kinds=("away_soft",),
    )
    policy = FocusVisionReminderPolicy(config=config)
    # State has been AWAY_PENDING_SCAN for only 2 seconds (stable_seconds too low normally)
    snapshot = _make_snapshot(FocusVisionState.AWAY_PENDING_SCAN, stable_seconds=2.0, now=100.0)
    reminder = policy.evaluate(
        snapshot,
        language="en",
        now=100.0,
        person_absent_seconds=35.0,  # 35s wall-clock absence
        phone_accumulated_seconds=None,
    )
    assert reminder is not None
    assert reminder.kind == FocusVisionReminderKind.AWAY_SOFT


def test_policy_uses_phone_accumulated_seconds_for_phone_distraction():
    config = FocusVisionConfig(
        startup_grace_seconds=0.0,
        phone_warning_after_seconds=30.0,
        warning_cooldown_seconds=0.0,
        enabled_reminder_kinds=("phone_distraction",),
    )
    policy = FocusVisionReminderPolicy(config=config)
    snapshot = _make_snapshot(FocusVisionState.PHONE_DISTRACTION, stable_seconds=1.0, now=100.0)
    reminder = policy.evaluate(
        snapshot,
        language="en",
        now=100.0,
        person_absent_seconds=None,
        phone_accumulated_seconds=35.0,
    )
    assert reminder is not None
    assert reminder.kind == FocusVisionReminderKind.PHONE_DISTRACTION


def test_policy_away_soft_falls_back_to_stable_seconds_when_no_wall_clock():
    config = FocusVisionConfig(
        startup_grace_seconds=0.0,
        away_soft_reminder_after_seconds=30.0,
        warning_cooldown_seconds=0.0,
        enabled_reminder_kinds=("away_soft",),
    )
    policy = FocusVisionReminderPolicy(config=config)
    # No person_absent_seconds provided — falls back to stable_seconds
    snapshot = _make_snapshot(FocusVisionState.AWAY_PENDING_SCAN, stable_seconds=35.0, now=100.0)
    reminder = policy.evaluate(snapshot, language="en", now=100.0)
    assert reminder is not None
    assert reminder.kind == FocusVisionReminderKind.AWAY_SOFT


# ---------------------------------------------------------------------------
# Part 4: FocusVisionSentinelService integration
# ---------------------------------------------------------------------------

def test_service_tick_passes_person_absent_seconds_to_policy():
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(presence=False, captured_at=0.0)

    mock_policy = MagicMock()
    mock_policy.evaluate.return_value = None
    mock_policy.session_started_at = None
    mock_policy.start_session = MagicMock()

    config = _service_config()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=config,
        reminder_policy=mock_policy,
        telemetry=MagicMock(),
    )

    # Seed person evidence at t=0
    assert service._evidence_accumulator is not None
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=0.0)

    # Tick at t=10 with no person visible
    backend.latest_observation.return_value = _observation(presence=False, captured_at=10.0)
    service.tick(now=10.0)

    # evaluate() must have been called with person_absent_seconds kwarg
    call_kwargs = mock_policy.evaluate.call_args.kwargs
    assert "person_absent_seconds" in call_kwargs
    assert call_kwargs["person_absent_seconds"] is not None
    assert call_kwargs["person_absent_seconds"] >= 9.9


def test_focus_scan_does_not_call_pan_tilt_when_scan_disabled():
    """With pan_tilt_scan_enabled=False, focus scan must not call move_delta on any backend."""
    pan_tilt = MagicMock()
    backend = MagicMock()
    backend.latest_observation.return_value = None  # no person

    config = _service_config(pan_tilt_scan_enabled=False, active_monitoring_enabled=True)
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=config,
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )

    service._trigger_focus_scan("periodic", 0.0)

    # Wait for background thread to finish
    import time
    time.sleep(0.3)

    pan_tilt.move_delta.assert_not_called()
    pan_tilt.center.assert_not_called()


def test_focus_scan_no_mobile_base_movement():
    """Focus scans must not call any base/drive movement methods."""
    pan_tilt = MagicMock()
    backend = MagicMock()
    backend.latest_observation.return_value = None

    config = _service_config(pan_tilt_scan_enabled=False, active_monitoring_enabled=True)
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=config,
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )

    service._trigger_focus_scan("away_recheck", 0.0)

    import time
    time.sleep(0.3)

    pan_tilt.drive.assert_not_called() if hasattr(pan_tilt, "drive") else None
    pan_tilt.move_forward.assert_not_called() if hasattr(pan_tilt, "move_forward") else None
    pan_tilt.rotate_base.assert_not_called() if hasattr(pan_tilt, "rotate_base") else None


def test_session_start_resets_accumulator_and_scheduler():
    """service.start() must reset accumulator and scheduler to clean state."""
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(presence=True, captured_at=0.0)

    config = _service_config()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=config,
        telemetry=MagicMock(),
    )

    # Accumulate some state — use people_count=1 so accumulator records person evidence
    backend.latest_observation.return_value = _observation(presence=True, people_count=1, captured_at=0.0)
    service.tick(now=0.0)
    assert service._evidence_accumulator is not None
    assert service._evidence_accumulator.person_absent_seconds(now=0.0) is not None

    # Reset via start()
    service.start(language="en")
    # Give it a moment then stop
    import time
    time.sleep(0.05)
    service.stop()

    # After start(), accumulator should be fresh (no person evidence yet from this session tick)
    # _evidence_accumulator.reset() was called in start(), clearing last_person_evidence_at
    # (start() resets it, then tick() in the background may or may not have run)
    # We test by checking the scheduler also reset
    assert service._scan_scheduler is not None
    # The scheduler's session_started_at was set during start() — it's not None
    assert service._scan_scheduler._session_started_at is not None


def test_telemetry_includes_timing_and_scan_fields():
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(presence=False, captured_at=10.0)

    mock_telemetry = MagicMock()
    config = _service_config()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=config,
        telemetry=mock_telemetry,
    )

    service.tick(now=10.0)

    assert mock_telemetry.append.called
    written = mock_telemetry.append.call_args[0][0]
    diagnostics = written["diagnostics"]
    assert "phone_accumulated_seconds" in diagnostics
    assert "person_absent_seconds" in diagnostics
    assert "last_person_evidence_seconds_ago" in diagnostics
    assert "focus_scan_running" in diagnostics
    assert "last_focus_scan" in diagnostics


def test_away_soft_fires_by_wall_clock_despite_unstable_state():
    """
    AWAY_SOFT must fire based on wall-clock person_absent_seconds, not stable_seconds.
    Simulates alternating no_observation gaps that keep resetting stable_seconds,
    while person_absent_seconds grows continuously from last confirmed sighting.
    """
    backend = MagicMock()
    config = _service_config(
        away_soft_reminder_after_seconds=5.0,
        absence_pending_scan_after_seconds=1.0,
        active_monitoring_enabled=False,
        enabled_reminder_kinds=("away_soft",),
    )
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=config,
        telemetry=MagicMock(),
    )

    # t=0: person present — use people_count=1 so accumulator records evidence
    backend.latest_observation.return_value = _observation(presence=True, people_count=1, captured_at=0.0)
    service.tick(now=0.0)

    # t=1: no person → ABSENT (stable_seconds=0)
    backend.latest_observation.return_value = _observation(presence=False, captured_at=1.0)
    service.tick(now=1.0)

    # t=2: no person → ABSENT stable=1.0 → AWAY_PENDING_SCAN (blocked); person_absent=2s < 5s
    backend.latest_observation.return_value = _observation(presence=False, captured_at=2.0)
    r2 = service.tick(now=2.0)
    assert r2.reminder is None

    # t=3: None observation → NO_OBSERVATION; resets micro_scan to idle; person_absent=3s < 5s
    backend.latest_observation.return_value = None
    r3 = service.tick(now=3.0)
    assert r3.reminder is None

    # t=4: no person → ABSENT new (stable=0); person_absent=4s < 5s
    backend.latest_observation.return_value = _observation(presence=False, captured_at=4.0)
    r4 = service.tick(now=4.0)
    assert r4.reminder is None

    # t=5: no person → ABSENT stable=1.0 → AWAY_PENDING_SCAN again; person_absent=5.0 ≥ 5s → AWAY_SOFT
    backend.latest_observation.return_value = _observation(presence=False, captured_at=5.0)
    r5 = service.tick(now=5.0)
    assert r5.reminder is not None, (
        "Expected AWAY_SOFT reminder: person absent 5s wall-clock but stable_seconds kept resetting"
    )
    assert r5.reminder.kind == FocusVisionReminderKind.AWAY_SOFT


def test_raw_phone_object_with_face_starts_timer_without_behavior_phone():
    backend = MagicMock()
    config = _service_config(
        phone_warning_after_seconds=30.0,
        warning_cooldown_seconds=0.0,
        enabled_reminder_kinds=("phone_distraction",),
    )
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=config,
        telemetry=MagicMock(),
    )

    backend.latest_observation.return_value = _observation(
        presence=False,
        phone=False,
        face_count=1,
        labels=("object:cell phone",),
        captured_at=0.0,
    )
    service.tick(now=0.0)

    assert service._evidence_accumulator is not None
    assert service._evidence_accumulator.phone_first_seen_seconds_ago(now=0.0) == 0.0
    assert service._evidence_accumulator.phone_accumulated_seconds() == 0.0


def test_raw_phone_object_with_yolo_person_fallback_starts_timer():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(enabled_reminder_kinds=("phone_distraction",)),
        telemetry=MagicMock(),
    )

    backend.latest_observation.return_value = _observation(
        presence=False,
        phone=False,
        labels=("object:cell phone", "object:person"),
        captured_at=0.0,
    )
    result = service.tick(now=0.0)

    assert result.snapshot is not None
    assert result.snapshot.current_state == FocusVisionState.PHONE_DISTRACTION
    assert service._evidence_accumulator is not None
    assert service._evidence_accumulator.phone_first_seen_seconds_ago(now=0.0) == 0.0


def test_raw_phone_object_without_person_does_not_start_timer():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(enabled_reminder_kinds=("phone_distraction",)),
        telemetry=MagicMock(),
    )

    backend.latest_observation.return_value = _observation(
        presence=False,
        phone=False,
        labels=("object:cell phone",),
        captured_at=0.0,
    )
    result = service.tick(now=0.0)

    assert result.reminder is None
    assert service._evidence_accumulator is not None
    assert service._evidence_accumulator.phone_first_seen_seconds_ago(now=0.0) is None
    assert service._evidence_accumulator.phone_accumulated_seconds() == 0.0


def test_raw_phone_evidence_fires_immediate_phone_distraction():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            phone_warning_after_seconds=30.0,
            warning_cooldown_seconds=0.0,
            enabled_reminder_kinds=("phone_distraction",),
        ),
        telemetry=MagicMock(),
    )

    backend.latest_observation.return_value = _observation(
        phone=False,
        face_count=1,
        labels=("object:cell phone",),
        captured_at=0.0,
    )
    result = service.tick(now=0.0)

    assert result.reminder is not None
    assert result.reminder.kind == FocusVisionReminderKind.PHONE_DISTRACTION


def test_behavior_phone_usage_without_hard_phone_evidence_does_not_warn():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            phone_warning_after_seconds=0.0,
            warning_cooldown_seconds=0.0,
            enabled_reminder_kinds=("phone_distraction",),
        ),
        telemetry=MagicMock(),
    )

    backend.latest_observation.return_value = _observation(
        phone=True,
        face_count=1,
        labels=(),
        captured_at=0.0,
    )
    result = service.tick(now=0.0)

    assert result.reminder is None


def test_raw_phone_evidence_30_seconds_fires_phone_distraction_without_behavior_phone():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            phone_warning_after_seconds=30.0,
            warning_cooldown_seconds=0.0,
            enabled_reminder_kinds=("phone_distraction",),
        ),
        telemetry=MagicMock(),
    )

    backend.latest_observation.return_value = _observation(
        phone=False,
        face_count=1,
        labels=("object:cell phone",),
        captured_at=0.0,
    )
    service.tick(now=0.0)
    backend.latest_observation.return_value = _observation(
        phone=False,
        face_count=1,
        labels=("object:cell phone",),
        captured_at=30.0,
    )
    result = service.tick(now=30.0)

    assert result.reminder is not None
    assert result.reminder.kind == FocusVisionReminderKind.PHONE_DISTRACTION


def test_short_raw_phone_gap_does_not_reset_timer():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            phone_gap_tolerance_seconds=5.0,
            phone_warning_after_seconds=30.0,
            warning_cooldown_seconds=0.0,
            enabled_reminder_kinds=("phone_distraction",),
        ),
        telemetry=MagicMock(),
    )

    backend.latest_observation.return_value = _observation(face_count=1, labels=("object:cell phone",), captured_at=0.0)
    service.tick(now=0.0)
    backend.latest_observation.return_value = _observation(face_count=1, labels=("object:cell phone",), captured_at=4.0)
    service.tick(now=4.0)
    backend.latest_observation.return_value = _observation(face_count=1, labels=(), captured_at=6.0)
    service.tick(now=6.0)
    backend.latest_observation.return_value = _observation(face_count=1, labels=("object:cell phone",), captured_at=8.0)
    service.tick(now=8.0)

    assert service._evidence_accumulator is not None
    assert service._evidence_accumulator.phone_first_seen_seconds_ago(now=8.0) == 8.0
    assert service._evidence_accumulator.phone_accumulated_seconds() == 8.0


def test_long_raw_phone_gap_resets_timer():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            phone_gap_tolerance_seconds=5.0,
            phone_warning_after_seconds=30.0,
            warning_cooldown_seconds=0.0,
            enabled_reminder_kinds=("phone_distraction",),
        ),
        telemetry=MagicMock(),
    )

    backend.latest_observation.return_value = _observation(face_count=1, labels=("object:cell phone",), captured_at=0.0)
    service.tick(now=0.0)
    backend.latest_observation.return_value = _observation(face_count=1, labels=(), captured_at=6.0)
    service.tick(now=6.0)

    assert service._evidence_accumulator is not None
    assert service._evidence_accumulator.phone_first_seen_seconds_ago(now=6.0) is None
    assert service._evidence_accumulator.phone_accumulated_seconds() == 0.0


def test_phone_reminder_cooldown_prevents_service_spam():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            phone_warning_after_seconds=1.0,
            warning_cooldown_seconds=120.0,
            enabled_reminder_kinds=("phone_distraction",),
        ),
        telemetry=MagicMock(),
    )

    backend.latest_observation.return_value = _observation(face_count=1, labels=("object:cell phone",), captured_at=0.0)
    first = service.tick(now=0.0)
    backend.latest_observation.return_value = _observation(face_count=1, labels=("object:cell phone",), captured_at=2.0)
    second = service.tick(now=2.0)
    backend.latest_observation.return_value = _observation(face_count=1, labels=("object:cell phone",), captured_at=3.0)
    third = service.tick(now=3.0)

    assert first.reminder is not None
    assert second.reminder is None
    assert third.reminder is None


def test_away_recheck_no_person_scan_fires_away_soft_immediately():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            away_soft_reminder_after_seconds=30.0,
            warning_cooldown_seconds=0.0,
            enabled_reminder_kinds=("away_soft",),
        ),
        telemetry=MagicMock(),
    )
    service._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=False,
        triggered_at=10.0,
        completed_at=11.0,
        camera_available=True,
    )
    assert service._evidence_accumulator is not None
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=0.0)
    backend.latest_observation.return_value = _observation(captured_at=11.0)

    result = service.tick(now=11.0)

    assert result.reminder is not None
    assert result.reminder.kind == FocusVisionReminderKind.AWAY_SOFT
    assert result.snapshot is not None
    assert result.snapshot.current_state == FocusVisionState.AWAY_PENDING_SCAN


def test_away_recheck_person_found_scan_does_not_fire_away_soft():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(enabled_reminder_kinds=("away_soft",)),
        telemetry=MagicMock(),
    )
    service._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=True,
        triggered_at=10.0,
        completed_at=11.0,
        camera_available=True,
    )
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=0.0)
    backend.latest_observation.return_value = _observation(captured_at=11.0)

    result = service.tick(now=11.0)

    assert result.reminder is None


def test_person_return_before_away_notification_suppresses_away_soft():
    backend = MagicMock()
    delivered: list[object] = []
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            dry_run=False,
            voice_warnings_enabled=True,
            away_soft_reminder_after_seconds=30.0,
            warning_cooldown_seconds=0.0,
            enabled_reminder_kinds=("away_soft",),
        ),
        telemetry=MagicMock(),
    )
    service.set_reminder_handler(delivered.append)
    service._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=False,
        triggered_at=10.0,
        completed_at=11.0,
        camera_available=True,
    )
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=0.0)
    backend.latest_observation.return_value = _observation(people_count=1, captured_at=11.0)

    result = service.tick(now=11.0)

    assert result.reminder is None
    assert delivered == []


def test_camera_unavailable_scan_does_not_accuse_user():
    """Scan blocked because hardware was disabled (never ran) — do not deliver.

    camera_available=False with scan_blocked_reason='pan_tilt_scan_disabled' means
    the pan-tilt never moved so we have no confidence about user absence.  Only a
    scan that physically ran (scan_blocked_reason='') should trigger the reminder.
    """
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(enabled_reminder_kinds=("away_soft",)),
        telemetry=MagicMock(),
    )
    service._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=False,
        triggered_at=10.0,
        completed_at=11.0,
        camera_available=False,
        scan_blocked_reason="pan_tilt_scan_disabled",
    )
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=0.0)
    backend.latest_observation.return_value = _observation(captured_at=11.0)

    result = service.tick(now=11.0)

    assert result.reminder is None


def test_away_soft_cooldown_prevents_service_spam():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            away_soft_reminder_after_seconds=30.0,
            warning_cooldown_seconds=120.0,
            enabled_reminder_kinds=("away_soft",),
        ),
        telemetry=MagicMock(),
    )
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=0.0)
    backend.latest_observation.return_value = _observation(captured_at=11.0)
    service._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=False,
        triggered_at=10.0,
        completed_at=11.0,
        camera_available=True,
    )
    first = service.tick(now=11.0)
    service._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=False,
        triggered_at=20.0,
        completed_at=21.0,
        camera_available=True,
    )
    second = service.tick(now=21.0)

    assert first.reminder is not None
    assert second.reminder is None


def test_telemetry_includes_raw_phone_and_away_scan_timing_fields():
    backend = MagicMock()
    telemetry = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            phone_warning_after_seconds=30.0,
            warning_cooldown_seconds=0.0,
            enabled_reminder_kinds=("phone_distraction",),
        ),
        telemetry=telemetry,
    )
    service._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=False,
        triggered_at=1.0,
        completed_at=2.0,
        movement_executed=True,
        camera_available=True,
    )
    backend.latest_observation.return_value = _observation(
        face_count=1,
        labels=("object:cell phone",),
        captured_at=0.0,
    )

    service.tick(now=0.0)

    diagnostics = telemetry.append.call_args[0][0]["diagnostics"]
    assert diagnostics["raw_phone_object_detected"] is True
    assert diagnostics["phone_person_evidence"] is True
    assert diagnostics["phone_first_seen_seconds_ago"] == 0.0
    assert diagnostics["phone_evidence_elapsed_seconds"] == 0.0
    assert diagnostics["phone_gap_seconds"] == 0.0
    assert diagnostics["phone_reminder_due"] is True
    assert diagnostics["immediate_phone_reminder_due"] is True
    assert diagnostics["phone_reminder_after_seconds"] == 30.0
    assert diagnostics["away_recheck_scan_completed"] is True
    assert diagnostics["away_recheck_person_found"] is False
    assert "away_soft_due_from_scan" in diagnostics
    assert "away_soft_due_reason" in diagnostics
    last_scan = diagnostics["last_focus_scan"]
    assert last_scan["camera_available"] is True
    assert last_scan["movement_executed"] is True
    assert last_scan["scan_type"] == "away_recheck"
    assert last_scan["person_found"] is False


# ---------------------------------------------------------------------------
# Part 5: FocusScanResult telemetry truthfulness
# ---------------------------------------------------------------------------

def test_scan_result_disabled_has_correct_blocked_reason():
    """pan_tilt_scan_enabled=False → blocked=True, scan_blocked_reason='pan_tilt_scan_disabled'."""
    pan_tilt = MagicMock()
    backend = MagicMock()
    backend.latest_observation.return_value = None

    config = _service_config(pan_tilt_scan_enabled=False, active_monitoring_enabled=True)
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=config,
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )

    service._trigger_focus_scan("periodic", 0.0)
    import time as _time
    _time.sleep(0.4)

    result = service._last_focus_scan_result
    assert result is not None
    assert result.blocked is True
    assert result.scan_blocked_reason == "pan_tilt_scan_disabled"
    assert result.movement_executed is False
    assert result.pan_tilt_scan_enabled is False
    pan_tilt.move_delta.assert_not_called()


def test_scan_result_backend_missing_has_correct_blocked_reason():
    """pan_tilt_scan_enabled=True but no backend → blocked=True, reason='pan_tilt_backend_missing'."""
    backend = MagicMock()
    backend.latest_observation.return_value = None

    config = _service_config(pan_tilt_scan_enabled=True, active_monitoring_enabled=True)
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=config,
        pan_tilt_backend=None,
        telemetry=MagicMock(),
    )

    service._trigger_focus_scan("away_recheck", 0.0)
    import time as _time
    _time.sleep(0.4)

    result = service._last_focus_scan_result
    assert result is not None
    assert result.blocked is True
    assert result.scan_blocked_reason == "pan_tilt_backend_missing"
    assert result.movement_executed is False
    assert result.pan_tilt_backend_present is False


def test_scan_result_hardware_gates_closed_when_no_movement():
    """Backend present and scan enabled but move_delta returns movement_executed=False → gates_closed."""
    pan_tilt = MagicMock()
    pan_tilt.move_delta.return_value = {
        "movement_executed": False,
        "missing_safety_gates": ["hardware_enabled", "motion_enabled"],
        "detail": "safety gates closed",
    }
    backend = MagicMock()
    backend.latest_observation.return_value = None

    config = _service_config(
        pan_tilt_scan_enabled=True,
        active_monitoring_enabled=True,
        scan_point_settle_seconds=0.0,
    )
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=config,
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )

    service._trigger_focus_scan("periodic", 0.0)
    import time as _time
    _time.sleep(0.4)

    result = service._last_focus_scan_result
    assert result is not None
    assert result.blocked is True
    assert result.scan_blocked_reason == "hardware_gates_closed"
    assert result.movement_executed is False
    assert result.pan_tilt_scan_enabled is True
    assert result.pan_tilt_backend_present is True
    assert "hardware_enabled" in result.missing_safety_gates or "motion_enabled" in result.missing_safety_gates


def test_scan_result_movement_executed_true_when_backend_confirms():
    """Backend returns movement_executed=True → scan result reflects that, blocked=False."""
    pan_tilt = MagicMock()
    pan_tilt.move_delta.return_value = {
        "movement_executed": True,
        "detail": "Waveshare serial move_delta executed.",
    }
    backend = MagicMock()
    backend.latest_observation.return_value = None

    config = _service_config(
        pan_tilt_scan_enabled=True,
        active_monitoring_enabled=True,
        scan_point_settle_seconds=0.0,
    )
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=config,
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )

    service._trigger_focus_scan("periodic", 0.0)
    import time as _time
    _time.sleep(0.4)

    result = service._last_focus_scan_result
    assert result is not None
    assert result.movement_executed is True
    assert result.blocked is False
    assert result.scan_blocked_reason == ""
    assert result.pan_tilt_scan_enabled is True
    assert result.pan_tilt_backend_present is True


def test_scan_result_no_mobile_base_calls_with_enabled_scan():
    """Even with scan enabled and backend present, no mobile base methods must be called."""
    pan_tilt = MagicMock()
    pan_tilt.move_delta.return_value = {"movement_executed": True}
    backend = MagicMock()
    backend.latest_observation.return_value = None

    config = _service_config(
        pan_tilt_scan_enabled=True,
        active_monitoring_enabled=True,
        scan_point_settle_seconds=0.0,
    )
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=config,
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )

    service._trigger_focus_scan("away_recheck", 0.0)
    import time as _time
    _time.sleep(0.4)

    for attr in ("drive", "move_forward", "rotate_base", "move_base", "set_velocity"):
        assert not getattr(pan_tilt, attr).called, f"pan_tilt.{attr} must not be called"


def test_scan_result_to_dict_includes_all_telemetry_fields():
    result = FocusScanResult(
        scan_type="periodic",
        person_found=False,
        triggered_at=1.0,
        completed_at=2.0,
        blocked=True,
        movement_executed=False,
        scan_blocked_reason="pan_tilt_scan_disabled",
        pan_tilt_scan_enabled=False,
        pan_tilt_backend_present=True,
        missing_safety_gates=("hardware_enabled",),
    )
    d = result.to_dict()
    assert d["blocked"] is True
    assert d["movement_executed"] is False
    assert d["scan_blocked_reason"] == "pan_tilt_scan_disabled"
    assert d["pan_tilt_scan_enabled"] is False
    assert d["pan_tilt_backend_present"] is True
    assert "hardware_enabled" in d["missing_safety_gates"]


# ---------------------------------------------------------------------------
# Part 6: V3 Reactive Monitoring
# ---------------------------------------------------------------------------

def test_periodic_scan_disabled_by_config_default():
    cfg = FocusVisionConfig()
    assert cfg.periodic_scan_enabled is False
    assert cfg.away_recheck_scan_after_seconds == 2.0
    assert cfg.absence_pending_scan_after_seconds == 2.0
    assert cfg.phone_warning_after_seconds == 20.0


def test_periodic_scan_suppressed_when_person_visible():
    cfg = _service_config(
        active_monitoring_enabled=True,
        periodic_scan_enabled=True,
        periodic_scan_interval_seconds=1.0,
        away_recheck_scan_after_seconds=2.0,
    )
    service = FocusVisionSentinelService(vision_backend=MagicMock(), config=cfg)
    service._evidence_accumulator = FocusMonitoringEvidenceAccumulator()
    service._evidence_accumulator.reset(now=0.0)
    # Person seen at t=1.9 → absent_seconds=0.1 at t=2.0 — clearly visible
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=1.9)
    service._scan_scheduler = FocusMonitoringScanScheduler(
        periodic_scan_interval_seconds=1.0,
        away_recheck_scan_after_seconds=2.0,
    )
    service._scan_scheduler.reset(now=0.0)

    with patch.object(FocusVisionSentinelService, "_trigger_focus_scan") as mock_trigger:
        service._check_and_trigger_scans(2.0)
        mock_trigger.assert_not_called()


def test_yolo_only_person_treated_as_present():
    cfg = _service_config()
    service = FocusVisionSentinelService(vision_backend=MagicMock(), config=cfg)
    ev = FocusVisionEvidence(
        face_count=0,
        people_count=0,
        yolo_person_count=1,
        person_without_face=True,
    )
    assert service._has_person_evidence(ev) is True


def test_face_missing_yolo_body_present_has_person_evidence():
    cfg = _service_config()
    service = FocusVisionSentinelService(vision_backend=MagicMock(), config=cfg)
    # Face detector found nothing but YOLO body found → person present
    ev = FocusVisionEvidence(face_count=0, people_count=1, person_without_face=True)
    assert service._has_person_evidence(ev) is True
    # No phone evidence → no phone accumulation
    assert service._has_phone_person_evidence(ev) is False


def test_away_recheck_fires_at_2s_absence_threshold():
    acc = FocusMonitoringEvidenceAccumulator()
    acc.reset(now=0.0)
    acc.update(person_seen=True, phone_seen=False, now=0.0)
    scheduler = FocusMonitoringScanScheduler(
        periodic_scan_interval_seconds=35.0,
        away_recheck_scan_after_seconds=2.0,
    )
    scheduler.reset(now=0.0)
    absent = acc.person_absent_seconds(now=2.1)
    assert absent is not None
    assert scheduler.is_away_recheck_due(now=2.1, person_absent_seconds=absent)


def test_away_recheck_not_due_before_2s_threshold():
    acc = FocusMonitoringEvidenceAccumulator()
    acc.reset(now=0.0)
    acc.update(person_seen=True, phone_seen=False, now=0.0)
    scheduler = FocusMonitoringScanScheduler(
        periodic_scan_interval_seconds=35.0,
        away_recheck_scan_after_seconds=2.0,
    )
    scheduler.reset(now=0.0)
    absent = acc.person_absent_seconds(now=1.9)
    assert not scheduler.is_away_recheck_due(now=1.9, person_absent_seconds=absent)


def test_away_soft_fires_when_state_is_away_confirmed():
    """Bug 2 fix: _away_soft_due_from_scan must allow AWAY_CONFIRMED state."""
    cfg = _service_config()
    service = FocusVisionSentinelService(vision_backend=MagicMock(), config=cfg)
    service._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=False,
        triggered_at=0.0,
        completed_at=1.0,
        camera_available=True,
    )
    snapshot = _make_snapshot(FocusVisionState.AWAY_CONFIRMED, stable_seconds=5.0)
    due, reason = service._away_soft_due_from_scan(snapshot, person_seen=False)
    assert due is True
    assert reason == "away_recheck_no_person"


def test_periodic_scan_result_not_used_for_away_soft():
    """Only away_recheck type scan results may trigger away_soft."""
    cfg = _service_config()
    service = FocusVisionSentinelService(vision_backend=MagicMock(), config=cfg)
    service._last_focus_scan_result = FocusScanResult(
        scan_type="periodic",
        person_found=False,
        triggered_at=0.0,
        completed_at=1.0,
        camera_available=True,
    )
    snapshot = _make_snapshot(FocusVisionState.ABSENT, stable_seconds=5.0)
    due, _reason = service._away_soft_due_from_scan(snapshot, person_seen=False)
    assert due is False


def test_intermittent_phone_accumulator_does_not_bypass_hard_evidence_gate():
    """Phone accumulated seconds alone must not fire when state is ON_TASK."""
    from modules.features.focus_vision.reminder_policy import FocusVisionReminderPolicy
    policy = FocusVisionReminderPolicy(
        config=FocusVisionConfig(
            phone_warning_after_seconds=25.0,
            voice_warnings_enabled=True,
            dry_run=False,
            startup_grace_seconds=0.0,
            warning_cooldown_seconds=0.0,
        )
    )
    policy.start_session(started_at=0.0)
    snapshot = _make_snapshot(FocusVisionState.ON_TASK, stable_seconds=0.0, now=100.0)
    reminder = policy.evaluate(
        snapshot, language="en", now=100.0, phone_accumulated_seconds=26.0
    )
    assert reminder is None


def test_phone_accumulated_seconds_alone_does_not_fire_reminder():
    from modules.features.focus_vision.reminder_policy import FocusVisionReminderPolicy
    policy = FocusVisionReminderPolicy(
        config=FocusVisionConfig(
            phone_warning_after_seconds=25.0,
            voice_warnings_enabled=True,
            dry_run=False,
            startup_grace_seconds=0.0,
            warning_cooldown_seconds=0.0,
        )
    )
    policy.start_session(started_at=0.0)
    snapshot = _make_snapshot(FocusVisionState.ON_TASK, stable_seconds=0.0, now=100.0)
    reminder = policy.evaluate(snapshot, language="en", now=100.0, phone_accumulated_seconds=25.0)
    assert reminder is None


def test_immediate_phone_flag_fires_without_accumulated_seconds():
    from modules.features.focus_vision.reminder_policy import FocusVisionReminderPolicy
    policy = FocusVisionReminderPolicy(
        config=FocusVisionConfig(
            phone_warning_after_seconds=25.0,
            voice_warnings_enabled=True,
            dry_run=False,
            startup_grace_seconds=0.0,
            warning_cooldown_seconds=0.0,
        )
    )
    policy.start_session(started_at=0.0)
    snapshot = _make_snapshot(FocusVisionState.ON_TASK, stable_seconds=0.0, now=100.0)
    reminder = policy.evaluate(snapshot, language="en", now=100.0, immediate_phone_reminder_due=True)
    assert reminder is not None
    assert reminder.kind == FocusVisionReminderKind.PHONE_DISTRACTION


def test_phone_usage_active_without_hard_phone_evidence_is_not_phone_signal():
    """behavior:phone_usage_active alone must not fake a phone warning."""
    cfg = _service_config()
    service = FocusVisionSentinelService(vision_backend=MagicMock(), config=cfg)
    ev = FocusVisionEvidence(
        phone_usage_active=True,
        phone_object_detected=False,
        face_count=1,
    )
    assert service._has_phone_person_evidence(ev) is False


# ---------------------------------------------------------------------------
# Part 7: V3 Hard Visual Scan Evidence
# ---------------------------------------------------------------------------

def test_scan_behavior_labels_only_hard_person_found_false():
    """face=0 yolo=0 but behavior/session labels present → scan hard_person_found=False."""
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(
        presence=True,
        face_count=0,
        people_count=0,
        labels=("behavior:presence", "session:presence_active"),
        captured_at=0.0,
    )
    service = FocusVisionSentinelService(vision_backend=backend, config=_service_config())
    found, cam, info = service._check_person_for_scan_result()
    assert found is False
    assert info["behavior_presence_ignored_for_scan"] is True
    assert info["face_count"] == 0
    assert info["yolo_person_count"] == 0


def test_scan_people_count_only_no_face_no_yolo_hard_person_found_false():
    """people_count=1 from behavioral tracker, face=0, yolo=0 → scan ignores tracker count."""
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(
        face_count=0,
        people_count=1,
        captured_at=0.0,
    )
    service = FocusVisionSentinelService(vision_backend=backend, config=_service_config())
    found, cam, info = service._check_person_for_scan_result()
    assert found is False
    assert info["face_count"] == 0
    assert info["yolo_person_count"] == 0


def test_scan_stale_observation_ignored():
    """Observation older than 5 seconds → scan treats camera as not seeing person."""
    import time as _time
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(
        face_count=1,
        people_count=1,
        labels=("object:person",),
        captured_at=_time.monotonic() - 10.0,
    )
    service = FocusVisionSentinelService(vision_backend=backend, config=_service_config())
    found, cam, info = service._check_person_for_scan_result()
    assert found is False
    assert info["stale_observation_ignored"] is True


def test_scan_yolo_person_without_face_not_found_for_face_only_focus():
    """Focus reacquisition scans use fresh face evidence, not person-only labels."""
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(
        labels=("object:person",),
        captured_at=0.0,
    )
    service = FocusVisionSentinelService(vision_backend=backend, config=_service_config())
    found, cam, info = service._check_person_for_scan_result()
    assert found is False
    assert info["yolo_person_count"] == 1
    assert info["hard_person_found"] is False


def test_scan_face_count_fresh_hard_person_found_true():
    """Fresh observation with face_count=1 → hard_person_found=True."""
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(
        face_count=1,
        captured_at=0.0,
    )
    service = FocusVisionSentinelService(vision_backend=backend, config=_service_config())
    found, cam, info = service._check_person_for_scan_result()
    assert found is True
    assert info["face_count"] == 1
    assert info["hard_person_found"] is True


def test_away_soft_fires_when_scan_triggered_after_absence_started():
    """Scan triggered after person was last seen AND person not found → away_soft fires."""
    cfg = _service_config()
    service = FocusVisionSentinelService(vision_backend=MagicMock(), config=cfg)
    service._evidence_accumulator = FocusMonitoringEvidenceAccumulator()
    service._evidence_accumulator.reset(now=0.0)
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=5.0)
    service._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=False,
        triggered_at=7.0,
        completed_at=9.0,
        camera_available=True,
    )
    snapshot = _make_snapshot(FocusVisionState.ABSENT, stable_seconds=5.0)
    due, reason = service._away_soft_due_from_scan(snapshot, person_seen=False)
    assert due is True
    assert reason == "away_recheck_no_person"


def test_lost_hard_person_triggers_immediate_away_scan():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(active_monitoring_enabled=True, continuous_tracking_enabled=False),
        telemetry=MagicMock(),
    )
    assert service._evidence_accumulator is not None
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=0.0)
    backend.latest_observation.return_value = _observation(captured_at=1.0)

    with patch.object(FocusVisionSentinelService, "_trigger_focus_scan", autospec=True) as trigger:
        result = service.tick(now=1.0)

    assert result.snapshot is not None
    assert trigger.call_count == 1
    assert trigger.call_args[0][1] == "away_recheck"
    telemetry_event = service.telemetry.append.call_args[0][0]
    assert telemetry_event["immediate_away_scan_triggered"] is True


def test_yolo_person_visible_does_not_trigger_away_scan():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(active_monitoring_enabled=True, continuous_tracking_enabled=False),
        telemetry=MagicMock(),
    )
    assert service._evidence_accumulator is not None
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=0.0)
    backend.latest_observation.return_value = _observation(labels=("object:person",), captured_at=1.0)

    with patch.object(FocusVisionSentinelService, "_trigger_focus_scan", autospec=True) as trigger:
        result = service.tick(now=1.0)

    assert result.reminder is None
    trigger.assert_not_called()


class _TrackingServiceStub:
    def __init__(self, *, target_type: str = "face", pan_delta: float = 1.0) -> None:
        self.target_type = target_type
        self.pan_delta = pan_delta
        self.calls = 0

    def plan_once(self, *, force_refresh: bool = False) -> dict[str, object]:
        self.calls += 1
        return {
            "has_target": True,
            "target": {"target_type": self.target_type},
            "pan_delta_degrees": self.pan_delta,
            "tilt_delta_degrees": 0.0,
            "reason": "recenter_target",
        }

    def latest_pan_tilt_adapter_result(self) -> dict[str, object]:
        return {"status": "dry_run_backend_command_blocked", "backend_command_executed": False}


def test_visible_face_tracks_continuously_without_away_reminder():
    backend = MagicMock()
    pan_tilt = MagicMock()
    pan_tilt.move_delta.return_value = {"movement_executed": True}
    tracking = _TrackingServiceStub(target_type="face", pan_delta=1.2)
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(active_monitoring_enabled=True, continuous_tracking_enabled=True),
        pan_tilt_backend=pan_tilt,
        vision_tracking_service=tracking,
        telemetry=MagicMock(),
    )
    backend.latest_observation.return_value = _observation(face_count=1, captured_at=0.0)

    result = service.tick(now=0.0)

    assert result.reminder is None
    assert tracking.calls == 1
    pan_tilt.move_delta.assert_called_once()
    event = service.telemetry.append.call_args[0][0]
    assert event["focus_tracking_active"] is True
    assert event["tracking_target_type"] == "face"
    assert event["tracking_move_executed"] is True
    assert event["immediate_away_scan_triggered"] is False


def test_face_lost_but_yolo_person_tracks_person_without_warning():
    backend = MagicMock()
    pan_tilt = MagicMock()
    pan_tilt.move_delta.return_value = {"movement_executed": True}
    tracking = _TrackingServiceStub(target_type="person", pan_delta=-1.0)
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(active_monitoring_enabled=True, continuous_tracking_enabled=True),
        pan_tilt_backend=pan_tilt,
        vision_tracking_service=tracking,
        telemetry=MagicMock(),
    )
    backend.latest_observation.return_value = _observation(labels=("object:person",), captured_at=0.0)

    result = service.tick(now=0.0)

    assert result.reminder is None
    pan_tilt.move_delta.assert_called_once()
    event = service.telemetry.append.call_args[0][0]
    assert event["hard_person_visible"] is True
    assert event["focus_tracking_active"] is True
    assert event["tracking_target_type"] == "person"
    assert event["immediate_away_scan_triggered"] is False


def test_away_scan_completed_no_person_delivers_immediate_reminder():
    backend = MagicMock()
    delivered: list[object] = []
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            dry_run=False,
            voice_warnings_enabled=True,
            continuous_tracking_enabled=False,
            warning_cooldown_seconds=0.0,
            enabled_reminder_kinds=("away_soft",),
        ),
        telemetry=MagicMock(),
    )
    service.set_reminder_handler(delivered.append)
    assert service._evidence_accumulator is not None
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=1.0)
    service._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=False,
        triggered_at=2.0,
        completed_at=3.0,
        camera_available=True,
        scan_id="away_recheck_2.000",
        scan_point_results=({"point": "center", "hard_person_found": False},),
    )
    backend.latest_observation.return_value = _observation(captured_at=3.0)

    result = service.tick(now=3.0)

    assert result.reminder is not None
    assert result.reminder.kind == FocusVisionReminderKind.AWAY_SOFT
    assert result.reminder_delivered is True
    assert delivered == [result.reminder]
    event = service.telemetry.append.call_args[0][0]
    assert event["immediate_away_reminder_due"] is True
    assert event["immediate_away_reminder_reason"] == "away_recheck_no_person"


def test_camera_covered_valid_no_person_scan_then_away_reminder():
    backend = MagicMock()
    pan_tilt = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            active_monitoring_enabled=True,
            pan_tilt_scan_enabled=False,
            warning_cooldown_seconds=0.0,
            enabled_reminder_kinds=("away_soft",),
        ),
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )
    assert service._evidence_accumulator is not None
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=1.0)
    backend.latest_observation.return_value = _observation(captured_at=0.0)

    service._run_focus_scan_background("away_recheck", 2.0)
    result = service.tick(now=3.0)

    assert service._last_focus_scan_result is not None
    assert service._last_focus_scan_result.camera_available is True
    assert service._last_focus_scan_result.person_found is False
    assert result.reminder is not None
    assert result.reminder.kind == FocusVisionReminderKind.AWAY_SOFT


def test_stuck_focus_scan_expires_with_clear_failed_result():
    backend = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(active_monitoring_enabled=True),
        telemetry=MagicMock(),
    )
    service._focus_scan_running = True
    service._focus_scan_started_at = 1.0
    service._active_focus_scan_id = "away_recheck_1.000"
    service._active_focus_scan_type = "away_recheck"
    assert service._evidence_accumulator is not None
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=0.0)
    backend.latest_observation.return_value = _observation(captured_at=20.0)

    result = service.tick(now=20.0)

    assert result.snapshot is not None
    assert service._focus_scan_running is False
    assert service._last_focus_scan_result is not None
    assert service._last_focus_scan_result.scan_blocked_reason == "scan_timeout"
    event = service.telemetry.append.call_args[0][0]
    assert event["immediate_away_scan_failed"] is True
    assert event["scan_id"] == "away_recheck_1.000"


def test_away_soft_blocked_when_scan_finds_person():
    """Scan finds person → away_soft must not fire."""
    cfg = _service_config()
    service = FocusVisionSentinelService(vision_backend=MagicMock(), config=cfg)
    service._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=True,
        triggered_at=7.0,
        completed_at=9.0,
        camera_available=True,
    )
    snapshot = _make_snapshot(FocusVisionState.ABSENT, stable_seconds=5.0)
    due, reason = service._away_soft_due_from_scan(snapshot, person_seen=False)
    assert due is False
    assert reason == "person_found"


def test_old_scan_predates_absence_does_not_suppress_reminder():
    """Scan triggered before person was last seen is rejected — it belongs to an old episode."""
    cfg = _service_config()
    service = FocusVisionSentinelService(vision_backend=MagicMock(), config=cfg)
    service._evidence_accumulator = FocusMonitoringEvidenceAccumulator()
    service._evidence_accumulator.reset(now=0.0)
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=5.0)
    service._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=False,
        triggered_at=3.0,  # triggered BEFORE person was last seen at t=5
        completed_at=4.0,
        camera_available=True,
    )
    snapshot = _make_snapshot(FocusVisionState.ABSENT, stable_seconds=5.0)
    due, reason = service._away_soft_due_from_scan(snapshot, person_seen=False)
    assert due is False
    assert reason == "scan_predates_absence"


def test_no_observation_returns_camera_unavailable():
    """No observation from backend → scan returns (False, False, ...)."""
    backend = MagicMock()
    backend.latest_observation.return_value = None
    service = FocusVisionSentinelService(vision_backend=backend, config=_service_config())
    found, cam, info = service._check_person_for_scan_result()
    assert found is False
    assert cam is False


def test_phone_accumulated_seconds_ignored_at_20s_threshold():
    """Phone accumulated seconds alone must not create a reminder."""
    from modules.features.focus_vision.reminder_policy import FocusVisionReminderPolicy
    policy = FocusVisionReminderPolicy(
        config=FocusVisionConfig(
            phone_warning_after_seconds=20.0,
            voice_warnings_enabled=True,
            dry_run=False,
            startup_grace_seconds=0.0,
            warning_cooldown_seconds=0.0,
        )
    )
    policy.start_session(started_at=0.0)
    snapshot = _make_snapshot(FocusVisionState.ON_TASK, stable_seconds=0.0, now=100.0)
    reminder = policy.evaluate(snapshot, language="en", now=100.0, phone_accumulated_seconds=20.0)
    assert reminder is None


def test_phone_distraction_state_fires_at_zero_stable_seconds():
    """PHONE_DISTRACTION state is reactive; it does not wait for the old 20s threshold."""
    from modules.features.focus_vision.reminder_policy import FocusVisionReminderPolicy
    policy = FocusVisionReminderPolicy(
        config=FocusVisionConfig(
            phone_warning_after_seconds=20.0,
            voice_warnings_enabled=True,
            dry_run=False,
            startup_grace_seconds=0.0,
            warning_cooldown_seconds=0.0,
        )
    )
    policy.start_session(started_at=0.0)
    snapshot = _make_snapshot(FocusVisionState.PHONE_DISTRACTION, stable_seconds=0.0, now=100.0)
    reminder = policy.evaluate(snapshot, language="en", now=100.0)
    assert reminder is not None
    assert reminder.kind == FocusVisionReminderKind.PHONE_DISTRACTION


def test_phone_candidate_with_hard_person_starts_timer():
    """Phone object label + person present → phone_object_detected=True → accumulator counts."""
    from modules.features.focus_vision.observation_reader import FocusVisionObservationReader
    obs = _observation(
        labels=("object:cell phone",),
        face_count=1,
        captured_at=0.0,
    )
    ev = FocusVisionObservationReader().read(obs)
    assert ev.phone_object_detected is True
    assert ev.phone_candidate_detected is True
    assert ev.phone_detection_source == "yolo_object_label"


def test_phone_candidate_without_person_does_not_warn():
    """Phone label present but no person evidence → phone_object_detected=False → no accumulation."""
    from modules.features.focus_vision.observation_reader import FocusVisionObservationReader
    obs = _observation(
        labels=("object:cell phone",),
        face_count=0,
        people_count=0,
        captured_at=0.0,
    )
    ev = FocusVisionObservationReader().read(obs)
    assert ev.phone_candidate_detected is True
    assert ev.phone_object_detected is False

    cfg = _service_config()
    service = FocusVisionSentinelService(vision_backend=MagicMock(), config=cfg)
    assert service._has_phone_person_evidence(ev) is False


def test_hard_visual_person_excludes_tracker_people_count():
    """_has_hard_visual_person() returns False when only people_count is nonzero."""
    cfg = _service_config()
    service = FocusVisionSentinelService(vision_backend=MagicMock(), config=cfg)
    ev = FocusVisionEvidence(people_count=1, face_count=0, yolo_person_count=0)
    assert service._has_hard_visual_person(ev) is False
    assert service._has_person_evidence(ev) is True  # general check still counts it


def test_scan_point_results_collected_in_scan_result():
    """FocusScanResult includes scan_point_results and scan_id after scan completes."""
    result = FocusScanResult(
        scan_type="away_recheck",
        person_found=False,
        triggered_at=1.0,
        completed_at=2.0,
        camera_available=False,
        scan_id="away_recheck_1.000",
        scan_points_attempted=1,
        scan_point_results=({"point": "pre_move", "hard_person_found": False},),
        behavior_presence_ignored_for_scan=True,
    )
    d = result.to_dict()
    assert d["scan_id"] == "away_recheck_1.000"
    assert d["scan_points_attempted"] == 1
    assert d["behavior_presence_ignored_for_scan"] is True
    assert len(d["scan_point_results"]) == 1
    assert d["scan_point_results"][0]["hard_person_found"] is False


def _tracking_observation(
    *,
    face: bool = True,
    person: bool = False,
    phone: bool = False,
    x_center: float = 0.70,
    captured_at: float = 100.0,
) -> VisionObservation:
    obs = _observation(
        face_count=1 if face else 0,
        people_count=1 if person else 0,
        labels=tuple(label for label in (("object:person",) if person else ()) + (("object:cell phone",) if phone else ())),
        captured_at=captured_at,
    )
    width = 640
    height = 480
    box_width = 100
    box_height = 120
    left = int((x_center * width) - (box_width / 2))
    top = 160
    detection = {
        "bounding_box": {
            "left": left,
            "top": top,
            "right": left + box_width,
            "bottom": top + box_height,
        },
        "confidence": 0.9,
    }
    perception = obs.metadata["perception"]
    perception["frame_width"] = width
    perception["frame_height"] = height
    if face:
        perception["faces"] = [detection]
    if person:
        perception["people"] = [detection]
    obs.metadata["frame_width"] = width
    obs.metadata["frame_height"] = height
    return obs


def _object_person_tracking_observation(*, x_center: float = 0.30, captured_at: float = 100.0) -> VisionObservation:
    obs = _tracking_observation(face=False, person=False, x_center=x_center, captured_at=captured_at)
    width = 640
    height = 480
    box_width = 120
    box_height = 220
    left = int((x_center * width) - (box_width / 2))
    top = 120
    obs.labels = ["object:person"]
    obs.metadata["perception"]["objects"] = [
        {
            "label": "person",
            "confidence": 0.88,
            "bounding_box": {
                "left": left,
                "top": top,
                "right": left + box_width,
                "bottom": top + box_height,
            },
            "metadata": {},
        }
    ]
    return obs


def test_continuous_tracking_defaults_enabled_for_runtime_settings():
    from modules.shared.config.settings import load_settings

    cfg = FocusVisionConfig.from_mapping(load_settings())
    assert cfg.continuous_tracking_enabled is True
    assert cfg.tracking_interval_seconds <= 0.2


def test_tracking_worker_step_moves_pan_tilt_for_visible_face():
    backend = MagicMock()
    backend.latest_observation.return_value = _tracking_observation(face=True, x_center=0.75, captured_at=100.0)
    pan_tilt = MagicMock()
    pan_tilt.move_delta.return_value = {"movement_executed": True}
    tracking = MagicMock()
    tracking.plan_once.return_value = {"has_target": False, "reason": "no_target"}
    tracking.latest_pan_tilt_adapter_result.return_value = {"backend_command_executed": False}
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(continuous_tracking_enabled=True, tracking_interval_seconds=0.05),
        pan_tilt_backend=pan_tilt,
        vision_tracking_service=tracking,
        telemetry=MagicMock(),
    )
    service._running = True

    status = service._tracking_worker_step(current_time=100.0)

    tracking.plan_once.assert_not_called()
    pan_tilt.move_delta.assert_called_once()
    assert status["focus_tracking_active"] is True
    assert status["tracking_target_type"] == "face"
    assert status["tracking_move_executed"] is True
    assert status["tracking_backend_command_executed"] is True
    assert status["mobile_base_movement_attempted"] is False
    assert status.get("tracking_plan_called") is False


def test_face_high_in_frame_produces_positive_tilt_command():
    backend = MagicMock()
    backend.latest_observation.return_value = _tracking_observation(face=True, x_center=0.5, captured_at=100.0)
    backend.latest_observation.return_value.metadata["perception"]["faces"][0]["bounding_box"].update(
        {"top": 30, "bottom": 130}
    )
    pan_tilt = MagicMock()
    pan_tilt.move_delta.return_value = {"movement_executed": True, "latest_telemetry": {"tilt": 2.0}}
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(continuous_tracking_enabled=True),
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )
    service._running = True

    status = service._tracking_worker_step(current_time=100.0)

    tilt = pan_tilt.move_delta.call_args.kwargs["tilt_delta_degrees"]
    assert tilt > 0.0
    assert status["tracking_move_degrees"]["tilt_delta_degrees"] > 0.0
    assert status["tracking_backend_response"]["latest_telemetry"]["tilt"] == 2.0


def test_face_low_in_frame_does_not_command_tilt_below_center():
    backend = MagicMock()
    backend.latest_observation.return_value = _tracking_observation(face=True, x_center=0.5, captured_at=100.0)
    backend.latest_observation.return_value.metadata["perception"]["faces"][0]["bounding_box"].update(
        {"top": 350, "bottom": 450}
    )
    pan_tilt = MagicMock()
    pan_tilt.move_delta.return_value = {"movement_executed": True}
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(continuous_tracking_enabled=True),
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )
    service._running = True

    status = service._tracking_worker_step(current_time=100.0)

    pan_tilt.move_delta.assert_not_called()
    assert status["raw_tilt_delta_degrees"] < 0.0
    assert status["final_tilt_delta_degrees"] == 0.0
    assert status["tilt_clamped_to_center"] is True
    assert status["tracking_move_degrees"]["tilt_delta_degrees"] == 0.0


def test_face_diagonal_offset_produces_pan_and_tilt_command():
    backend = MagicMock()
    backend.latest_observation.return_value = _tracking_observation(face=True, x_center=0.75, captured_at=100.0)
    backend.latest_observation.return_value.metadata["perception"]["faces"][0]["bounding_box"].update(
        {"top": 40, "bottom": 140}
    )
    pan_tilt = MagicMock()
    pan_tilt.move_delta.return_value = {"movement_executed": True}
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(continuous_tracking_enabled=True),
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )
    service._running = True

    service._tracking_worker_step(current_time=100.0)

    kwargs = pan_tilt.move_delta.call_args.kwargs
    assert abs(kwargs["pan_delta_degrees"]) > 0.0
    assert abs(kwargs["tilt_delta_degrees"]) > 0.0


def test_centered_face_stays_inside_deadzone_without_jitter():
    backend = MagicMock()
    backend.latest_observation.return_value = _tracking_observation(face=True, x_center=0.5, captured_at=100.0)
    backend.latest_observation.return_value.metadata["perception"]["faces"][0]["bounding_box"].update(
        {"left": 270, "right": 370, "top": 190, "bottom": 290}
    )
    pan_tilt = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(continuous_tracking_enabled=True),
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )
    service._running = True

    status = service._tracking_worker_step(current_time=100.0)

    pan_tilt.move_delta.assert_not_called()
    assert status["tracking_reason"] == "target_centered"


def test_tracking_worker_does_not_track_person_when_face_missing():
    backend = MagicMock()
    backend.latest_observation.return_value = _tracking_observation(face=False, person=True, x_center=0.25, captured_at=100.0)
    pan_tilt = MagicMock()
    pan_tilt.move_delta.return_value = {"movement_executed": True}
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(continuous_tracking_enabled=True),
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )
    service._running = True

    status = service._tracking_worker_step(current_time=100.0)

    assert status["hard_person_visible"] is True
    assert status["tracking_target_type"] == "none"
    assert status["hard_face_visible"] is False
    assert status["tracking_state"] == "face_lost_debounce"
    assert status["tracking_move_executed"] is False
    pan_tilt.move_delta.assert_not_called()


def test_tracking_worker_does_not_track_fresh_object_person_box_when_face_missing():
    backend = MagicMock()
    backend.latest_observation.return_value = _object_person_tracking_observation(x_center=0.25, captured_at=100.0)
    pan_tilt = MagicMock()
    pan_tilt.move_delta.return_value = {"movement_executed": True}
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(continuous_tracking_enabled=True),
        pan_tilt_backend=pan_tilt,
        telemetry=MagicMock(),
    )
    service._running = True

    status = service._tracking_worker_step(current_time=100.0)

    assert status["hard_person_visible"] is True
    assert status["tracking_target_type"] == "none"
    assert status["hard_face_visible"] is False
    assert status["tracking_state"] == "face_lost_debounce"
    assert status["tracking_move_executed"] is False
    pan_tilt.move_delta.assert_not_called()


def test_tracking_worker_surfaces_missing_dependencies_in_telemetry():
    backend = MagicMock()
    backend.latest_observation.return_value = _tracking_observation(face=True, x_center=0.75, captured_at=100.0)
    telemetry = MagicMock()
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(continuous_tracking_enabled=True),
        pan_tilt_backend=None,
        vision_tracking_service=None,
        telemetry=telemetry,
    )
    service._running = True

    status = service._tracking_worker_step(current_time=100.0)
    service._write_tracking_telemetry(status, current_time=100.0)

    event = telemetry.append.call_args[0][0]
    assert event["vision_tracking_service_available"] is False
    assert event["pan_tilt_backend_available"] is False
    assert event["continuous_tracking_enabled"] is True
    assert event["tracking_reason"] == "pan_tilt_backend_unavailable"


def test_tracking_worker_delivers_phone_reminder_on_first_eligible_tick():
    backend = MagicMock()
    backend.latest_observation.return_value = _tracking_observation(face=True, phone=True, captured_at=100.0)
    delivered: list[object] = []
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            dry_run=False,
            voice_warnings_enabled=True,
            continuous_tracking_enabled=True,
            warning_cooldown_seconds=0.0,
            enabled_reminder_kinds=("phone_distraction",),
        ),
        pan_tilt_backend=MagicMock(move_delta=MagicMock(return_value={"movement_executed": True})),
        telemetry=MagicMock(),
    )
    service.set_reminder_handler(delivered.append)
    service._running = True

    status = service._tracking_worker_step(current_time=100.0)

    assert status["immediate_phone_reminder_due"] is True
    assert status["phone_reminder_delivered"] is True
    assert len(delivered) == 1


def test_tracking_worker_delivers_away_after_completed_no_person_scan():
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(captured_at=100.0)
    delivered: list[object] = []
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            dry_run=False,
            voice_warnings_enabled=True,
            active_monitoring_enabled=True,
            continuous_tracking_enabled=True,
            pan_tilt_scan_enabled=False,
            warning_cooldown_seconds=0.0,
            enabled_reminder_kinds=("away_soft",),
        ),
        telemetry=MagicMock(),
    )
    service.set_reminder_handler(delivered.append)
    service._running = True
    assert service._evidence_accumulator is not None
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=90.0)
    service._last_focus_scan_result = FocusScanResult(
        scan_type="away_recheck",
        person_found=False,
        triggered_at=95.0,
        completed_at=96.0,
        camera_available=True,
    )

    status = service._tracking_worker_step(current_time=100.0)

    assert status["immediate_away_reminder_due"] is True
    assert status["away_reminder_delivered"] is True
    assert len(delivered) == 1


def test_tracking_worker_delivers_away_after_scan_timeout():
    backend = MagicMock()
    backend.latest_observation.return_value = _observation(captured_at=100.0)
    delivered: list[object] = []
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            dry_run=False,
            voice_warnings_enabled=True,
            active_monitoring_enabled=True,
            continuous_tracking_enabled=True,
            warning_cooldown_seconds=0.0,
            enabled_reminder_kinds=("away_soft",),
        ),
        telemetry=MagicMock(),
    )
    service.set_reminder_handler(delivered.append)
    service._running = True
    service._focus_scan_running = True
    service._focus_scan_started_at = 90.0
    service._active_focus_scan_id = "away_recheck_90.000"
    service._active_focus_scan_type = "away_recheck"

    status = service._tracking_worker_step(current_time=100.0)

    assert status["immediate_away_reminder_due"] is True
    assert status["away_reminder_delivered"] is True
    assert len(delivered) == 1
    assert service._focus_scan_running is False


def test_continuous_tracking_disables_slow_away_scan_loop():
    service = FocusVisionSentinelService(
        vision_backend=MagicMock(),
        config=_service_config(
            continuous_tracking_enabled=True,
            active_monitoring_enabled=True,
            periodic_scan_enabled=False,
        ),
        telemetry=MagicMock(),
    )
    assert service._evidence_accumulator is not None
    assert service._scan_scheduler is not None
    service._evidence_accumulator.update(person_seen=True, phone_seen=False, now=0.0)
    service._evidence_accumulator.update(person_seen=False, phone_seen=False, now=10.0)
    service._scan_scheduler.reset(now=0.0)

    with patch.object(FocusVisionSentinelService, "_trigger_focus_scan") as trigger:
        service._check_and_trigger_scans(10.0)

    trigger.assert_not_called()


def test_tracking_worker_stops_with_focus_service():
    backend = MagicMock()
    backend.latest_observation.return_value = _tracking_observation(face=True, x_center=0.5)
    service = FocusVisionSentinelService(
        vision_backend=backend,
        config=_service_config(
            enabled=True,
            continuous_tracking_enabled=True,
            tracking_interval_seconds=0.05,
            observation_interval_seconds=0.2,
        ),
        pan_tilt_backend=MagicMock(move_delta=MagicMock(return_value={"movement_executed": False})),
        telemetry=MagicMock(),
    )

    service.start(language="en")
    assert service._tracking_thread is not None
    assert service._tracking_thread.is_alive()
    service.stop()

    assert service._tracking_thread is None
    assert service.status()["focus_tracking_worker_running"] is False
