from __future__ import annotations

from modules.devices.vision.behavior import BehaviorSnapshot
from modules.devices.vision.capture import FramePacket
from modules.devices.vision.perception import PerceptionSnapshot
from modules.devices.vision.sessions import VisionSessionSnapshot
from modules.runtime.contracts import VisionObservation


def _signal_to_dict(signal) -> dict[str, object]:
    return {
        "active": signal.active,
        "confidence": signal.confidence,
        "reasons": list(signal.reasons),
        "metadata": dict(signal.metadata),
    }


def _session_to_dict(session) -> dict[str, object]:
    return {
        "active": session.active,
        "state": session.state,
        "current_active_seconds": session.current_active_seconds,
        "last_active_streak_seconds": session.last_active_streak_seconds,
        "total_active_seconds": session.total_active_seconds,
        "activations": session.activations,
        "last_started_at": session.last_started_at,
        "last_ended_at": session.last_ended_at,
        "metadata": dict(session.metadata),
    }


def _box_to_dict(box) -> dict[str, int]:
    return {
        "left": box.left,
        "top": box.top,
        "right": box.right,
        "bottom": box.bottom,
        "width": box.width,
        "height": box.height,
    }


def _person_to_dict(person) -> dict[str, object]:
    return {
        "label": person.label,
        "confidence": person.confidence,
        "bounding_box": _box_to_dict(person.bounding_box),
        "metadata": dict(person.metadata),
    }


def _object_to_dict(obj) -> dict[str, object]:
    return {
        "label": obj.label,
        "confidence": obj.confidence,
        "bounding_box": _box_to_dict(obj.bounding_box),
        "metadata": dict(obj.metadata),
    }


