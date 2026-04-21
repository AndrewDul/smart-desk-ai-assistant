from __future__ import annotations

from modules.devices.vision.behavior import BehaviorSnapshot
from modules.devices.vision.capture import FramePacket
from modules.devices.vision.perception import PerceptionSnapshot
from modules.runtime.contracts import VisionObservation


def _signal_to_dict(signal) -> dict[str, object]:
    return {
        "active": signal.active,
        "confidence": signal.confidence,
        "reasons": list(signal.reasons),
        "metadata": dict(signal.metadata),
    }


def build_vision_observation(
    packet: FramePacket,
    perception: PerceptionSnapshot | None = None,
    behavior: BehaviorSnapshot | None = None,
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
    return build_vision_observation(packet=packet, perception=None, behavior=None)