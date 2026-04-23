from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.behavior.shared import has_downward_attention_proxy
from modules.devices.vision.perception.models import PerceptionSnapshot

_DEFAULT_PHONE_OBJECT_LABELS = ("phone", "cell phone", "mobile phone", "smartphone")


def _normalized_label_set(values: Iterable[str], *, fallback: tuple[str, ...]) -> frozenset[str]:
    normalized = {str(value).strip().lower() for value in values if str(value).strip()}
    if not normalized:
        normalized = set(fallback)
    return frozenset(normalized)


@dataclass(slots=True)
class PhoneUsageInterpreter:
    active_threshold: float = 0.60
    phone_object_labels: frozenset[str] = frozenset(_DEFAULT_PHONE_OBJECT_LABELS)
    computer_work_active_penalty: float = 0.18
    screen_visible_penalty: float = 0.08
    no_screen_bonus: float = 0.05

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> "PhoneUsageInterpreter":
        payload = dict(raw or {})
        return cls(
            active_threshold=max(
                0.0,
                min(1.0, float(payload.get("phone_usage_active_threshold", 0.60))),
            ),
            phone_object_labels=_normalized_label_set(
                payload.get("phone_usage_object_labels", _DEFAULT_PHONE_OBJECT_LABELS),
                fallback=_DEFAULT_PHONE_OBJECT_LABELS,
            ),
            computer_work_active_penalty=max(
                0.0,
                float(payload.get("phone_usage_computer_work_active_penalty", 0.18)),
            ),
            screen_visible_penalty=max(
                0.0,
                float(payload.get("phone_usage_screen_visible_penalty", 0.08)),
            ),
            no_screen_bonus=max(
                0.0,
                float(payload.get("phone_usage_no_screen_bonus", 0.05)),
            ),
        )

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
            if obj.label.strip().lower() in self.phone_object_labels
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
                    "active_threshold": self.active_threshold,
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
            confidence -= self.computer_work_active_penalty

        if screen_candidate_count == 0:
            reasons.append("no_screen_candidate_visible")
            confidence += self.no_screen_bonus
        else:
            reasons.append("screen_candidate_visible")
            confidence -= self.screen_visible_penalty

        active = confidence >= self.active_threshold

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
                "active_threshold": self.active_threshold,
                "computer_work_active_penalty": self.computer_work_active_penalty,
                "screen_visible_penalty": self.screen_visible_penalty,
                "no_screen_bonus": self.no_screen_bonus,
            },
        )