def build_vision_observation(
    packet: FramePacket,
    perception: PerceptionSnapshot | None = None,
    behavior: BehaviorSnapshot | None = None,
    sessions: VisionSessionSnapshot | None = None,
) -> VisionObservation:
    metadata = dict(packet.metadata)
    metadata.update(
        {
            "frame_width": packet.width,
            "frame_height": packet.height,
            "frame_channels": packet.channels,
            "capture_backend": packet.backend_label,
            "camera_online": True,
        }
    )

    labels: list[str] = ["camera_online", f"capture_backend:{packet.backend_label}"]
    confidence = 1.0

    user_present = False
    desk_active = False
    on_phone_likely = False
    studying_likely = False
    computer_work_likely = False

    if perception is not None:
        object_labels = sorted({obj.label.strip().lower() for obj in perception.objects if obj.label.strip()})
        labels.extend(f"object:{label}" for label in object_labels)
        labels.extend(perception.scene.labels)

        metadata["perception"] = {
            "people_count": len(perception.people),
            "object_count": len(perception.objects),
            "people": [_person_to_dict(person) for person in perception.people],
            "objects": [_object_to_dict(obj) for obj in perception.objects],
            "detectors": dict(perception.metadata.get("detectors", {})),
            "desk_zone_people_count": perception.scene.desk_zone_people_count,
            "screen_candidate_count": perception.scene.screen_candidate_count,
            "handheld_candidate_count": perception.scene.handheld_candidate_count,
            "scene_metadata": perception.scene.metadata,
        }

        signal_confidences = [person.confidence for person in perception.people]
        signal_confidences.extend(obj.confidence for obj in perception.objects)
        if signal_confidences:
            confidence = max(0.0, min(1.0, max(signal_confidences)))
    else:
        metadata["perception"] = {
            "people_count": 0,
            "object_count": 0,
            "people": [],
            "objects": [],
            "detectors": {"people": "null", "objects": "null", "scene": "null"},
            "desk_zone_people_count": 0,
            "screen_candidate_count": 0,
            "handheld_candidate_count": 0,
        }

    if behavior is not None:
        user_present = behavior.presence.active
        desk_active = behavior.desk_activity.active
        computer_work_likely = behavior.computer_work.active
        on_phone_likely = behavior.phone_usage.active
        studying_likely = behavior.study_activity.active

        metadata["behavior"] = {
            "presence": _signal_to_dict(behavior.presence),
            "desk_activity": _signal_to_dict(behavior.desk_activity),
            "computer_work": _signal_to_dict(behavior.computer_work),
            "phone_usage": _signal_to_dict(behavior.phone_usage),
            "study_activity": _signal_to_dict(behavior.study_activity),
            "pipeline_metadata": dict(behavior.metadata),
        }

        if behavior.presence.active:
            labels.append("behavior:presence")
        if behavior.desk_activity.active:
            labels.append("behavior:desk_activity")
        if behavior.computer_work.active:
            labels.append("behavior:computer_work")
        if behavior.phone_usage.active:
            labels.append("behavior:phone_usage")
        if behavior.study_activity.active:
            labels.append("behavior:study_activity")

        behavior_confidences = [
            behavior.presence.confidence,
            behavior.desk_activity.confidence,
            behavior.computer_work.confidence,
            behavior.phone_usage.confidence,
            behavior.study_activity.confidence,
        ]
        confidence = max(confidence, max(behavior_confidences, default=0.0))
    else:
        metadata["behavior"] = {
            "presence": {"active": False, "confidence": 0.0, "reasons": [], "metadata": {}},
            "desk_activity": {"active": False, "confidence": 0.0, "reasons": [], "metadata": {}},
            "computer_work": {"active": False, "confidence": 0.0, "reasons": [], "metadata": {}},
            "phone_usage": {"active": False, "confidence": 0.0, "reasons": [], "metadata": {}},
            "study_activity": {"active": False, "confidence": 0.0, "reasons": [], "metadata": {}},
        }

    if sessions is not None:
        metadata["sessions"] = {
            "presence": _session_to_dict(sessions.presence),
            "desk_activity": _session_to_dict(sessions.desk_activity),
            "computer_work": _session_to_dict(sessions.computer_work),
            "phone_usage": _session_to_dict(sessions.phone_usage),
            "study_activity": _session_to_dict(sessions.study_activity),
            "tracker_metadata": dict(sessions.metadata),
        }

        if sessions.presence.active:
            labels.append("session:presence_active")
        if sessions.phone_usage.active:
            labels.append("session:phone_active")
        if sessions.study_activity.active:
            labels.append("session:study_active")
    else:
        metadata["sessions"] = {
            "presence": {
                "active": False,
                "state": "inactive",
                "current_active_seconds": 0.0,
                "last_active_streak_seconds": 0.0,
                "total_active_seconds": 0.0,
                "activations": 0,
                "last_started_at": None,
                "last_ended_at": None,
                "metadata": {},
            },
            "desk_activity": {
                "active": False,
                "state": "inactive",
                "current_active_seconds": 0.0,
                "last_active_streak_seconds": 0.0,
                "total_active_seconds": 0.0,
                "activations": 0,
                "last_started_at": None,
                "last_ended_at": None,
                "metadata": {},
            },
            "computer_work": {
                "active": False,
                "state": "inactive",
                "current_active_seconds": 0.0,
                "last_active_streak_seconds": 0.0,
                "total_active_seconds": 0.0,
                "activations": 0,
                "last_started_at": None,
                "last_ended_at": None,
                "metadata": {},
            },
            "phone_usage": {
                "active": False,
                "state": "inactive",
                "current_active_seconds": 0.0,
                "last_active_streak_seconds": 0.0,
                "total_active_seconds": 0.0,
                "activations": 0,
                "last_started_at": None,
                "last_ended_at": None,
                "metadata": {},
            },
            "study_activity": {
                "active": False,
                "state": "inactive",
                "current_active_seconds": 0.0,
                "last_active_streak_seconds": 0.0,
                "total_active_seconds": 0.0,
                "activations": 0,
                "last_started_at": None,
                "last_ended_at": None,
                "metadata": {},
            },
        }

    return VisionObservation(
        detected=True,
        user_present=user_present,
        studying_likely=studying_likely,
        on_phone_likely=on_phone_likely,
        computer_work_likely=computer_work_likely,
        desk_active=desk_active,
        labels=labels,
        confidence=confidence,
        captured_at=packet.captured_at,
        metadata=metadata,
    )


def build_camera_only_observation(packet: FramePacket) -> VisionObservation:
    return build_vision_observation(packet=packet, perception=None, behavior=None, sessions=None)