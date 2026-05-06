from __future__ import annotations

from dataclasses import dataclass

from .models import FocusVisionDecision, FocusVisionState, FocusVisionStateSnapshot


@dataclass(slots=True)
class FocusVisionStateMachine:
    """Track how long the current focus vision state has been stable."""

    _current_state: FocusVisionState | None = None
    _state_started_at: float | None = None
    _last_snapshot: FocusVisionStateSnapshot | None = None

    def update(self, decision: FocusVisionDecision) -> FocusVisionStateSnapshot:
        observed_at = float(decision.observed_at)
        if self._current_state != decision.state:
            self._current_state = decision.state
            self._state_started_at = observed_at

        started_at = float(self._state_started_at if self._state_started_at is not None else observed_at)
        stable_seconds = max(0.0, observed_at - started_at)
        snapshot = FocusVisionStateSnapshot(
            current_state=decision.state,
            stable_seconds=round(stable_seconds, 3),
            state_started_at=started_at,
            updated_at=observed_at,
            decision=decision,
        )
        self._last_snapshot = snapshot
        return snapshot

    def reset(self) -> None:
        self._current_state = None
        self._state_started_at = None
        self._last_snapshot = None

    def snapshot(self) -> FocusVisionStateSnapshot | None:
        return self._last_snapshot


__all__ = ["FocusVisionStateMachine"]
