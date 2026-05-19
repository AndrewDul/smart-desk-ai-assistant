from __future__ import annotations

from modules.features.focus_vision import (
    FocusVisionConfig,
    FocusVisionDecision,
    FocusVisionEvidence,
    FocusVisionReminderKind,
    FocusVisionReminderPolicy,
    FocusVisionState,
    FocusVisionStateMachine,
)


def _decision(state: FocusVisionState, observed_at: float) -> FocusVisionDecision:
    return FocusVisionDecision(
        state=state,
        confidence=0.8,
        reasons=("unit_test",),
        observed_at=observed_at,
        evidence=FocusVisionEvidence(detected=True, captured_at=observed_at),
    )


def test_state_machine_counts_stable_seconds_for_unchanged_state() -> None:
    machine = FocusVisionStateMachine()

    first = machine.update(_decision(FocusVisionState.ABSENT, 10.0))
    second = machine.update(_decision(FocusVisionState.ABSENT, 18.5))

    assert first.stable_seconds == 0.0
    assert second.stable_seconds == 8.5


def test_state_machine_resets_duration_when_state_changes() -> None:
    machine = FocusVisionStateMachine()

    machine.update(_decision(FocusVisionState.ABSENT, 10.0))
    snapshot = machine.update(_decision(FocusVisionState.ON_TASK, 13.0))

    assert snapshot.current_state == FocusVisionState.ON_TASK
    assert snapshot.stable_seconds == 0.0


def test_reminder_policy_emits_polish_absence_reminder_after_threshold() -> None:
    config = FocusVisionConfig(
        startup_grace_seconds=0.0,
        absence_warning_after_seconds=5.0,
        warning_cooldown_seconds=60.0,
    )
    policy = FocusVisionReminderPolicy(config=config)
    policy.start_session(started_at=0.0)
    machine = FocusVisionStateMachine()
    machine.update(_decision(FocusVisionState.AWAY_CONFIRMED, 10.0))
    snapshot = machine.update(_decision(FocusVisionState.AWAY_CONFIRMED, 16.0))

    reminder = policy.evaluate(snapshot, language="pl", now=16.0)

    assert reminder is not None
    assert reminder.kind == FocusVisionReminderKind.ABSENCE
    assert reminder.language == "pl"
    assert "Wróć do biurka" in reminder.text


def test_reminder_policy_respects_cooldown() -> None:
    config = FocusVisionConfig(
        startup_grace_seconds=0.0,
        phone_warning_after_seconds=2.0,
        warning_cooldown_seconds=60.0,
    )
    policy = FocusVisionReminderPolicy(config=config)
    policy.start_session(started_at=0.0)
    machine = FocusVisionStateMachine()
    machine.update(_decision(FocusVisionState.PHONE_DISTRACTION, 10.0))
    snapshot = machine.update(_decision(FocusVisionState.PHONE_DISTRACTION, 13.0))

    first = policy.evaluate(snapshot, language="en", now=13.0)
    second = policy.evaluate(snapshot, language="en", now=20.0)

    assert first is not None
    assert second is None

def test_reminder_policy_can_enable_only_phone_distraction_reminders() -> None:
    config = FocusVisionConfig(
        startup_grace_seconds=0.0,
        absence_warning_after_seconds=5.0,
        phone_warning_after_seconds=2.0,
        enabled_reminder_kinds=("phone_distraction",),
    )
    policy = FocusVisionReminderPolicy(config=config)
    policy.start_session(started_at=0.0)

    absent_machine = FocusVisionStateMachine()
    absent_machine.update(_decision(FocusVisionState.ABSENT, 10.0))
    absent_snapshot = absent_machine.update(_decision(FocusVisionState.ABSENT, 20.0))

    phone_machine = FocusVisionStateMachine()
    phone_machine.update(_decision(FocusVisionState.PHONE_DISTRACTION, 30.0))
    phone_snapshot = phone_machine.update(_decision(FocusVisionState.PHONE_DISTRACTION, 34.0))

    assert policy.evaluate(absent_snapshot, language="en", now=20.0) is None

    reminder = policy.evaluate(phone_snapshot, language="en", now=34.0)
    assert reminder is not None
    assert reminder.kind == FocusVisionReminderKind.PHONE_DISTRACTION
    assert "Put the phone down" in reminder.text



def test_reminder_policy_accepts_absent_alias_for_absence_reminders() -> None:
    config = FocusVisionConfig(
        startup_grace_seconds=0.0,
        absence_warning_after_seconds=5.0,
        enabled_reminder_kinds=("absent",),
    )
    policy = FocusVisionReminderPolicy(config=config)
    policy.start_session(started_at=0.0)
    machine = FocusVisionStateMachine()
    machine.update(_decision(FocusVisionState.AWAY_CONFIRMED, 10.0))
    snapshot = machine.update(_decision(FocusVisionState.AWAY_CONFIRMED, 16.0))

    reminder = policy.evaluate(snapshot, language="en", now=16.0)

    assert reminder is not None
    assert reminder.kind == FocusVisionReminderKind.ABSENCE
    assert "Come back to your desk" in reminder.text


def test_reminder_policy_uses_phone_session_duration_when_state_stability_resets() -> None:
    config = FocusVisionConfig(
        startup_grace_seconds=0.0,
        phone_warning_after_seconds=10.0,
        enabled_reminder_kinds=("phone_distraction",),
    )
    policy = FocusVisionReminderPolicy(config=config)
    policy.start_session(started_at=0.0)
    machine = FocusVisionStateMachine()
    snapshot = machine.update(
        FocusVisionDecision(
            state=FocusVisionState.PHONE_DISTRACTION,
            confidence=1.0,
            reasons=("phone_usage_active", "phone_usage_session_active"),
            observed_at=12030.0,
            evidence=FocusVisionEvidence(
                detected=True,
                phone_usage_active=True,
                phone_usage_confidence=1.0,
                phone_usage_active_seconds=42.825,
                captured_at=12030.0,
                labels=("object:cell phone", "behavior:phone_usage"),
            ),
        )
    )

    assert snapshot.stable_seconds == 0.0

    reminder = policy.evaluate(snapshot, language="en", now=12030.0)

    assert reminder is not None
    assert reminder.kind == FocusVisionReminderKind.PHONE_DISTRACTION
    assert reminder.dry_run == (config.dry_run or not config.voice_warnings_enabled)
    assert "Put the phone down" in reminder.text
