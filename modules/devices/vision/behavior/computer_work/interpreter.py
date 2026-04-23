from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from modules.devices.vision.behavior.models import ActivitySignal
from modules.devices.vision.behavior.shared import has_downward_attention_proxy
from modules.devices.vision.perception.models import PerceptionSnapshot

_DEFAULT_COMPUTER_OBJECT_LABELS = ("monitor", "screen", "laptop", "keyboard", "mouse")
_DEFAULT_PHONE_OBJECT_LABELS = ("phone", "cell phone", "mobile phone", "smartphone")


def _normalized_label_set(values: Iterable[str], *, fallback: tuple[str, ...]) -> frozenset[str]:
    normalized = {str(value).strip().lower() for value in values if str(value).strip()}
    if not normalized:
        normalized = set(fallback)
    return frozenset(normalized)


@dataclass(slots=True)
class ComputerWorkInterpreter:
    active_threshold: float = 0.65
    computer_object_labels: frozenset[str] = frozenset(_DEFAULT_COMPUTER_OBJECT_LABELS)
    phone_object_labels: frozenset[str] = frozenset(_DEFAULT_PHONE_OBJECT_LABELS)
    downward_attention_penalty: float = 0.16
    explicit_screen_downward_penalty_multiplier: float = 0.35
    explicit_screen_attention_recovery_bonus: float = 0.08

    @classmethod
    def from_mapping(cls, raw: dict[str, Any] | None) -> "ComputerWorkInterpreter":
        payload = dict(raw or {})
        return cls(
            active_threshold=max(
                0.0,
                min(1.0, float(payload.get("computer_work_active_threshold", 0.65))),
            ),
            computer_object_labels=_normalized_label_set(
                payload.get(
                    "computer_work_screen_object_labels",
                    _DEFAULT_COMPUTER_OBJECT_LABELS,
                ),
                fallback=_DEFAULT_COMPUTER_OBJECT_LABELS,
            ),
            phone_object_labels=_normalized_label_set(
                payload.get(
                    "computer_work_phone_object_labels",
                    _DEFAULT_PHONE_OBJECT_LABELS,
                ),
                fallback=_DEFAULT_PHONE_OBJECT_LABELS,
            ),
            downward_attention_penalty=max(
                0.0,
                float(payload.get("computer_work_downward_attention_penalty", 0.16)),
            ),
            explicit_screen_downward_penalty_multiplier=max(
                0.0,
                float(payload.get("computer_work_explicit_screen_downward_penalty_multiplier", 0.35)),
            ),
            explicit_screen_attention_recovery_bonus=max(
                0.0,
                float(payload.get("computer_work_explicit_screen_attention_recovery_bonus", 0.08)),
            ),
        )

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
            if obj.label.strip().lower() in self.computer_object_labels
        )
        phone_objects = tuple(
            obj
            for obj in perception.objects
            if obj.label.strip().lower() in self.phone_object_labels
        )

        engagement_face_count = perception.scene.engagement_face_count
        handheld_candidate_count = perception.scene.handheld_candidate_count
        screen_candidate_count = perception.scene.screen_candidate_count
        phone_like_evidence = handheld_candidate_count > 0 or bool(phone_objects)
        downward_attention_proxy = has_downward_attention_proxy(perception)
        explicit_screen_evidence = screen_candidate_count > 0 or bool(computer_objects)

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

        applied_downward_penalty = 0.0
        if downward_attention_proxy:
            reasons.append("downward_attention_proxy")
            applied_downward_penalty = self.downward_attention_penalty
            if explicit_screen_evidence:
                applied_downward_penalty *= self.explicit_screen_downward_penalty_multiplier
                reasons.append("explicit_screen_evidence_softens_downward_attention")
            confidence -= applied_downward_penalty

        if (
            desk_activity.active
            and engagement_face_count > 0
            and not phone_like_evidence
            and not downward_attention_proxy
        ):
            reasons.append("desk_screen_posture_proxy")
            confidence += 0.18

        if (
            explicit_screen_evidence
            and not phone_like_evidence
            and downward_attention_proxy
        ):
            reasons.append("explicit_screen_attention_recovery")
            confidence += self.explicit_screen_attention_recovery_bonus

        if phone_like_evidence:
            reasons.append("phone_like_evidence_present")
            confidence -= 0.20
        else:
            reasons.append("no_phone_like_evidence")
            confidence += 0.06

        inference_mode = "inactive"
        if explicit_screen_evidence:
            inference_mode = "hybrid"
        elif desk_activity.active and engagement_face_count > 0 and not downward_attention_proxy:
            inference_mode = "desk_face_proxy"
        elif downward_attention_proxy:
            inference_mode = "suppressed_downward_attention"

        active = confidence >= self.active_threshold

        return ActivitySignal(
            active=active,
            confidence=confidence,
            reasons=tuple(reasons),
            metadata={
                "computer_object_count": len(computer_objects),
                "screen_candidate_count": screen_candidate_count,
                "engagement_face_count": engagement_face_count,
                "phone_like_evidence": phone_like_evidence,
                "downward_attention_proxy": downward_attention_proxy,
                "downward_attention_penalty_applied": applied_downward_penalty,
                "inference_mode": inference_mode,
                "active_threshold": self.active_threshold,
                "explicit_screen_downward_penalty_multiplier": self.explicit_screen_downward_penalty_multiplier,
                "explicit_screen_attention_recovery_bonus": self.explicit_screen_attention_recovery_bonus,
            },
        )