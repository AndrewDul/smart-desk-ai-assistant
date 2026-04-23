"""
Hardware smoke test — full NeXa app boot with real vision runtime enabled.

Run manually on Pi:
    sudo systemctl stop nexa.service
    PYTHONPATH=. python tests/vision/hardware/camera/camera_full_app_boot_smoke.py
    sudo systemctl start nexa.service

Purpose:
    - verify full app boot with vision enabled in config/settings.json
    - verify CameraService starts inside CoreAssistant boot
    - verify real observations are available from the live app runtime
    - verify perception object_count > 0 is visible through the full app path
    - verify behavior metadata is present in the final observation
"""
from __future__ import annotations

import sys
import time

from modules.core.assistant import CoreAssistant


MEASURE_SECONDS = 10.0
SAMPLE_INTERVAL = 0.75
MIN_FRAMES_WITH_OBJECTS = 3


def _sep(char: str = "-", width: int = 72) -> None:
    print(char * width)


def _labels_from_observation(observation) -> list[str]:
    perception = observation.metadata.get("perception", {}) or {}
    objects = perception.get("objects", []) or []
    labels: list[str] = []
    for obj in objects:
        label = str(obj.get("label", "")).strip().lower()
        if label:
            labels.append(label)
    return labels


def main() -> int:
    _sep("=")
    print("NeXa Vision — Full App Boot Smoke Test")
    _sep("=")

    assistant = CoreAssistant()

    try:
        print("[1] Booting full CoreAssistant...")
        assistant.boot()

        vision = getattr(assistant, "vision", None)
        if vision is None:
            print("[FAIL] Assistant has no vision backend attached")
            return 1

        status_method = getattr(vision, "status", None)
        if not callable(status_method):
            print("[FAIL] Vision backend does not expose status()")
            return 1

        status = status_method()
        print(f"[config] vision backend            : {status.get('backend')}")
        print(f"[config] continuous capture       : {status.get('continuous_capture_enabled')}")
        print(f"[config] detectors                : {status.get('detectors')}")
        print(f"[config] capabilities             : {status.get('capabilities')}")
        _sep()

        print(f"[2] Sampling live app observations for {MEASURE_SECONDS:.0f}s...")
        print("    Keep yourself and your desk scene visible to the camera.")
        _sep()

        deadline = time.monotonic() + MEASURE_SECONDS
        samples = 0
        frames_with_objects = 0
        frames_with_presence = 0
        frames_with_desk = 0
        last_observation = None

        while time.monotonic() < deadline:
            observation = vision.latest_observation(force_refresh=False)
            if observation is None:
                time.sleep(SAMPLE_INTERVAL)
                continue

            last_observation = observation
            samples += 1

            perception = observation.metadata.get("perception", {}) or {}
            behavior = observation.metadata.get("behavior", {}) or {}

            object_count = int(perception.get("object_count", 0))
            labels = _labels_from_observation(observation)

            presence_active = bool((behavior.get("presence", {}) or {}).get("active", False))
            desk_active = bool((behavior.get("desk_activity", {}) or {}).get("active", False))
            computer_active = bool((behavior.get("computer_work", {}) or {}).get("active", False))
            phone_active = bool((behavior.get("phone_usage", {}) or {}).get("active", False))
            study_active = bool((behavior.get("study_activity", {}) or {}).get("active", False))

            if object_count > 0:
                frames_with_objects += 1
            if presence_active:
                frames_with_presence += 1
            if desk_active:
                frames_with_desk += 1

            print(
                f"  [sample] objects={object_count} "
                f"labels={labels[:4] if labels else []} "
                f"presence={presence_active} "
                f"desk={desk_active} "
                f"computer={computer_active} "
                f"phone={phone_active} "
                f"study={study_active}"
            )

            time.sleep(SAMPLE_INTERVAL)

        _sep()
        print(f"[result] samples                    : {samples}")
        print(f"[result] frames with objects        : {frames_with_objects}")
        print(f"[result] frames with presence       : {frames_with_presence}")
        print(f"[result] frames with desk activity  : {frames_with_desk}")

        if last_observation is None:
            print("[FAIL] No observation was produced by the full app runtime")
            return 1

        perception = last_observation.metadata.get("perception", {}) or {}
        behavior = last_observation.metadata.get("behavior", {}) or {}
        sessions = last_observation.metadata.get("sessions", {}) or {}

        print(f"[result] last perception summary    : people={perception.get('people_count')} faces={perception.get('face_count')} objects={perception.get('object_count')}")
        print(f"[result] last labels                : {last_observation.labels}")
        print(f"[result] behavior keys              : {sorted(list(behavior.keys()))}")
        print(f"[result] session keys               : {sorted(list(sessions.keys()))}")

        objects_ok = frames_with_objects >= MIN_FRAMES_WITH_OBJECTS
        behavior_ok = all(
            key in behavior
            for key in (
                "presence",
                "desk_activity",
                "computer_work",
                "phone_usage",
                "study_activity",
            )
        )

        _sep()
        if objects_ok:
            print(f"[PASS] Full app runtime produced objects on {frames_with_objects} frames")
        else:
            print(f"[FAIL] Full app runtime produced objects on only {frames_with_objects} frames")

        if behavior_ok:
            print("[PASS] Behavior metadata is present in full app observations")
        else:
            print("[FAIL] Behavior metadata is incomplete in full app observations")

        return 0 if objects_ok and behavior_ok else 1

    finally:
        print("[3] Shutting down CoreAssistant...")
        try:
            assistant.shutdown()
        except Exception as error:
            print(f"[WARN] Assistant shutdown raised: {error}")
        _sep("=")


if __name__ == "__main__":
    sys.exit(main())