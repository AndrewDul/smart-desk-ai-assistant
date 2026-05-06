from __future__ import annotations

from typing import Any

from modules.runtime.contracts import VisionObservation

from .models import FocusVisionEvidence


class FocusVisionObservationReader:
    """Extract focus-relevant evidence from the stable VisionObservation contract."""

    def read(self, observation: VisionObservation | None) -> FocusVisionEvidence:
        if observation is None:
            return FocusVisionEvidence(metadata={"reason": "missing_observation"})

        metadata = dict(getattr(observation, "metadata", {}) or {})
        behavior = dict(metadata.get("behavior") or {})
        sessions = dict(metadata.get("sessions") or {})

        presence = _signal(behavior, "presence")
        desk_activity = _signal(behavior, "desk_activity")
        computer_work = _signal(behavior, "computer_work")
        phone_usage = _signal(behavior, "phone_usage")
        study_activity = _signal(behavior, "study_activity")

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
            labels=tuple(str(label) for label in getattr(observation, "labels", []) or []),
            metadata={
                "observation_confidence": float(getattr(observation, "confidence", 0.0) or 0.0),
                "behavior_available": bool(behavior),
                "sessions_available": bool(sessions),
            },
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


__all__ = ["FocusVisionObservationReader"]
