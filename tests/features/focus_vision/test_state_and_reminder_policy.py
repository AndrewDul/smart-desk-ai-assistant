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
    machine.update(_decision(FocusVisionState.ABSENT, 10.0))
    snapshot = machine.update(_decision(FocusVisionState.ABSENT, 16.0))

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
