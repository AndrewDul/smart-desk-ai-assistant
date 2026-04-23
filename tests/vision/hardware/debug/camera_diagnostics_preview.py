from __future__ import annotations

import argparse
import json
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
from modules.devices.vision.diagnostics import build_diagnostics_snapshot, render_diagnostics_overlay
from modules.devices.vision.perception import PerceptionPipeline
from modules.devices.vision.sessions import VisionSessionTracker
from modules.devices.vision.stabilization import BehaviorStabilizer

WINDOW_NAME = "NeXa Vision Diagnostics Preview"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the NeXa live diagnostics preview for the vision pipeline.",
    )
    parser.add_argument("--backend", default="picamera2", choices=("picamera2", "opencv"))
    parser.add_argument("--camera-index", type=int, default=0)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--frame-delay-ms", type=int, default=1)
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "var" / "vision" / "diagnostics_preview"),
        help="Directory used for saved screenshots and diagnostics payloads.",
    )
    return parser


def _build_runtime_mapping(args: argparse.Namespace) -> dict[str, object]:
    return {
        "enabled": True,
        "backend": args.backend,
        "fallback_backend": "opencv",
        "camera_index": args.camera_index,
        "frame_width": args.width,
        "frame_height": args.height,
        "lazy_start": True,
        "people_detection_enabled": True,
        "people_detector_backend": "opencv_hog",
        "people_detector_min_confidence": 0.40,
        "people_detector_min_area_ratio": 0.02,
        "people_detector_min_height_ratio": 0.15,
        "people_detector_max_width_ratio": 0.85,
        "people_detector_use_clahe": True,
        "people_detector_upscale_factor": 1.5,
        "people_detector_desk_roi_enabled": True,
        "people_detector_roi_x_min": 0.10,
        "people_detector_roi_y_min": 0.08,
        "people_detector_roi_x_max": 0.90,
        "people_detector_roi_y_max": 0.98,
        "face_detection_enabled": True,
        "face_detector_backend": "opencv_haar",
        "face_detector_min_area_ratio": 0.002,
        "face_detector_use_clahe": True,
        "face_detector_roi_enabled": True,
        "object_detection_enabled": False,
        "object_detector_backend": "null",
        "scene_understanding_enabled": True,
        "behavior_interpretation_enabled": True,
        "temporal_stabilization_enabled": True,
        "temporal_stabilization_activation_hits": 2,
        "temporal_stabilization_deactivation_hits": 2,
        "temporal_stabilization_hold_seconds": 1.25,
    }


def _build_runtime_config(raw_config: dict[str, object]) -> VisionRuntimeConfig:
    return VisionRuntimeConfig.from_mapping(raw_config)


def _packet_pixels_to_preview_bgr(packet) -> object:
    pixels = packet.pixels
    if packet.backend_label == "picamera2":
        return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR)
    return pixels


def _add_preview_footer(image, *, paused: bool) -> None:
    footer = "controls: q/esc=quit  s=save snapshot  p=pause/resume"
    if paused:
        footer += "  [paused]"

    cv2.rectangle(
        image,
        (0, image.shape[0] - 28),
        (image.shape[1], image.shape[0]),
        (24, 24, 24),
        -1,
    )
    cv2.putText(
        image,
        footer,
        (10, image.shape[0] - 9),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (235, 235, 235),
        1,
        cv2.LINE_AA,
    )


def _save_snapshot(*, output_dir: Path, image, diagnostics: dict[str, object]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    image_path = output_dir / f"vision-preview-{stamp}.png"
    json_path = output_dir / f"vision-preview-{stamp}.json"

    cv2.imwrite(str(image_path), image)
    json_path.write_text(json.dumps(diagnostics, indent=2, default=str), encoding="utf-8")
    return image_path


def main() -> None:
    args = _build_arg_parser().parse_args()
    output_dir = Path(args.output_dir)
    raw_config = _build_runtime_mapping(args)
    config = _build_runtime_config(raw_config)

    reader = VisionCaptureReader(config=config)
    perception = PerceptionPipeline.from_config(config)

    behavior_factory = getattr(BehaviorPipeline, "from_mapping", None)
    if callable(behavior_factory):
        behavior = behavior_factory(raw_config)
    else:
        behavior = BehaviorPipeline()

    stabilizer = BehaviorStabilizer.from_config(config)
    sessions = VisionSessionTracker()

    paused = False
    last_overlay = None
    last_diagnostics = None

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

    try:
        while True:
            if not paused or last_overlay is None:
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
                ).to_dict()

                preview_frame = _packet_pixels_to_preview_bgr(packet)
                overlay = render_diagnostics_overlay(preview_frame, diagnostics)
                _add_preview_footer(overlay, paused=paused)

                last_overlay = overlay
                last_diagnostics = diagnostics

            if last_overlay is None:
                raise RuntimeError("Diagnostics preview failed to produce an overlay frame.")

            cv2.imshow(WINDOW_NAME, last_overlay)
            key = cv2.waitKey(max(1, int(args.frame_delay_ms))) & 0xFF

            if key in (27, ord("q")):
                break
            if key == ord("p"):
                paused = not paused
                if last_overlay is not None:
                    overlay_copy = last_overlay.copy()
                    _add_preview_footer(overlay_copy, paused=paused)
                    last_overlay = overlay_copy
                continue
            if key == ord("s") and last_diagnostics is not None:
                saved_path = _save_snapshot(
                    output_dir=output_dir,
                    image=last_overlay,
                    diagnostics=last_diagnostics,
                )
                print(f"Saved diagnostics snapshot to: {saved_path}")
    finally:
        reader.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()