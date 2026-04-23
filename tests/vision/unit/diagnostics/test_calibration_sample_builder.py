from __future__ import annotations

import unittest

from modules.devices.vision.diagnostics import (
    DiagnosticsDetection,
    DiagnosticsSignal,
    DiagnosticsSnapshot,
    build_calibration_sample,
)


class CalibrationSampleBuilderTests(unittest.TestCase):
    def test_build_calibration_sample_extracts_object_labels_and_inference_modes(self) -> None:
        snapshot = DiagnosticsSnapshot(
            frame={
                "width": 1280,
                "height": 720,
                "channels": 3,
                "captured_at": 123.45,
                "backend": "picamera2",
                "capture_metadata": {},
            },
            signals={
                "computer_work": DiagnosticsSignal(
                    name="computer_work",
                    raw_active=True,
                    stable_active=True,
                    raw_confidence=0.62,
                    stable_confidence=0.71,
                    raw_reasons=("desk_face_proxy",),
                    stable_reasons=("desk_face_proxy",),
                    metadata={
                        "inference_mode": "desk_face_proxy",
                        "raw_metadata": {
                            "inference_mode": "desk_face_proxy",
                        },
                    },
                ),
                "phone_usage": DiagnosticsSignal(
                    name="phone_usage",
                    raw_active=False,
                    stable_active=False,
                    raw_confidence=0.0,
                    stable_confidence=0.0,
                    raw_reasons=("phone_visual_evidence_missing",),
                    stable_reasons=("phone_visual_evidence_missing",),
                    metadata={
                        "inference_mode": "inactive_no_visual_evidence",
                        "raw_metadata": {
                            "inference_mode": "inactive_no_visual_evidence",
                        },
                    },
                ),
                "study_activity": DiagnosticsSignal(
                    name="study_activity",
                    raw_active=True,
                    stable_active=True,
                    raw_confidence=0.69,
                    stable_confidence=0.74,
                    raw_reasons=("computer_work_confirmed",),
                    stable_reasons=("computer_work_confirmed",),
                    metadata={
                        "inference_mode": "computer_work_supported",
                        "raw_metadata": {
                            "inference_mode": "computer_work_supported",
                        },
                    },
                ),
            },
            detections={
                "people": (),
                "faces": (),
                "objects": (
                    DiagnosticsDetection(
                        kind="object",
                        label="cup",
                        confidence=0.88,
                        bounding_box={"left": 10, "top": 10, "right": 40, "bottom": 50},
                    ),
                    DiagnosticsDetection(
                        kind="object",
                        label="laptop",
                        confidence=0.91,
                        bounding_box={"left": 100, "top": 120, "right": 500, "bottom": 360},
                    ),
                    DiagnosticsDetection(
                        kind="object",
                        label="cup",
                        confidence=0.86,
                        bounding_box={"left": 60, "top": 20, "right": 90, "bottom": 55},
                    ),
                ),
            },
            scene={
                "labels": ["camera_online"],
                "desk_zone_people_count": 1,
                "engagement_face_count": 1,
                "screen_candidate_count": 1,
                "handheld_candidate_count": 0,
                "metadata": {},
            },
            sessions={},
            summary={
                "user_present": True,
                "desk_active": True,
                "computer_work_likely": True,
                "on_phone_likely": False,
                "studying_likely": True,
                "people_count": 0,
                "face_count": 0,
                "object_count": 3,
            },
        )

        sample = build_calibration_sample(
            capture_tag="desk-laptop",
            diagnostics=snapshot,
        ).to_dict()

        self.assertEqual(sample["capture_tag"], "desk-laptop")
        self.assertEqual(sample["backend"], "picamera2")
        self.assertEqual(sample["counts"], {"people": 0, "faces": 0, "objects": 3})
        self.assertEqual(sample["object_labels"], ["cup", "laptop"])
        self.assertEqual(
            sample["signals"]["computer_work"]["stable_inference_mode"],
            "desk_face_proxy",
        )
        self.assertEqual(
            sample["signals"]["phone_usage"]["stable_inference_mode"],
            "inactive_no_visual_evidence",
        )
        self.assertEqual(
            sample["signals"]["study_activity"]["stable_inference_mode"],
            "computer_work_supported",
        )


if __name__ == "__main__":
    unittest.main()