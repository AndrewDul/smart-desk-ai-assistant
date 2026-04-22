from __future__ import annotations

from modules.devices.vision.behavior import BehaviorSnapshot
from modules.devices.vision.capture import FramePacket
from modules.devices.vision.diagnostics.models import (
    DiagnosticsDetection,
    DiagnosticsSignal,
    DiagnosticsSnapshot,
)
from modules.devices.vision.perception import PerceptionSnapshot
from modules.devices.vision.sessions import VisionSessionSnapshot


_SIGNAL_NAMES = (
    "presence",
    "desk_activity",
    "computer_work",
    "phone_usage",
    "study_activity",
)


def _box_to_dict(box) -> dict[str, int]:
    return {
        "left": box.left,
        "top": box.top,
        "right": box.right,
        "bottom": box.bottom,
        "width": box.width,
        "height": box.height,
    }


def _build_signal(
    name: str,
    raw_signal,
    stable_signal,
) -> DiagnosticsSignal:
    metadata = dict(stable_signal.metadata)
    metadata["raw_metadata"] = dict(raw_signal.metadata)

    return DiagnosticsSignal(
        name=name,
        raw_active=bool(raw_signal.active),
        stable_active=bool(stable_signal.active),
        raw_confidence=float(raw_signal.confidence),
        stable_confidence=float(stable_signal.confidence),
        raw_reasons=tuple(raw_signal.reasons),
        stable_reasons=tuple(stable_signal.reasons),
        metadata=metadata,
    )


def _build_detections(perception: PerceptionSnapshot) -> dict[str, tuple[DiagnosticsDetection, ...]]:
    return {
        "people": tuple(
            DiagnosticsDetection(
                kind="person",
                label=person.label,
                confidence=float(person.confidence),
                bounding_box=_box_to_dict(person.bounding_box),
                metadata=dict(person.metadata),
            )
            for person in perception.people
        ),
        "faces": tuple(
            DiagnosticsDetection(
                kind="face",
                label=face.label,
                confidence=float(face.confidence),
                bounding_box=_box_to_dict(face.bounding_box),
                metadata=dict(face.metadata),
            )
            for face in perception.faces
        ),
        "objects": tuple(
            DiagnosticsDetection(
                kind="object",
                label=obj.label,
                confidence=float(obj.confidence),
                bounding_box=_box_to_dict(obj.bounding_box),
                metadata=dict(obj.metadata),
            )
            for obj in perception.objects
        ),
    }


def _build_scene(perception: PerceptionSnapshot) -> dict[str, object]:
    return {
        "labels": list(perception.scene.labels),
        "desk_zone_people_count": perception.scene.desk_zone_people_count,
        "engagement_face_count": perception.scene.engagement_face_count,
        "screen_candidate_count": perception.scene.screen_candidate_count,
        "handheld_candidate_count": perception.scene.handheld_candidate_count,
        "metadata": dict(perception.scene.metadata),
    }


def _build_sessions(sessions: VisionSessionSnapshot) -> dict[str, object]:
    return {
        "presence": {
            "active": sessions.presence.active,
            "state": sessions.presence.state,
            "current_active_seconds": sessions.presence.current_active_seconds,
            "total_active_seconds": sessions.presence.total_active_seconds,
            "activations": sessions.presence.activations,
        },
        "desk_activity": {
            "active": sessions.desk_activity.active,
            "state": sessions.desk_activity.state,
            "current_active_seconds": sessions.desk_activity.current_active_seconds,
            "total_active_seconds": sessions.desk_activity.total_active_seconds,
            "activations": sessions.desk_activity.activations,
        },
        "computer_work": {
            "active": sessions.computer_work.active,
            "state": sessions.computer_work.state,
            "current_active_seconds": sessions.computer_work.current_active_seconds,
            "total_active_seconds": sessions.computer_work.total_active_seconds,
            "activations": sessions.computer_work.activations,
        },
        "phone_usage": {
            "active": sessions.phone_usage.active,
            "state": sessions.phone_usage.state,
            "current_active_seconds": sessions.phone_usage.current_active_seconds,
            "total_active_seconds": sessions.phone_usage.total_active_seconds,
            "activations": sessions.phone_usage.activations,
        },
        "study_activity": {
            "active": sessions.study_activity.active,
            "state": sessions.study_activity.state,
            "current_active_seconds": sessions.study_activity.current_active_seconds,
            "total_active_seconds": sessions.study_activity.total_active_seconds,
            "activations": sessions.study_activity.activations,
        },
        "metadata": dict(sessions.metadata),
    }


def build_diagnostics_snapshot(
    packet: FramePacket,
    *,
    perception: PerceptionSnapshot,
    raw_behavior: BehaviorSnapshot,
    behavior: BehaviorSnapshot,
    sessions: VisionSessionSnapshot,
) -> DiagnosticsSnapshot:
    signals = {
        name: _build_signal(
            name,
            getattr(raw_behavior, name),
            getattr(behavior, name),
        )
        for name in _SIGNAL_NAMES
    }

    return DiagnosticsSnapshot(
        frame={
            "width": packet.width,
            "height": packet.height,
            "channels": packet.channels,
            "captured_at": packet.captured_at,
            "backend": packet.backend_label,
            "capture_metadata": dict(packet.metadata),
        },
        signals=signals,
        detections=_build_detections(perception),
        scene=_build_scene(perception),
        sessions=_build_sessions(sessions),
        summary={
            "user_present": behavior.presence.active,
            "desk_active": behavior.desk_activity.active,
            "computer_work_likely": behavior.computer_work.active,
            "on_phone_likely": behavior.phone_usage.active,
            "studying_likely": behavior.study_activity.active,
            "people_count": len(perception.people),
            "face_count": len(perception.faces),
            "object_count": len(perception.objects),
        },
    )