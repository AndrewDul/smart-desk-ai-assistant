# tests/vision/hardware/camera/camera_hailo_yolo_smoke.py
"""
Hardware smoke test — HailoYoloObjectDetector on real camera + yolov11m_h10.hef.

Prerequisites:
    - /dev/hailo0 visible
    - hailo_platform installed (hailortcli scan should show a device)
    - /usr/share/hailo-models/yolov11m_h10.hef present
    - nexa.service stopped before running this test

Run:
    sudo systemctl stop nexa.service
    PYTHONPATH=. python tests/vision/hardware/camera/camera_hailo_yolo_smoke.py
    sudo systemctl start nexa.service

Sit in front of the camera during the measurement window with some objects
visible (person, phone, laptop, cup, etc.).

Expected output:
    - HailoDeviceManager opens /dev/hailo0 successfully
    - HEF loads without error
    - At least MIN_INFERENCE_CYCLES inference cycles complete
    - timing_ms dict is populated (preprocess, inference, postprocess)
    - At least MIN_FRAMES_WITH_OBJECTS frames report object_count > 0
    - All detected labels are valid COCO class names
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any

from modules.devices.vision.perception.objects.coco_labels import COCO_LABELS

HEF_PATH = "/usr/share/hailo-models/yolov11m_h10.hef"
MEASURE_SECONDS = 15.0
SAMPLE_INTERVAL = 0.5
INFERENCE_CADENCE_HZ = 2.0
MIN_INFERENCE_CYCLES = 3
MIN_FRAMES_WITH_OBJECTS = 1


def _sep(char: str = "-", width: int = 62) -> None:
    print(char * width)


def _check_prerequisites() -> bool:
    ok = True
    if not os.path.exists("/dev/hailo0"):
        print("[FAIL] /dev/hailo0 not found — is the AI HAT+ 2 connected?")
        ok = False
    else:
        print("[OK]   /dev/hailo0 present")

    if not os.path.exists(HEF_PATH):
        print(f"[FAIL] HEF not found: {HEF_PATH}")
        ok = False
    else:
        size_mb = os.path.getsize(HEF_PATH) / 1_048_576
        print(f"[OK]   HEF present ({size_mb:.1f} MB): {HEF_PATH}")

    return ok


def main() -> int:
    _sep("=")
    print("NeXa Vision — HailoYoloObjectDetector Hardware Smoke Test")
    _sep("=")

    print("\n[Phase 1] Pre-flight checks")
    _sep()
    if not _check_prerequisites():
        print("\n[ABORT] Prerequisites not met.")
        return 1

    # Import after pre-flight to avoid hailo init errors before checks.
    from modules.devices.vision.camera_service.service import CameraService

    config: dict[str, Any] = {
        "enabled": True,
        "continuous_capture_enabled": True,
        "continuous_capture_target_fps": 10.0,
        "people_detection_enabled": True,
        "people_detector_backend": "hybrid_face_primary",
        "face_detection_enabled": True,
        "face_detector_backend": "opencv_haar",
        "object_detection_enabled": True,
        "object_detector_backend": "hailo_yolov11",
        "object_detector_hailo_hef_path": HEF_PATH,
        "object_detector_hailo_score_threshold": 0.35,
        "object_detector_hailo_max_detections": 30,
        "object_detector_hailo_initial_cadence_hz": INFERENCE_CADENCE_HZ,
        "object_detector_hailo_desk_relevant_only": False,
        "lazy_start": True,
    }

    service = CameraService(config=config)

    print("\n[Phase 2] Starting CameraService with Hailo object detection")
    _sep()
    service.start()

    svc_status = service.status()
    print(f"[config] backend            : {svc_status.get('backend')}")
    print(f"[config] continuous_capture : {svc_status.get('continuous_capture_enabled')}")
    print(f"[config] detectors          : {svc_status.get('detectors')}")

    _sep()
    print(f"\n[Phase 3] Measuring for {MEASURE_SECONDS:.0f}s  (inference ~{INFERENCE_CADENCE_HZ:.0f} Hz)")
    print("         Sit in front of the camera with objects visible.\n")

    total_samples = 0
    frames_with_objects = 0
    all_labels_seen: set[str] = set()
    timing_samples: list[dict[str, float]] = []

    # COCO class names for validation — values of COCO_LABELS dict.
    valid_coco_names: set[str] = set(COCO_LABELS.values())

    deadline = time.monotonic() + MEASURE_SECONDS

    while time.monotonic() < deadline:
        time.sleep(SAMPLE_INTERVAL)

        obs = service.latest_observation()
        if obs is None:
            print("  [--] observation=None (capture not ready yet)")
            continue

        total_samples += 1

        # Objects are in obs.metadata["perception"]["objects"] as list of dicts.
        perception_meta: dict = obs.metadata.get("perception", {})
        object_count: int = perception_meta.get("object_count", 0)
        raw_objects: list[dict] = perception_meta.get("objects", [])

        if object_count > 0:
            frames_with_objects += 1
            for obj in raw_objects:
                label = obj.get("label", "")
                if label:
                    all_labels_seen.add(label)

        # Collect timing from the detector status.
        det_status = service.object_detector_status()
        if det_status:
            timing = det_status.get("last_timing_ms", {})
            if timing.get("inference_ms", 0.0) > 0.0:
                timing_samples.append(timing)

        # Object labels for progress readout (from observation.labels "object:X" form).
        obj_label_str = ", ".join(sorted(all_labels_seen)[:5]) or "(none yet)"
        initialized = det_status.get("initialized", "?") if det_status else "?"
        paused = det_status.get("paused", "?") if det_status else "?"
        print(
            f"  sample={total_samples:3d}  "
            f"objects={object_count:2d}  "
            f"seen=[{obj_label_str}]  "
            f"inferences_collected={len(timing_samples)}  "
            f"hailo_init={initialized}  paused={paused}"
        )

    _sep()
    print("\n[Phase 4] Results")
    _sep()

    inferences_run = len(timing_samples)
    print(f"  total_samples         : {total_samples}")
    print(f"  inference_cycles_run  : {inferences_run}")
    print(f"  frames_with_objects   : {frames_with_objects}")
    print(f"  unique_labels_seen    : {sorted(all_labels_seen)}")

    if timing_samples:
        avg_pre   = sum(t.get("preprocess_ms", 0.0) for t in timing_samples) / len(timing_samples)
        avg_inf   = sum(t.get("inference_ms", 0.0) for t in timing_samples) / len(timing_samples)
        avg_post  = sum(t.get("postprocess_ms", 0.0) for t in timing_samples) / len(timing_samples)
        print(f"\n  avg_preprocess_ms     : {avg_pre:.1f}")
        print(f"  avg_inference_ms      : {avg_inf:.1f}")
        print(f"  avg_postprocess_ms    : {avg_post:.1f}")
        print(f"  avg_total_cycle_ms    : {avg_pre + avg_inf + avg_post:.1f}")

    invalid_labels = {lbl for lbl in all_labels_seen if lbl not in valid_coco_names}

    _sep()
    print("\n[Phase 5] Pass / Fail")
    _sep()

    passed = True

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal passed
        tag = "PASS" if condition else "FAIL"
        suffix = f"  ({detail})" if detail else ""
        print(f"  [{tag}] {name}{suffix}")
        if not condition:
            passed = False

    check("At least one observation returned", total_samples > 0)
    check(
        f"At least {MIN_INFERENCE_CYCLES} inference cycles completed",
        inferences_run >= MIN_INFERENCE_CYCLES,
        f"got {inferences_run}",
    )
    check(
        f"At least {MIN_FRAMES_WITH_OBJECTS} frames with objects > 0",
        frames_with_objects >= MIN_FRAMES_WITH_OBJECTS,
        f"got {frames_with_objects}",
    )
    check(
        "All detected labels are valid COCO class names",
        len(invalid_labels) == 0,
        f"invalid={sorted(invalid_labels)}" if invalid_labels else "ok",
    )
    check(
        "timing_ms populated (inference_ms > 0)",
        len(timing_samples) > 0,
    )

    _sep()
    verdict = "SMOKE TEST PASSED" if passed else "SMOKE TEST FAILED"
    print(f"\n  [{verdict}]")
    if not passed:
        print("  Check FAIL lines above. Common issues:")
        print("    - inferences=0 -> check /dev/hailo0, hef path, hailo_platform install")
        print("    - objects=0    -> move closer, check score_threshold (0.35 ok)")
        print("    - timing empty -> inference didn't complete (check hailo service logs)")
    _sep("=")

    print("\n[Phase 6] Stopping CameraService...")
    service.stop()
    print("Done.\n")

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())