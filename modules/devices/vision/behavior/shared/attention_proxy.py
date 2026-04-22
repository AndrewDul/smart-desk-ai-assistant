from __future__ import annotations

from modules.devices.vision.perception.models import FaceDetection, PerceptionSnapshot


def has_downward_attention_proxy(perception: PerceptionSnapshot) -> bool:
    if not perception.faces or perception.frame_height <= 0:
        return False

    primary_face = max(
        perception.faces,
        key=lambda face: (face.confidence, face.bounding_box.height),
    )
    return face_suggests_downward_attention(primary_face, perception.frame_height)


def face_suggests_downward_attention(face: FaceDetection, frame_height: int) -> bool:
    normalized_center_y = face.bounding_box.center_y / frame_height
    normalized_bottom_y = face.bounding_box.bottom / frame_height
    return normalized_center_y >= 0.45 and normalized_bottom_y >= 0.60