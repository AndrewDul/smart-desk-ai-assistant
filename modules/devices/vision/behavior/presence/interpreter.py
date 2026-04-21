from __future__ import annotations

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.perception.models import PerceptionSnapshot


class PresenceInterpreter:
    def interpret(self, perception: PerceptionSnapshot) -> ActivitySignal:
        reasons: list[str] = []

        max_person_confidence = max(
            (person.confidence for person in perception.people),
            default=0.0,
        )
        desk_zone_people_count = perception.scene.desk_zone_people_count

        active = bool(perception.people) or desk_zone_people_count > 0
        confidence = 0.0

        if perception.people:
            reasons.append("person_detected")
            confidence = max(confidence, max_person_confidence)

        if desk_zone_people_count > 0:
            reasons.append("person_in_desk_zone")
            confidence = max(confidence, 0.7)

        return ActivitySignal(
            active=active,
            confidence=confidence,
            reasons=tuple(reasons),
            metadata={
                "people_count": len(perception.people),
                "desk_zone_people_count": desk_zone_people_count,
            },
        )