from __future__ import annotations

from dataclasses import dataclass, field

from modules.devices.vision.behavior import ActivitySignal, BehaviorSnapshot
from modules.devices.vision.sessions.models import ActivitySessionSnapshot, VisionSessionSnapshot


@dataclass(slots=True)
class _ActivityTrackerState:
    active: bool = False
    current_active_seconds: float = 0.0
    last_active_streak_seconds: float = 0.0
    total_active_seconds: float = 0.0
    activations: int = 0
    last_started_at: float | None = None
    last_ended_at: float | None = None
    last_observed_at: float | None = None

    def update(self, signal: ActivitySignal, captured_at: float) -> ActivitySessionSnapshot:
        delta = 0.0
        if self.last_observed_at is not None:
            delta = max(0.0, float(captured_at) - float(self.last_observed_at))

        if signal.active:
            if self.active:
                self.current_active_seconds += delta
                self.total_active_seconds += delta
            else:
                self.active = True
                self.activations += 1
                self.current_active_seconds = 0.0
                self.last_started_at = captured_at
        else:
            if self.active:
                self.current_active_seconds += delta
                self.total_active_seconds += delta
                self.last_active_streak_seconds = self.current_active_seconds
                self.current_active_seconds = 0.0
                self.active = False
                self.last_ended_at = captured_at

        self.last_observed_at = captured_at

        return ActivitySessionSnapshot(
            active=self.active,
            state="active" if self.active else "inactive",
            current_active_seconds=round(self.current_active_seconds, 3),
            last_active_streak_seconds=round(self.last_active_streak_seconds, 3),
            total_active_seconds=round(self.total_active_seconds, 3),
            activations=self.activations,
            last_started_at=self.last_started_at,
            last_ended_at=self.last_ended_at,
            metadata={
                "signal_confidence": signal.confidence,
                "signal_reasons": list(signal.reasons),
            },
        )


@dataclass(slots=True)
class VisionSessionTracker:
    presence_state: _ActivityTrackerState = field(default_factory=_ActivityTrackerState)
    desk_activity_state: _ActivityTrackerState = field(default_factory=_ActivityTrackerState)
    computer_work_state: _ActivityTrackerState = field(default_factory=_ActivityTrackerState)
    phone_usage_state: _ActivityTrackerState = field(default_factory=_ActivityTrackerState)
    study_activity_state: _ActivityTrackerState = field(default_factory=_ActivityTrackerState)

    def update(
        self,
        behavior: BehaviorSnapshot,
        captured_at: float,
    ) -> VisionSessionSnapshot:
        presence = self.presence_state.update(behavior.presence, captured_at)
        desk_activity = self.desk_activity_state.update(behavior.desk_activity, captured_at)
        computer_work = self.computer_work_state.update(behavior.computer_work, captured_at)
        phone_usage = self.phone_usage_state.update(behavior.phone_usage, captured_at)
        study_activity = self.study_activity_state.update(behavior.study_activity, captured_at)

        return VisionSessionSnapshot(
            presence=presence,
            desk_activity=desk_activity,
            computer_work=computer_work,
            phone_usage=phone_usage,
            study_activity=study_activity,
            metadata={
                "tracker_version": 1,
                "captured_at": captured_at,
            },
        )