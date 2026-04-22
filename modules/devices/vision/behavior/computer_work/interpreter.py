from __future__ import annotations

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.perception.models import PerceptionSnapshot

_COMPUTER_OBJECT_LABELS = {"monitor", "screen", "laptop", "keyboard", "mouse"}
_PHONE_OBJECT_LABELS = {"phone", "cell phone", "mobile phone", "smartphone"}


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
        phone_objects = tuple(
            obj
            for obj in perception.objects
            if obj.label.strip().lower() in _PHONE_OBJECT_LABELS
        )

        engagement_face_count = perception.scene.engagement_face_count
        handheld_candidate_count = perception.scene.handheld_candidate_count
        screen_candidate_count = perception.scene.screen_candidate_count
        phone_like_evidence = handheld_candidate_count > 0 or bool(phone_objects)

        if desk_activity.active:
            reasons.append("desk_activity_confirmed")
            confidence += 0.30

        if engagement_face_count > 0:
            reasons.append("face_engaged_at_desk")
            confidence += 0.22

        if screen_candidate_count > 0:
            reasons.append("screen_candidate_visible")
            confidence += 0.18

        if computer_objects:
            reasons.append("computer_object_detected")
            confidence += 0.20
            confidence += max((obj.confidence for obj in computer_objects), default=0.0) * 0.25

        if desk_activity.active and engagement_face_count > 0 and not phone_like_evidence:
            reasons.append("desk_screen_posture_proxy")
            confidence += 0.18

        if phone_like_evidence:
            reasons.append("phone_like_evidence_present")
            confidence -= 0.20
        else:
            reasons.append("no_phone_like_evidence")
            confidence += 0.06

        inference_mode = "inactive"
        if computer_objects or screen_candidate_count > 0:
            inference_mode = "hybrid"
        elif desk_activity.active and engagement_face_count > 0:
            inference_mode = "desk_face_proxy"

        active = confidence >= 0.65

        return ActivitySignal(
            active=active,
            confidence=confidence,
            reasons=tuple(reasons),
            metadata={
                "computer_object_count": len(computer_objects),
                "screen_candidate_count": screen_candidate_count,
                "engagement_face_count": engagement_face_count,
                "phone_like_evidence": phone_like_evidence,
                "inference_mode": inference_mode,
            },
        )