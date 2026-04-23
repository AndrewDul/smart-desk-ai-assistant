"""
Hardware smoke test — behavior signals + diagnostics metadata on a real camera.

Run manually on Pi:
    sudo systemctl stop nexa.service
    PYTHONPATH=. python tests/vision/hardware/camera/camera_behavior_diagnostics_smoke.py
    sudo systemctl start nexa.service

Purpose:
    - verify full behavior stack runs on real camera frames
    - verify diagnostics payload is present on each observation
    - verify behavior metadata exposes inference_mode for:
        * computer_work
        * phone_usage
        * study_activity
    - verify diagnostics signals preserve stable metadata and raw metadata
"""
from __future__ import annotations

import sys
import time

from modules.devices.vision.camera_service.service import CameraService


MEASURE_SECONDS = 12.0
SAMPLE_INTERVAL = 0.75
MIN_FRAMES_WITH_OBJECTS = 3


def _sep(char: str = "-", width: int = 72) -> None:
    print(char * width)


def _safe_inference_mode(payload: dict[str, object] | None) -> str:
    data = dict(payload or {})
    metadata = dict(data.get("metadata", {}) or {})
    return str(metadata.get("inference_mode", "") or "-")


def main() -> int:
    _sep("=")
    print("NeXa Vision — Behavior Diagnostics Smoke Test")
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
        "scene_understanding_enabled": False,
        "behavior_interpretation_enabled": True,
        "temporal_stabilization_enabled": True,
        "temporal_stabilization_activation_hits": 2,
        "temporal_stabilization_deactivation_hits": 2,
        "temporal_stabilization_hold_seconds": 1.25,
    }

    service = CameraService(config=config)

    print("[1] Starting CameraService...")
    service.start()

    status = service.status()
    print(f"[config] backend                 : {status.get('backend')}")
    print(f"[config] continuous_capture      : {status.get('continuous_capture_enabled')}")
    print(f"[config] detectors               : {status.get('detectors')}")
    print(f"[config] capabilities            : {status.get('capabilities')}")
    _sep()

    print(f"[2] Keep yourself and your desk scene visible for {MEASURE_SECONDS:.0f}s...")
    print("    (laptop / monitor / keyboard / mouse / phone / cup etc.)")
    _sep()

    deadline = time.monotonic() + MEASURE_SECONDS
    frames_sampled = 0
    frames_with_objects = 0
    frames_with_diagnostics = 0
    frames_with_all_inference_modes = 0
    last_observation = None
    last_print_at = 0.0

    while time.monotonic() < deadline:
        observation = service.latest_observation(force_refresh=True)
        if observation is None:
            time.sleep(SAMPLE_INTERVAL)
            continue

        last_observation = observation
        frames_sampled += 1

        perception = dict(observation.metadata.get("perception", {}) or {})
        behavior = dict(observation.metadata.get("behavior", {}) or {})
        diagnostics = dict(observation.metadata.get("diagnostics", {}) or {})
        signals = dict(diagnostics.get("signals", {}) or {})

        object_count = int(perception.get("object_count", 0))
        if object_count > 0:
            frames_with_objects += 1

        if diagnostics:
            frames_with_diagnostics += 1

        computer_mode = _safe_inference_mode(behavior.get("computer_work"))
        phone_mode = _safe_inference_mode(behavior.get("phone_usage"))
        study_mode = _safe_inference_mode(behavior.get("study_activity"))

        diagnostics_modes_present = all(
            str(
                dict((signals.get(name) or {}).get("metadata", {}) or {}).get("inference_mode", "")
            ).strip()
            for name in ("computer_work", "phone_usage", "study_activity")
        )
        if diagnostics_modes_present:
            frames_with_all_inference_modes += 1

        now = time.monotonic()
        if now - last_print_at >= 1.0:
            print(
                f"  [sample] objects={object_count} "
                f"presence={bool((behavior.get('presence', {}) or {}).get('active', False))} "
                f"computer={bool((behavior.get('computer_work', {}) or {}).get('active', False))}/{computer_mode} "
                f"phone={bool((behavior.get('phone_usage', {}) or {}).get('active', False))}/{phone_mode} "
                f"study={bool((behavior.get('study_activity', {}) or {}).get('active', False))}/{study_mode}"
            )
            last_print_at = now

        time.sleep(SAMPLE_INTERVAL)

    _sep()
    print(f"[result] frames sampled                 : {frames_sampled}")
    print(f"[result] frames with objects            : {frames_with_objects}")
    print(f"[result] frames with diagnostics        : {frames_with_diagnostics}")
    print(f"[result] frames with inference modes    : {frames_with_all_inference_modes}")

    if last_observation is None:
        print("[FAIL] No observation returned from CameraService")
        print("[3] Closing CameraService...")
        service.close()
        _sep("=")
        return 1

    behavior = dict(last_observation.metadata.get("behavior", {}) or {})
    diagnostics = dict(last_observation.metadata.get("diagnostics", {}) or {})
    signals = dict(diagnostics.get("signals", {}) or {})
    summary = dict(diagnostics.get("summary", {}) or {})

    print(f"[result] last behavior keys            : {sorted(list(behavior.keys()))}")
    print(f"[result] last diagnostics signal keys  : {sorted(list(signals.keys()))}")
    print(f"[result] last diagnostics summary      : {summary}")

    objects_ok = frames_with_objects >= MIN_FRAMES_WITH_OBJECTS
    diagnostics_ok = frames_with_diagnostics == frames_sampled and frames_sampled > 0
    inference_modes_ok = frames_with_all_inference_modes > 0

    _sep()
    if objects_ok:
        print(f"[PASS] objects detected on {frames_with_objects} frames (min {MIN_FRAMES_WITH_OBJECTS})")
    else:
        print(f"[FAIL] objects detected on only {frames_with_objects} frames (min {MIN_FRAMES_WITH_OBJECTS})")

    if diagnostics_ok:
        print("[PASS] diagnostics payload present on every sampled observation")
    else:
        print("[FAIL] diagnostics payload missing on some sampled observations")

    if inference_modes_ok:
        print("[PASS] diagnostics metadata exposes inference_mode for computer/phone/study")
    else:
        print("[FAIL] diagnostics metadata did not expose inference_mode for all target signals")

    print("[3] Closing CameraService...")
    service.close()
    _sep("=")

    return 0 if objects_ok and diagnostics_ok and inference_modes_ok else 1


if __name__ == "__main__":
    sys.exit(main())