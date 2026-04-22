from __future__ import annotations

from dataclasses import dataclass, field

from modules.devices.vision.behavior import ActivitySignal, BehaviorSnapshot
from modules.devices.vision.config import VisionRuntimeConfig


@dataclass(slots=True)
class _SignalStabilizerState:
    stable_active: bool = False
    consecutive_positive_hits: int = 0
    consecutive_negative_hits: int = 0
    last_positive_at: float | None = None

    def update(
        self,
        signal: ActivitySignal,
        *,
        captured_at: float,
        activation_hits: int,
        deactivation_hits: int,
        hold_seconds: float,
        held_confidence_floor: float = 0.55,
    ) -> ActivitySignal:
        raw_active = bool(signal.active)

        if raw_active:
            self.consecutive_positive_hits += 1
            self.consecutive_negative_hits = 0
            self.last_positive_at = captured_at
        else:
            self.consecutive_negative_hits += 1
            self.consecutive_positive_hits = 0

        within_hold = (
            self.last_positive_at is not None
            and (captured_at - self.last_positive_at) <= hold_seconds
        )

        if self.stable_active:
            if raw_active:
                pass
            elif within_hold:
                pass
            elif self.consecutive_negative_hits >= deactivation_hits:
                self.stable_active = False
        else:
            if raw_active and self.consecutive_positive_hits >= activation_hits:
                self.stable_active = True

        reasons = list(signal.reasons)
        if self.stable_active:
            if not raw_active and within_hold:
                reasons.append("stability_hold_active")
        else:
            if raw_active and self.consecutive_positive_hits < activation_hits:
                reasons.append("awaiting_stability_confirmation")

        confidence = signal.confidence
        if self.stable_active and not raw_active and within_hold:
            confidence = max(confidence, held_confidence_floor)

        metadata = dict(signal.metadata)
        metadata.update(
            {
                "raw_active": raw_active,
                "stable_active": self.stable_active,
                "consecutive_positive_hits": self.consecutive_positive_hits,
                "consecutive_negative_hits": self.consecutive_negative_hits,
                "hold_seconds": hold_seconds,
                "last_positive_at": self.last_positive_at,
            }
        )

        return ActivitySignal(
            active=self.stable_active,
            confidence=confidence,
            reasons=tuple(reasons),
            metadata=metadata,
        )


@dataclass(slots=True)
class BehaviorStabilizer:
    enabled: bool = True
    activation_hits: int = 2
    deactivation_hits: int = 2
    hold_seconds: float = 1.25
    presence_state: _SignalStabilizerState = field(default_factory=_SignalStabilizerState)
    desk_activity_state: _SignalStabilizerState = field(default_factory=_SignalStabilizerState)
    computer_work_state: _SignalStabilizerState = field(default_factory=_SignalStabilizerState)
    phone_usage_state: _SignalStabilizerState = field(default_factory=_SignalStabilizerState)
    study_activity_state: _SignalStabilizerState = field(default_factory=_SignalStabilizerState)

    @classmethod
    def from_config(cls, config: VisionRuntimeConfig) -> "BehaviorStabilizer":
        return cls(
            enabled=config.temporal_stabilization_enabled,
            activation_hits=config.temporal_stabilization_activation_hits,
            deactivation_hits=config.temporal_stabilization_deactivation_hits,
            hold_seconds=config.temporal_stabilization_hold_seconds,
        )

    def stabilize(
        self,
        behavior: BehaviorSnapshot,
        captured_at: float,
    ) -> BehaviorSnapshot:
        if not self.enabled:
            return behavior

        presence = self.presence_state.update(
            behavior.presence,
            captured_at=captured_at,
            activation_hits=self.activation_hits,
            deactivation_hits=self.deactivation_hits,
            hold_seconds=self.hold_seconds,
        )
        desk_activity = self.desk_activity_state.update(
            behavior.desk_activity,
            captured_at=captured_at,
            activation_hits=self.activation_hits,
            deactivation_hits=self.deactivation_hits,
            hold_seconds=self.hold_seconds,
        )
        computer_work = self.computer_work_state.update(
            behavior.computer_work,
            captured_at=captured_at,
            activation_hits=self.activation_hits,
            deactivation_hits=self.deactivation_hits,
            hold_seconds=self.hold_seconds,
        )
        phone_usage = self.phone_usage_state.update(
            behavior.phone_usage,
            captured_at=captured_at,
            activation_hits=self.activation_hits,
            deactivation_hits=self.deactivation_hits,
            hold_seconds=self.hold_seconds,
        )
        study_activity = self.study_activity_state.update(
            behavior.study_activity,
            captured_at=captured_at,
            activation_hits=self.activation_hits,
            deactivation_hits=self.deactivation_hits,
            hold_seconds=self.hold_seconds,
        )

        return BehaviorSnapshot(
            presence=presence,
            desk_activity=desk_activity,
            computer_work=computer_work,
            phone_usage=phone_usage,
            study_activity=study_activity,
            metadata={
                **dict(behavior.metadata),
                "stabilization": {
                    "enabled": self.enabled,
                    "activation_hits": self.activation_hits,
                    "deactivation_hits": self.deactivation_hits,
                    "hold_seconds": self.hold_seconds,
                },
            },
        )