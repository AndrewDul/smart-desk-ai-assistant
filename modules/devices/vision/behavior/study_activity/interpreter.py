from __future__ import annotations

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.perception.models import PerceptionSnapshot


class StudyActivityInterpreter:
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

        if desk_activity.active:
            reasons.append("desk_activity_confirmed")
            confidence += desk_activity.confidence * 0.35

        if computer_work.active:
            reasons.append("computer_work_confirmed")
            confidence += 0.3
        elif perception.scene.screen_candidate_count > 0:
            reasons.append("screen_candidate_visible")
            confidence += 0.15

        if phone_usage.active:
            reasons.append("phone_usage_detected")
            confidence -= 0.3
        else:
            reasons.append("phone_not_detected")
            confidence += 0.2

        confidence += 0.15
        active = confidence >= 0.65

        return ActivitySignal(
            active=active,
            confidence=confidence,
            reasons=tuple(reasons),
            metadata={
                "screen_candidate_count": perception.scene.screen_candidate_count,
                "phone_active": phone_usage.active,
                "computer_work_active": computer_work.active,
            },
        )