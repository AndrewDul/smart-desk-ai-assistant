from __future__ import annotations

import time
from dataclasses import dataclass, field

from modules.runtime.contracts import VisionObservation

from .models import FocusVisionDecision, FocusVisionEvidence, FocusVisionState
from .observation_reader import FocusVisionObservationReader


@dataclass(slots=True)
class FocusVisionDecisionEngine:
    """Convert current vision evidence into one focus-monitoring state."""

    reader: FocusVisionObservationReader = field(default_factory=FocusVisionObservationReader)

    def decide(self, observation: VisionObservation | None, *, observed_at: float | None = None) -> FocusVisionDecision:
        evidence = self.reader.read(observation)
        timestamp = float(observed_at if observed_at is not None else time.monotonic())
        if evidence.captured_at > 0.0:
            timestamp = evidence.captured_at

        if observation is None or not evidence.detected:
            return FocusVisionDecision(FocusVisionState.NO_OBSERVATION, 0.0, ("no_vision_observation",), timestamp, evidence)

        if self._is_phone_distraction(evidence):
            return FocusVisionDecision(FocusVisionState.PHONE_DISTRACTION, max(0.55, evidence.phone_usage_confidence), self._phone_reasons(evidence), timestamp, evidence)

        if self._is_on_task(evidence):
            return FocusVisionDecision(FocusVisionState.ON_TASK, self._on_task_confidence(evidence), self._on_task_reasons(evidence), timestamp, evidence)

        if self._is_absent(evidence):
            return FocusVisionDecision(FocusVisionState.ABSENT, 0.75, ("no_presence_or_desk_activity",), timestamp, evidence)

        return FocusVisionDecision(FocusVisionState.UNCERTAIN, 0.35, ("mixed_or_low_confidence_focus_evidence",), timestamp, evidence)

    @staticmethod
    def _is_phone_distraction(evidence: FocusVisionEvidence) -> bool:
        if not evidence.presence_active or not evidence.phone_usage_active:
            return False
        if evidence.computer_work_active and evidence.computer_work_confidence >= 0.85:
            return False
        return True

    @staticmethod
    def _is_on_task(evidence: FocusVisionEvidence) -> bool:
        if not evidence.presence_active or not evidence.desk_activity_active:
            return False
        if evidence.phone_usage_active:
            return False
        return evidence.study_activity_active or evidence.computer_work_active

    @staticmethod
    def _is_absent(evidence: FocusVisionEvidence) -> bool:
        return not evidence.presence_active and not evidence.desk_activity_active

    @staticmethod
    def _phone_reasons(evidence: FocusVisionEvidence) -> tuple[str, ...]:
        reasons = ["phone_usage_active", "presence_active"]
        if evidence.desk_activity_active:
            reasons.append("desk_activity_active")
        if evidence.phone_usage_active_seconds > 0.0:
            reasons.append("phone_usage_session_active")
        return tuple(reasons)

    @staticmethod
    def _on_task_reasons(evidence: FocusVisionEvidence) -> tuple[str, ...]:
        reasons = ["presence_active", "desk_activity_active", "phone_usage_inactive"]
        if evidence.study_activity_active:
            reasons.append("study_activity_active")
        if evidence.computer_work_active:
            reasons.append("computer_work_active")
        return tuple(reasons)

    @staticmethod
    def _on_task_confidence(evidence: FocusVisionEvidence) -> float:
        signals = [evidence.presence_confidence, evidence.desk_activity_confidence]
        if evidence.study_activity_active:
            signals.append(evidence.study_activity_confidence)
        if evidence.computer_work_active:
            signals.append(evidence.computer_work_confidence)
        return max(0.55, min(1.0, sum(signals) / max(1, len(signals))))


__all__ = ["FocusVisionDecisionEngine"]
