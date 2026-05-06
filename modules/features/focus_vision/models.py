from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FocusVisionState(str, Enum):
    """High-level focus monitoring state derived from vision behavior signals."""

    NO_OBSERVATION = "no_observation"
    ON_TASK = "on_task"
    ABSENT = "absent"
    PHONE_DISTRACTION = "phone_distraction"
    UNCERTAIN = "uncertain"


class FocusVisionReminderKind(str, Enum):
    """Reminder classes emitted by the focus vision policy."""

    ABSENCE = "absence"
    PHONE_DISTRACTION = "phone_distraction"


@dataclass(frozen=True, slots=True)
class FocusVisionEvidence:
    """Normalized evidence extracted from a VisionObservation."""

    detected: bool = False
    presence_active: bool = False
    desk_activity_active: bool = False
    computer_work_active: bool = False
    phone_usage_active: bool = False
    study_activity_active: bool = False
    presence_confidence: float = 0.0
    desk_activity_confidence: float = 0.0
    computer_work_confidence: float = 0.0
    phone_usage_confidence: float = 0.0
    study_activity_confidence: float = 0.0
    presence_active_seconds: float = 0.0
    desk_activity_active_seconds: float = 0.0
    computer_work_active_seconds: float = 0.0
    phone_usage_active_seconds: float = 0.0
    study_activity_active_seconds: float = 0.0
    captured_at: float = 0.0
    labels: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detected": self.detected,
            "presence_active": self.presence_active,
            "desk_activity_active": self.desk_activity_active,
            "computer_work_active": self.computer_work_active,
            "phone_usage_active": self.phone_usage_active,
            "study_activity_active": self.study_activity_active,
            "presence_confidence": self.presence_confidence,
            "desk_activity_confidence": self.desk_activity_confidence,
            "computer_work_confidence": self.computer_work_confidence,
            "phone_usage_confidence": self.phone_usage_confidence,
            "study_activity_confidence": self.study_activity_confidence,
            "presence_active_seconds": self.presence_active_seconds,
            "desk_activity_active_seconds": self.desk_activity_active_seconds,
            "computer_work_active_seconds": self.computer_work_active_seconds,
            "phone_usage_active_seconds": self.phone_usage_active_seconds,
            "study_activity_active_seconds": self.study_activity_active_seconds,
            "captured_at": self.captured_at,
            "labels": list(self.labels),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class FocusVisionDecision:
    """Single-frame focus decision before time-based stabilization."""

    state: FocusVisionState
    confidence: float
    reasons: tuple[str, ...]
    observed_at: float
    evidence: FocusVisionEvidence = field(default_factory=FocusVisionEvidence)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "confidence": self.confidence,
            "reasons": list(self.reasons),
            "observed_at": self.observed_at,
            "evidence": self.evidence.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class FocusVisionStateSnapshot:
    """Time-stabilized focus state snapshot."""

    current_state: FocusVisionState
    stable_seconds: float
    state_started_at: float
    updated_at: float
    decision: FocusVisionDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_state": self.current_state.value,
            "stable_seconds": self.stable_seconds,
            "state_started_at": self.state_started_at,
            "updated_at": self.updated_at,
            "decision": self.decision.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class FocusVisionReminder:
    """Deterministic focus reminder candidate."""

    kind: FocusVisionReminderKind
    language: str
    text: str
    created_at: float
    snapshot: FocusVisionStateSnapshot
    dry_run: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "language": self.language,
            "text": self.text,
            "created_at": self.created_at,
            "dry_run": self.dry_run,
            "snapshot": self.snapshot.to_dict(),
        }


__all__ = [
    "FocusVisionDecision",
    "FocusVisionEvidence",
    "FocusVisionReminder",
    "FocusVisionReminderKind",
    "FocusVisionState",
    "FocusVisionStateSnapshot",
]
