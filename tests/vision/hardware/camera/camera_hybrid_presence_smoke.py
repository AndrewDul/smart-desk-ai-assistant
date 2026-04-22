# tests/vision/hardware/camera/camera_hybrid_presence_smoke.py
"""
Hardware smoke test — Hybrid Face-Primary People Detector on a real camera.

Run manually on Pi:
    PYTHONPATH=. python tests/vision/hardware/camera/camera_hybrid_presence_smoke.py

Sit in front of the desk camera during the measurement window.

Expected output:
    - Worker starts, pipeline uses hybrid_face_primary backend
    - Over 10 seconds of capture, face_count > 0 and people_count > 0
      on a majority of frames where the user is actually visible
    - Projected person boxes are reported with source=face_projected
"""
from __future__ import annotations

import sys
import time

from modules.devices.vision.camera_service.service import CameraService


MEASURE_SECONDS = 10.0
SAMPLE_INTERVAL = 0.5
MIN_FRAMES_WITH_FACE = 5
MIN_FRAMES_WITH_PERSON = 5


def _sep(char: str = "-", width: int = 60) -> None:
    print(char * width)


def main() -> int:
    _sep("=")
    print("NeXa Vision — Hybrid Face-Primary Presence Smoke Test")
    _sep("=")

    config = {
        "enabled": True,
        "continuous_capture_enabled": True,
        "continuous_capture_target_fps": 10.0,
        "people_detection_enabled": True,
        "people_detector_backend": "hybrid_face_primary",
        "face_detection_enabled": True,
        "face_detector_backend": "opencv_haar",
        "lazy_start": True,
    }

    service = CameraService(config=config)

    print("[1] Starting CameraService...")
    service.start()

    status = service.status()
    print(f"[config] backend            : {status.get('backend')}")
    print(f"[config] continuous_capture : {status.get('continuous_capture_enabled')}")
    print(f"[config] detectors          : {status.get('detectors')}")
    _sep()

    print(f"[2] Sit in front of the camera. Measuring for {MEASURE_SECONDS:.0f}s...")
    print("    (sampling detections twice per second)")
    _sep()

    deadline = time.monotonic() + MEASURE_SECONDS
    frames_sampled = 0
    frames_with_face = 0
    frames_with_person = 0
    frames_with_face_projected = 0
    frames_with_merged = 0
    last_print_at = 0.0

    while time.monotonic() < deadline:
        observation = service.latest_observation(force_refresh=True)
        if observation is None:
            time.sleep(SAMPLE_INTERVAL)
            continue

        frames_sampled += 1
        diagnostics = observation.metadata.get("diagnostics", {}) or {}
        detections = diagnostics.get("detections", {}) or {}
        people = detections.get("people", []) or []
        faces = detections.get("faces", []) or []

        if faces:
            frames_with_face += 1
        if people:
            frames_with_person += 1

        for person in people:
            meta = person.get("metadata", {}) if isinstance(person, dict) else {}
            if meta.get("source") == "face_projected":
                frames_with_face_projected += 1
                break
        for person in people:
            meta = person.get("metadata", {}) if isinstance(person, dict) else {}
            if meta.get("source") == "hog+face":
                frames_with_merged += 1
                break

        now = time.monotonic()
        if now - last_print_at >= 1.0:
            print(
                f"  [sample] face_count={len(faces)} "
                f"person_count={len(people)} "
                f"user_present={observation.user_present} "
                f"desk_active={observation.desk_active}"
            )
            last_print_at = now

        time.sleep(SAMPLE_INTERVAL)

    _sep()
    print(f"[result] frames sampled              : {frames_sampled}")
    print(f"[result] frames with face detected   : {frames_with_face}")
    print(f"[result] frames with person detected : {frames_with_person}")
    print(f"[result] frames with face_projected  : {frames_with_face_projected}")
    print(f"[result] frames with hog+face merged : {frames_with_merged}")

    worker_stats = (service.status().get("worker") or {})
    print(f"[result] capture frames total        : {worker_stats.get('frames_captured')}")
    print(f"[result] capture consecutive errors  : {worker_stats.get('consecutive_errors')}")

    face_ok = frames_with_face >= MIN_FRAMES_WITH_FACE
    person_ok = frames_with_person >= MIN_FRAMES_WITH_PERSON

    _sep()
    if face_ok:
        print(f"[PASS] faces detected on {frames_with_face} frames (min {MIN_FRAMES_WITH_FACE})")
    else:
        print(f"[FAIL] only {frames_with_face} frames with face (min {MIN_FRAMES_WITH_FACE})")

    if person_ok:
        print(f"[PASS] people detected on {frames_with_person} frames (min {MIN_FRAMES_WITH_PERSON})")
    else:
        print(f"[FAIL] only {frames_with_person} frames with person (min {MIN_FRAMES_WITH_PERSON})")

    print("[3] Closing CameraService...")
    service.close()
    _sep("=")

    return 0 if face_ok and person_ok else 1


if __name__ == "__main__":
    sys.exit(main())