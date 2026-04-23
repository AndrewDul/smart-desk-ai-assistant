"""
Hardware capture tool — behavior calibration snapshots on a real camera.

Run manually on Pi:
    sudo systemctl stop nexa.service
    PYTHONPATH=. python tests/vision/hardware/camera/camera_behavior_calibration_capture.py --tag laptop-study
    sudo systemctl start nexa.service

What it does:
    - captures a configurable number of real camera samples
    - runs the full perception + behavior + stabilization + sessions path
    - saves one JSONL record per sample for later calibration work
    - optionally saves one PNG image per sample

Useful for:
    - computer_work false-positive tuning
    - phone_usage real-scene tuning
    - study_activity tuning
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import cv2

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.devices.vision.behavior import BehaviorPipeline
from modules.devices.vision.capture import VisionCaptureReader
from modules.devices.vision.config import VisionRuntimeConfig
from modules.devices.vision.diagnostics import build_calibration_sample, build_diagnostics_snapshot
from modules.devices.vision.perception import PerceptionPipeline
from modules.devices.vision.sessions import VisionSessionTracker
from modules.devices.vision.stabilization import BehaviorStabilizer


def _sep(char: str = "-", width: int = 72) -> None:
    print(char * width)


def _sanitize_tag(tag: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(tag or "").strip())
    cleaned = cleaned.strip("-_.")
    return cleaned or "untagged"


def _packet_pixels_to_bgr(packet):
    pixels = packet.pixels
    if packet.backend_label == "picamera2":
        return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    return pixels


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture labeled NeXa behavior calibration samples from the real camera.",
    )
    parser.add_argument("--tag", required=True, help="Human label for this capture set, e.g. laptop-study or phone-at-desk.")
    parser.add_argument("--samples", type=int, default=12, help="How many samples to capture.")
    parser.add_argument("--interval-seconds", type=float, default=0.75, help="Delay between samples.")
    parser.add_argument("--save-images", action="store_true", help="Also save one PNG per sample.")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "var" / "vision" / "calibration"),
        help="Root directory for saved calibration sessions.",
    )
    return parser


def _build_runtime_mapping() -> dict[str, object]:
    return {
        "enabled": True,
        "backend": "picamera2",
        "fallback_backend": "opencv",
        "camera_index": 0,
        "frame_width": 1280,
        "frame_height": 720,
        "lazy_start": True,
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


def main() -> int:
    args = _build_arg_parser().parse_args()
    capture_tag = _sanitize_tag(args.tag)
    output_root = Path(args.output_dir)
    session_stamp = time.strftime("%Y%m%d-%H%M%S")
    session_dir = output_root / f"{session_stamp}-{capture_tag}"
    images_dir = session_dir / "images"
    jsonl_path = session_dir / "samples.jsonl"

    session_dir.mkdir(parents=True, exist_ok=True)
    if args.save_images:
        images_dir.mkdir(parents=True, exist_ok=True)

    raw_config = _build_runtime_mapping()
    config = VisionRuntimeConfig.from_mapping(raw_config)

    reader = VisionCaptureReader(config=config)
    perception = PerceptionPipeline.from_config(config)

    behavior_factory = getattr(BehaviorPipeline, "from_mapping", None)
    if callable(behavior_factory):
        behavior = behavior_factory(raw_config)
    else:
        behavior = BehaviorPipeline()

    stabilizer = BehaviorStabilizer.from_config(config)
    sessions = VisionSessionTracker()

    object_detector = getattr(perception, "object_detector", None)
    detector_close = getattr(object_detector, "close", None)

    _sep("=")
    print("NeXa Vision — Behavior Calibration Capture")
    _sep("=")
    print(f"[config] tag                     : {capture_tag}")
    print(f"[config] samples                 : {args.samples}")
    print(f"[config] interval_seconds        : {args.interval_seconds}")
    print(f"[config] save_images             : {bool(args.save_images)}")
    print(f"[config] output_dir              : {session_dir}")
    _sep()

    try:
        with jsonl_path.open("w", encoding="utf-8") as jsonl_file:
            for index in range(1, max(1, int(args.samples)) + 1):
                packet = reader.read_frame()
                perception_snapshot = perception.analyze(packet)
                raw_behavior = behavior.analyze(perception_snapshot)
                stable_behavior = stabilizer.stabilize(raw_behavior, packet.captured_at)
                session_snapshot = sessions.update(stable_behavior, packet.captured_at)

                diagnostics = build_diagnostics_snapshot(
                    packet,
                    perception=perception_snapshot,
                    raw_behavior=raw_behavior,
                    behavior=stable_behavior,
                    sessions=session_snapshot,
                )

                calibration = build_calibration_sample(
                    capture_tag=capture_tag,
                    diagnostics=diagnostics,
                ).to_dict()

                calibration["sample_index"] = index
                calibration["wall_clock_saved_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                calibration["session_dir"] = str(session_dir)

                if args.save_images:
                    image_path = images_dir / f"sample-{index:03d}.png"
                    cv2.imwrite(str(image_path), _packet_pixels_to_bgr(packet))
                    calibration["image_path"] = str(image_path)

                jsonl_file.write(json.dumps(calibration, ensure_ascii=False) + "\n")
                jsonl_file.flush()

                summary = calibration["summary"]
                computer = calibration["signals"]["computer_work"]
                phone = calibration["signals"]["phone_usage"]
                study = calibration["signals"]["study_activity"]

                print(
                    f"[sample {index:03d}] "
                    f"objects={summary.get('object_count', 0)} "
                    f"computer={computer.get('stable_active', False)}/{computer.get('stable_inference_mode', '-')} "
                    f"phone={phone.get('stable_active', False)}/{phone.get('stable_inference_mode', '-')} "
                    f"study={study.get('stable_active', False)}/{study.get('stable_inference_mode', '-')}"
                )

                if index < args.samples:
                    time.sleep(max(0.0, float(args.interval_seconds)))

        _sep()
        print(f"[done] calibration jsonl saved to: {jsonl_path}")
        if args.save_images:
            print(f"[done] images saved to          : {images_dir}")
        _sep("=")
        return 0
    finally:
        try:
            if callable(detector_close):
                detector_close()
        finally:
            reader.close()


if __name__ == "__main__":
    raise SystemExit(main())