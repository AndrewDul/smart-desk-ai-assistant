from __future__ import annotations

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.perception.models import FaceDetection, PerceptionSnapshot

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

        if handheld_candidate_count > 0:
            reasons.append("handheld_candidate_visible")
            confidence += 0.30

        if phone_objects:
            reasons.append("phone_object_detected")
            confidence += 0.40
            confidence += max((obj.confidence for obj in phone_objects), default=0.0) * 0.20

        if desk_activity.active:
            reasons.append("desk_activity_confirmed")
            confidence += 0.08

        if engagement_face_count > 0:
            reasons.append("face_engaged_at_desk")
            confidence += 0.08

        downward_attention_proxy = self._has_downward_attention_proxy(perception)
        if downward_attention_proxy:
            reasons.append("downward_attention_proxy")
            confidence += 0.16

        if not computer_work.active:
            reasons.append("computer_work_not_active")
            confidence += 0.10
        else:
            reasons.append("computer_work_active")
            confidence -= 0.22

        if screen_candidate_count == 0:
            reasons.append("no_screen_candidate_visible")
            confidence += 0.08
        else:
            reasons.append("screen_candidate_visible")
            confidence -= 0.10

        if (
            desk_activity.active
            and engagement_face_count > 0
            and downward_attention_proxy
            and not computer_work.active
            and screen_candidate_count == 0
        ):
            reasons.append("desk_phone_posture_proxy")
            confidence += 0.18

        if phone_objects or handheld_candidate_count > 0:
            inference_mode = "object_or_handheld"
        elif downward_attention_proxy and desk_activity.active:
            inference_mode = "desk_face_proxy"
        else:
            inference_mode = "inactive"

        active = confidence >= 0.62

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
                "inference_mode": inference_mode,
            },
        )

    def _has_downward_attention_proxy(self, perception: PerceptionSnapshot) -> bool:
        if not perception.faces or perception.frame_height <= 0:
            return False

        primary_face = max(
            perception.faces,
            key=lambda face: (face.confidence, face.bounding_box.height),
        )
        return self._face_suggests_downward_attention(primary_face, perception.frame_height)

    @staticmethod
    def _face_suggests_downward_attention(face: FaceDetection, frame_height: int) -> bool:
        normalized_center_y = face.bounding_box.center_y / frame_height
        normalized_bottom_y = face.bounding_box.bottom / frame_height
        return normalized_center_y >= 0.45 and normalized_bottom_y >= 0.60