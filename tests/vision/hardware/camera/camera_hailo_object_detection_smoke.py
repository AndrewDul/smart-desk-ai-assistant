"""
Hardware smoke test — Hailo YOLOv11 object detector on a real desk camera.

Run manually on Pi:
    sudo systemctl stop nexa.service
    PYTHONPATH=. python tests/vision/hardware/camera/camera_hailo_object_detection_smoke.py
    sudo systemctl start nexa.service

Expected output:
    - Hailo object detector initializes on first inference
    - last_timing_ms becomes populated
    - object_count > 0 on multiple sampled frames
    - labels reflect visible desk scene items when they are in frame
"""
from __future__ import annotations

import sys
import time
from collections import Counter

from modules.devices.vision.camera_service.service import CameraService


MEASURE_SECONDS = 12.0
SAMPLE_INTERVAL = 0.5
MIN_FRAMES_WITH_OBJECTS = 3


def _sep(char: str = "-", width: int = 72) -> None:
    print(char * width)


def _format_labels(labels: list[str]) -> str:
    return ", ".join(labels[:4]) if labels else "-"


def main() -> int:
    _sep("=")
    print("NeXa Vision — Hailo YOLO Object Detection Smoke Test")
    _sep("=")

    config = {
        "enabled": True,
        "backend": "picamera2",
        "fallback_backend": "opencv",
        "camera_index": 0,
        "frame_width": 1280,
        "frame_height": 720,
        "lazy_start": True,
        "continuous_capture_enabled": True,
        "continuous_capture_target_fps": 10.0,
        "people_detection_enabled": True,
        "people_detector_backend": "hybrid_face_primary",
        "face_detection_enabled": True,
        "face_detector_backend": "opencv_haar",
        "object_detection_enabled": True,
        "object_detector_backend": "hailo_yolov11",
        "object_detector_hailo_hef_path": "/usr/share/hailo-models/yolov11m_h10.hef",
        "object_detector_hailo_score_threshold": 0.35,
        "object_detector_hailo_max_detections": 30,
        "object_detector_hailo_initial_cadence_hz": 2.0,
        "object_detector_hailo_desk_relevant_only": False,
    }

    service = CameraService(config=config)

    print("[1] Starting CameraService...")
    service.start()

    detector = getattr(service._perception, "object_detector", None)
    detector_status_fn = getattr(detector, "status", None)

    status = service.status()
    print(f"[config] backend                 : {status.get('backend')}")
    print(f"[config] continuous_capture      : {status.get('continuous_capture_enabled')}")
    print(f"[config] detectors               : {status.get('detectors')}")
    if callable(detector_status_fn):
        print(f"[config] initial object status   : {detector_status_fn()}")
    _sep()

    print(f"[2] Keep your real desk scene visible for {MEASURE_SECONDS:.0f}s...")
    print("    (monitor / laptop / keyboard / mouse / phone / book etc.)")
    _sep()

    deadline = time.monotonic() + MEASURE_SECONDS
    frames_sampled = 0
    frames_with_objects = 0
    label_counts: Counter[str] = Counter()
    initialized_at_least_once = False
    last_status: dict[str, object] = {}
    last_print_at = 0.0

    while time.monotonic() < deadline:
        observation = service.latest_observation(force_refresh=True)
        if observation is None:
            time.sleep(SAMPLE_INTERVAL)
            continue

        frames_sampled += 1
        perception = observation.metadata.get("perception", {}) or {}
        objects = perception.get("objects", []) or []

        labels: list[str] = []
        for obj in objects:
            label = str(obj.get("label", "")).strip().lower()
            if label:
                labels.append(label)

        if objects:
            frames_with_objects += 1
            label_counts.update(labels)

        if callable(detector_status_fn):
            last_status = detector_status_fn() or {}
            initialized_at_least_once = initialized_at_least_once or bool(
                last_status.get("initialized")
            )

        now = time.monotonic()
        if now - last_print_at >= 1.0:
            timing = (last_status.get("last_timing_ms") if last_status else {}) or {}
            print(
                f"  [sample] object_count={len(objects)} "
                f"labels={_format_labels(labels)} "
                f"initialized={last_status.get('initialized') if last_status else 'n/a'} "
                f"timing={timing}"
            )
            last_print_at = now

        time.sleep(SAMPLE_INTERVAL)

    _sep()
    print(f"[result] frames sampled              : {frames_sampled}")
    print(f"[result] frames with objects         : {frames_with_objects}")
    print(f"[result] detector initialized        : {initialized_at_least_once}")
    print(
        "[result] label frequency             : "
        + (
            ", ".join(f"{label}:{count}" for label, count in label_counts.most_common(10))
            if label_counts
            else "-"
        )
    )
    print(f"[result] final detector status       : {last_status}")

    initialized_ok = initialized_at_least_once
    objects_ok = frames_with_objects >= MIN_FRAMES_WITH_OBJECTS

    _sep()
    if initialized_ok:
        print("[PASS] Hailo detector initialized successfully")
    else:
        print("[FAIL] Hailo detector never reported initialized=True")

    if objects_ok:
        print(
            f"[PASS] objects detected on {frames_with_objects} frames "
            f"(min {MIN_FRAMES_WITH_OBJECTS})"
        )
    else:
        print(
            f"[FAIL] only {frames_with_objects} frames with objects "
            f"(min {MIN_FRAMES_WITH_OBJECTS})"
        )

    print("[3] Closing CameraService...")
    service.close()
    _sep("=")

    return 0 if initialized_ok and objects_ok else 1


if __name__ == "__main__":
    sys.exit(main())