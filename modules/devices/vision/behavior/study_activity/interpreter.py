from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.perception.models import PerceptionSnapshot


@dataclass(slots=True)
class StudyActivityInterpreter:
    active_threshold: float = 0.65
    desk_activity_weight: float = 0.35
    computer_work_bonus: float = 0.30
    screen_candidate_bonus: float = 0.15
    phone_usage_penalty: float = 0.30
    no_phone_bonus: float = 0.20
    baseline_bonus: float = 0.15
    require_desk_or_computer_evidence: bool = True

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> "StudyActivityInterpreter":
        payload = dict(raw or {})
        return cls(
            active_threshold=max(
                0.0,
                min(1.0, float(payload.get("study_activity_active_threshold", 0.65))),
            ),
            desk_activity_weight=max(
                0.0,
                float(payload.get("study_activity_desk_activity_weight", 0.35)),
            ),
            computer_work_bonus=max(
                0.0,
                float(payload.get("study_activity_computer_work_bonus", 0.30)),
            ),
            screen_candidate_bonus=max(
                0.0,
                float(payload.get("study_activity_screen_candidate_bonus", 0.15)),
            ),
            phone_usage_penalty=max(
                0.0,
                float(payload.get("study_activity_phone_usage_penalty", 0.30)),
            ),
            no_phone_bonus=max(
                0.0,
                float(payload.get("study_activity_no_phone_bonus", 0.20)),
            ),
            baseline_bonus=max(
                0.0,
                float(payload.get("study_activity_baseline_bonus", 0.15)),
            ),
            require_desk_or_computer_evidence=bool(
                payload.get("study_activity_require_desk_or_computer_evidence", True)
            ),
        )

    def interpret(
        self,
        perception: PerceptionSnapshot,
        presence: ActivitySignal,
        desk_activity: ActivitySignal,
        computer_work: ActivitySignal,
        phone_usage: ActivitySignal,
    ) -> ActivitySignal:
        reasons: list[str] = []
        confidence = 0.0

        if not presence.active:
            return ActivitySignal(
                active=False,
                confidence=0.0,
                reasons=(),
                metadata={"presence_required": True},
            )

        has_study_evidence = (
            desk_activity.active
            or computer_work.active
            or perception.scene.screen_candidate_count > 0
        )

        if self.require_desk_or_computer_evidence and not has_study_evidence:
            return ActivitySignal(
                active=False,
                confidence=0.0,
                reasons=("study_evidence_missing",),
                metadata={
                    "screen_candidate_count": perception.scene.screen_candidate_count,
                    "phone_active": phone_usage.active,
                    "computer_work_active": computer_work.active,
                    "desk_activity_active": desk_activity.active,
                    "active_threshold": self.active_threshold,
                    "require_desk_or_computer_evidence": self.require_desk_or_computer_evidence,
                    "inference_mode": "inactive_missing_study_evidence",
                },
            )

        if desk_activity.active:
            reasons.append("desk_activity_confirmed")
            confidence += desk_activity.confidence * self.desk_activity_weight

        if computer_work.active:
            reasons.append("computer_work_confirmed")
            confidence += self.computer_work_bonus
        elif perception.scene.screen_candidate_count > 0:
            reasons.append("screen_candidate_visible")
            confidence += self.screen_candidate_bonus

        if phone_usage.active:
            reasons.append("phone_usage_detected")
            confidence -= self.phone_usage_penalty
        else:
            reasons.append("phone_not_detected")
            confidence += self.no_phone_bonus

        confidence += self.baseline_bonus
        active = confidence >= self.active_threshold

        inference_mode = "inactive"
        if computer_work.active and not phone_usage.active:
            inference_mode = "computer_work_supported"
        elif desk_activity.active and perception.scene.screen_candidate_count > 0 and not phone_usage.active:
            inference_mode = "desk_screen_supported"
        elif phone_usage.active:
            inference_mode = "suppressed_by_phone_usage"
        elif has_study_evidence:
            inference_mode = "weak_study_proxy"

        return ActivitySignal(
            active=active,
            confidence=confidence,
            reasons=tuple(reasons),
            metadata={
                "screen_candidate_count": perception.scene.screen_candidate_count,
                "phone_active": phone_usage.active,
                "computer_work_active": computer_work.active,
                "desk_activity_active": desk_activity.active,
                "active_threshold": self.active_threshold,
                "desk_activity_weight": self.desk_activity_weight,
                "computer_work_bonus": self.computer_work_bonus,
                "screen_candidate_bonus": self.screen_candidate_bonus,
                "phone_usage_penalty": self.phone_usage_penalty,
                "no_phone_bonus": self.no_phone_bonus,
                "baseline_bonus": self.baseline_bonus,
                "require_desk_or_computer_evidence": self.require_desk_or_computer_evidence,
                "inference_mode": inference_mode,
            },
        )