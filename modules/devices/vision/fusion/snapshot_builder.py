from __future__ import annotations

from modules.devices.vision.capture import FramePacket
from modules.devices.vision.perception import PerceptionSnapshot
from modules.runtime.contracts import VisionObservation


def build_vision_observation(
    packet: FramePacket,
    perception: PerceptionSnapshot | None = None,
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

    user_present = False
    desk_active = False
    confidence = 1.0

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

        user_present = bool(perception.people) or perception.scene.desk_zone_people_count > 0
        desk_active = perception.scene.desk_zone_people_count > 0

        signal_confidences = [person.confidence for person in perception.people]
        signal_confidences.extend(obj.confidence for obj in perception.objects)
        if signal_confidences:
            confidence = max(0.0, min(1.0, max(signal_confidences)))

        labels.append("perception_ready")
    else:
        metadata["perception"] = {
            "people_count": 0,
            "object_count": 0,
            "desk_zone_people_count": 0,
            "screen_candidate_count": 0,
            "handheld_candidate_count": 0,
        }

    return VisionObservation(
        detected=True,
        user_present=user_present,
        studying_likely=False,
        on_phone_likely=False,
        desk_active=desk_active,
        labels=labels,
        confidence=confidence,
        captured_at=packet.captured_at,
        metadata=metadata,
    )


def build_camera_only_observation(packet: FramePacket) -> VisionObservation:
    return build_vision_observation(packet=packet, perception=None)