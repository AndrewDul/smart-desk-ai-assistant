from __future__ import annotations

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.perception.models import PerceptionSnapshot

_COMPUTER_OBJECT_LABELS = {"monitor", "screen", "laptop", "keyboard", "mouse"}


class ComputerWorkInterpreter:
    def interpret(
        self,
        perception: PerceptionSnapshot,
        presence: ActivitySignal,
        desk_activity: ActivitySignal,
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

        computer_objects = tuple(
            obj
            for obj in perception.objects
            if obj.label.strip().lower() in _COMPUTER_OBJECT_LABELS
        )

        if desk_activity.active:
            reasons.append("desk_activity_confirmed")
            confidence += 0.25

        if perception.scene.screen_candidate_count > 0:
            reasons.append("screen_candidate_visible")
            confidence += 0.3

        if computer_objects:
            reasons.append("computer_object_detected")
            confidence += max((obj.confidence for obj in computer_objects), default=0.0) * 0.5

        active = confidence >= 0.6

        return ActivitySignal(
            active=active,
            confidence=confidence,
            reasons=tuple(reasons),
            metadata={
                "computer_object_count": len(computer_objects),
                "screen_candidate_count": perception.scene.screen_candidate_count,
            },
        )