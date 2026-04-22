from __future__ import annotations

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.behavior.shared import has_downward_attention_proxy
from modules.devices.vision.perception.models import PerceptionSnapshot

_PHONE_OBJECT_LABELS = {"phone", "cell phone", "mobile phone", "smartphone"}


class PhoneUsageInterpreter:
    def interpret(
        self,
        perception: PerceptionSnapshot,
        presence: ActivitySignal,
        desk_activity: ActivitySignal,
        computer_work: ActivitySignal,
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
        engagement_face_count = perception.scene.engagement_face_count
        handheld_candidate_count = perception.scene.handheld_candidate_count
        screen_candidate_count = perception.scene.screen_candidate_count
        downward_attention_proxy = has_downward_attention_proxy(perception)
        visual_phone_evidence = bool(phone_objects)

        if not visual_phone_evidence:
            reasons.append("phone_visual_evidence_missing")

            if handheld_candidate_count > 0:
                reasons.append("handheld_candidate_visible")

            if downward_attention_proxy:
                reasons.append("downward_attention_proxy")

            if desk_activity.active:
                reasons.append("desk_activity_confirmed")

            if engagement_face_count > 0:
                reasons.append("face_engaged_at_desk")

            if computer_work.active:
                reasons.append("computer_work_active")

            if screen_candidate_count == 0:
                reasons.append("no_screen_candidate_visible")
            else:
                reasons.append("screen_candidate_visible")

            return ActivitySignal(
                active=False,
                confidence=0.0,
                reasons=tuple(reasons),
                metadata={
                    "phone_object_count": 0,
                    "handheld_candidate_count": handheld_candidate_count,
                    "engagement_face_count": engagement_face_count,
                    "screen_candidate_count": screen_candidate_count,
                    "downward_attention_proxy": downward_attention_proxy,
                    "visual_phone_evidence": False,
                    "inference_mode": "inactive_no_visual_evidence",
                },
            )

        reasons.append("phone_object_detected")
        confidence += 0.42
        confidence += max((obj.confidence for obj in phone_objects), default=0.0) * 0.22

        if handheld_candidate_count > 0:
            reasons.append("handheld_candidate_visible")
            confidence += 0.12

        if desk_activity.active:
            reasons.append("desk_activity_confirmed")
            confidence += 0.08

        if engagement_face_count > 0:
            reasons.append("face_engaged_at_desk")
            confidence += 0.08

        if downward_attention_proxy:
            reasons.append("downward_attention_proxy")
            confidence += 0.08

        if not computer_work.active:
            reasons.append("computer_work_not_active")
            confidence += 0.08
        else:
            reasons.append("computer_work_active")
            confidence -= 0.18

        if screen_candidate_count == 0:
            reasons.append("no_screen_candidate_visible")
            confidence += 0.05
        else:
            reasons.append("screen_candidate_visible")
            confidence -= 0.08

        active = confidence >= 0.60

        return ActivitySignal(
            active=active,
            confidence=confidence,
            reasons=tuple(reasons),
            metadata={
                "phone_object_count": len(phone_objects),
                "handheld_candidate_count": handheld_candidate_count,
                "engagement_face_count": engagement_face_count,
                "screen_candidate_count": screen_candidate_count,
                "downward_attention_proxy": downward_attention_proxy,
                "visual_phone_evidence": True,
                "inference_mode": "confirmed_phone_object",
            },
        )