from __future__ import annotations

from typing import Any

from modules.runtime.contracts import VisionObservation

from .models import FocusVisionEvidence


_PHONE_LABEL_NAMES: frozenset[str] = frozenset({
    "object:cell phone",
    "object:phone",
    "object:mobile phone",
    "object:smartphone",
    "phone",
    "cell phone",
    "mobile phone",
    "smartphone",
})


class FocusVisionObservationReader:
    """Extract focus-relevant evidence from the stable VisionObservation contract."""

    def read(self, observation: VisionObservation | None) -> FocusVisionEvidence:
        if observation is None:
            return FocusVisionEvidence(metadata={"reason": "missing_observation"})

        metadata = dict(getattr(observation, "metadata", {}) or {})
        behavior = dict(metadata.get("behavior") or {})
        sessions = dict(metadata.get("sessions") or {})
        perception = dict(metadata.get("perception") or {})

        presence = _signal(behavior, "presence")
        desk_activity = _signal(behavior, "desk_activity")
        computer_work = _signal(behavior, "computer_work")
        phone_usage = _signal(behavior, "phone_usage")
        study_activity = _signal(behavior, "study_activity")

        raw_face_count = _count_from_perception(perception, "face_count", "faces")
        raw_people_count = _count_from_perception(perception, "people_count", "people")

        obs_labels = tuple(str(label) for label in getattr(observation, "labels", []) or [])
        labels_set = frozenset(obs_labels)

        # YOLO person fallback: when Haar finds nothing and raw people detector returns 0,
        # bridge the YOLO "person" label into effective people_count so Focus Mode is not blind.
        yolo_person_count = 1 if "object:person" in labels_set else 0
        if raw_face_count == 0 and raw_people_count == 0 and yolo_person_count > 0:
            effective_people_count = 1
            person_without_face = True
            people_count_source = "yolo_person_fallback"
        elif raw_people_count > 0:
            effective_people_count = raw_people_count
            person_without_face = raw_people_count > 0 and raw_face_count == 0
            people_count_source = "raw_people"
        else:
            effective_people_count = 0
            person_without_face = False
            people_count_source = "none"

        # Phone candidate: any phone-like label regardless of person presence (for telemetry).
        phone_candidate_detected = bool(labels_set & _PHONE_LABEL_NAMES)
        phone_candidate_confidence = max(1.0, _confidence(phone_usage)) if phone_candidate_detected else 0.0

        # Phone bridge: YOLO labels are only meaningful when a person is also present,
        # so that a phone lying on an empty desk does not trigger phone distraction.
        person_evidence_present = effective_people_count > 0 or raw_face_count > 0
        phone_label_detected = bool(labels_set & _PHONE_LABEL_NAMES) and person_evidence_present
        phone_behavior_detected = _active_with_contract_fallback(phone_usage, getattr(observation, "on_phone_likely", False))
        phone_object_detected = phone_label_detected

        if phone_label_detected and phone_behavior_detected:
            phone_detection_source = "both"
        elif phone_label_detected:
            phone_detection_source = "yolo_object_label"
        elif phone_behavior_detected and person_evidence_present:
            phone_detection_source = "behavior_session"
        else:
            phone_detection_source = ""

        return FocusVisionEvidence(
            detected=bool(getattr(observation, "detected", False)),
            presence_active=_active_with_contract_fallback(presence, getattr(observation, "user_present", False)),
            desk_activity_active=_active_with_contract_fallback(desk_activity, getattr(observation, "desk_active", False)),
            computer_work_active=_active_with_contract_fallback(computer_work, getattr(observation, "computer_work_likely", False)),
            phone_usage_active=_active_with_contract_fallback(phone_usage, getattr(observation, "on_phone_likely", False)),
            study_activity_active=_active_with_contract_fallback(study_activity, getattr(observation, "studying_likely", False)),
            presence_confidence=_confidence(presence),
            desk_activity_confidence=_confidence(desk_activity),
            computer_work_confidence=_confidence(computer_work),
            phone_usage_confidence=_confidence(phone_usage),
            study_activity_confidence=_confidence(study_activity),
            presence_active_seconds=_active_seconds(_session(sessions, "presence")),
            desk_activity_active_seconds=_active_seconds(_session(sessions, "desk_activity")),
            computer_work_active_seconds=_active_seconds(_session(sessions, "computer_work")),
            phone_usage_active_seconds=_active_seconds(_session(sessions, "phone_usage")),
            study_activity_active_seconds=_active_seconds(_session(sessions, "study_activity")),
            captured_at=float(getattr(observation, "captured_at", 0.0) or 0.0),
            labels=obs_labels,
            metadata={
                "observation_confidence": float(getattr(observation, "confidence", 0.0) or 0.0),
                "behavior_available": bool(behavior),
                "sessions_available": bool(sessions),
                "perception_available": bool(perception),
            },
            face_count=raw_face_count,
            people_count=effective_people_count,
            person_without_face=person_without_face,
            yolo_person_count=yolo_person_count,
            phone_object_detected=phone_object_detected,
            people_count_source=people_count_source,
            phone_candidate_detected=phone_candidate_detected,
            phone_candidate_confidence=phone_candidate_confidence,
            phone_detection_source=phone_detection_source,
        )


def _signal(behavior: dict[str, Any], name: str) -> dict[str, Any]:
    value = behavior.get(name)
    return dict(value) if isinstance(value, dict) else {}


def _session(sessions: dict[str, Any], name: str) -> dict[str, Any]:
    value = sessions.get(name)
    return dict(value) if isinstance(value, dict) else {}


def _active_with_contract_fallback(signal: dict[str, Any], fallback: Any) -> bool:
    if "active" in signal:
        return bool(signal.get("active"))
    return bool(fallback)


def _confidence(signal: dict[str, Any]) -> float:
    try:
        value = float(signal.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        value = 0.0
    return max(0.0, min(1.0, value))


def _active_seconds(session: dict[str, Any]) -> float:
    try:
        return max(0.0, float(session.get("current_active_seconds", 0.0) or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _count_from_perception(perception: dict[str, Any], count_key: str, list_key: str) -> int:
    value = perception.get(count_key)
    if value is not None:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            pass
    items = perception.get(list_key)
    if isinstance(items, (list, tuple)):
        return len(items)
    return 0


__all__ = ["FocusVisionObservationReader"]
