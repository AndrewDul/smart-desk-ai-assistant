from __future__ import annotations

from modules.devices.vision.capture import FramePacket
from modules.runtime.contracts import VisionObservation


def build_camera_only_observation(packet: FramePacket) -> VisionObservation:
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

    return VisionObservation(
        detected=True,
        user_present=False,
        studying_likely=False,
        on_phone_likely=False,
        desk_active=False,
        labels=["camera_online", f"capture_backend:{packet.backend_label}"],
        confidence=1.0,
        captured_at=packet.captured_at,
        metadata=metadata,
    )