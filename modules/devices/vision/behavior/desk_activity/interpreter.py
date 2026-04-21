from __future__ import annotations

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.perception.models import PerceptionSnapshot


class DeskActivityInterpreter:
    def interpret(
        self,
        perception: PerceptionSnapshot,
        presence: ActivitySignal,
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

        reasons.append("presence_confirmed")
        confidence = max(confidence, 0.45)

        if perception.scene.desk_zone_people_count > 0:
            reasons.append("desk_zone_occupied")
            confidence += 0.25

        if perception.scene.screen_candidate_count > 0:
            reasons.append("screen_candidate_visible")
            confidence += 0.15

        if perception.scene.handheld_candidate_count > 0:
            reasons.append("handheld_candidate_visible")
            confidence += 0.05

        active = confidence >= 0.6

        return ActivitySignal(
            active=active,
            confidence=confidence,
            reasons=tuple(reasons),
            metadata={
                "desk_zone_people_count": perception.scene.desk_zone_people_count,
                "screen_candidate_count": perception.scene.screen_candidate_count,
                "handheld_candidate_count": perception.scene.handheld_candidate_count,
            },
        )