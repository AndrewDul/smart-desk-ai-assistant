from __future__ import annotations

import unittest

from modules.devices.vision.behavior import ActivitySignal, BehaviorSnapshot
from modules.devices.vision.capture import FramePacket
from modules.devices.vision.diagnostics import build_diagnostics_snapshot
from modules.devices.vision.perception.models import (
    BoundingBox,
    FaceDetection,
    ObjectDetection,
    PerceptionSnapshot,
    PersonDetection,
    SceneContext,
)
from modules.devices.vision.sessions.models import ActivitySessionSnapshot, VisionSessionSnapshot


class DiagnosticsSnapshotBuilderTests(unittest.TestCase):
    def test_builds_raw_and_stable_signal_comparison_with_scene_and_sessions(self) -> None:
        packet = FramePacket(
            pixels=[[0]],
            width=1280,
            height=720,
            channels=3,
            backend_label="picamera2",
            captured_at=123.45,
            metadata={"camera_index": 0},
        )
        perception = PerceptionSnapshot(
            frame_width=1280,
            frame_height=720,
            people=(
                PersonDetection(
                    bounding_box=BoundingBox(100, 120, 320, 700),
                    confidence=0.61,
                ),
            ),
            faces=(
                FaceDetection(
                    bounding_box=BoundingBox(220, 90, 360, 250),
                    confidence=0.84,
                ),
            ),
            objects=(
                ObjectDetection(
                    label="phone",
                    bounding_box=BoundingBox(700, 400, 820, 620),
                    confidence=0.76,
                ),
            ),
            scene=SceneContext(
                desk_zone_people_count=1,
                engagement_face_count=1,
                screen_candidate_count=0,
                handheld_candidate_count=1,
                labels=("face_in_engagement_zone",),
                metadata={
                    "zone_layout": {
                        "desk_zone": {"x_min": 0.12, "y_min": 0.32, "x_max": 0.88, "y_max": 0.98},
                    }
                },
            ),
        )
        raw_behavior = BehaviorSnapshot(
            presence=ActivitySignal(active=True, confidence=0.84, reasons=("face_detected",), metadata={"source": "face"}),
            desk_activity=ActivitySignal(active=True, confidence=0.7, reasons=("face_in_engagement_zone",)),
            phone_usage=ActivitySignal(active=False, confidence=0.4, reasons=("awaiting_object_confirmation",)),
        )
        stabilized_behavior = BehaviorSnapshot(
            presence=ActivitySignal(
                active=True,
                confidence=0.84,
                reasons=("face_detected",),
                metadata={
                    "stable_active": True,
                    "raw_active": True,
                    "consecutive_positive_hits": 2,
                },
            ),
            desk_activity=ActivitySignal(
                active=True,
                confidence=0.7,
                reasons=("face_in_engagement_zone",),
                metadata={
                    "stable_active": True,
                    "raw_active": True,
                    "consecutive_positive_hits": 2,
                },
            ),
            phone_usage=ActivitySignal(
                active=True,
                confidence=0.55,
                reasons=("stability_hold_active",),
                metadata={
                    "stable_active": True,
                    "raw_active": False,
                    "consecutive_negative_hits": 1,
                    "last_positive_at": 123.0,
                },
            ),
        )
        sessions = VisionSessionSnapshot(
            presence=ActivitySessionSnapshot(active=True, state="active", current_active_seconds=8.5, total_active_seconds=20.0, activations=1),
            desk_activity=ActivitySessionSnapshot(active=True, state="active", current_active_seconds=7.0, total_active_seconds=15.0, activations=1),
            phone_usage=ActivitySessionSnapshot(active=True, state="active", current_active_seconds=2.0, total_active_seconds=3.0, activations=1),
            metadata={"tracker_version": 1},
        )

        snapshot = build_diagnostics_snapshot(
            packet,
            perception=perception,
            raw_behavior=raw_behavior,
            behavior=stabilized_behavior,
            sessions=sessions,
        )
        payload = snapshot.to_dict()

        self.assertEqual(payload["frame"]["backend"], "picamera2")
        self.assertEqual(payload["summary"]["people_count"], 1)
        self.assertEqual(payload["summary"]["face_count"], 1)
        self.assertEqual(payload["signals"]["presence"]["raw_active"], True)
        self.assertEqual(payload["signals"]["presence"]["stable_active"], True)
        self.assertEqual(payload["signals"]["phone_usage"]["raw_active"], False)
        self.assertEqual(payload["signals"]["phone_usage"]["stable_active"], True)
        self.assertIn("stability_hold_active", payload["signals"]["phone_usage"]["stable_reasons"])
        self.assertEqual(payload["scene"]["engagement_face_count"], 1)
        self.assertEqual(payload["detections"]["faces"][0]["kind"], "face")
        self.assertEqual(payload["sessions"]["presence"]["current_active_seconds"], 8.5)


if __name__ == "__main__":
    unittest.main()