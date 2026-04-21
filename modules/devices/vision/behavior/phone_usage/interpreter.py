from __future__ import annotations

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.perception.models import PerceptionSnapshot

_PHONE_OBJECT_LABELS = {"phone", "cell phone", "mobile phone", "smartphone"}


class PhoneUsageInterpreter:
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

        phone_objects = tuple(
            obj
            for obj in perception.objects
            if obj.label.strip().lower() in _PHONE_OBJECT_LABELS
        )

        if perception.scene.handheld_candidate_count > 0:
            reasons.append("handheld_candidate_visible")
            confidence += 0.4

        if phone_objects:
            reasons.append("phone_object_detected")
            confidence += max((obj.confidence for obj in phone_objects), default=0.0) * 0.5

        active = confidence >= 0.6

        return ActivitySignal(
            active=active,
            confidence=confidence,
            reasons=tuple(reasons),
            metadata={
                "phone_object_count": len(phone_objects),
                "handheld_candidate_count": perception.scene.handheld_candidate_count,
            },
        )