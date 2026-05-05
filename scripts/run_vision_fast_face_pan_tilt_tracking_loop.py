#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from modules.devices.pan_tilt import PanTiltService
from validate_vision_tracking_execution_readiness import load_settings, validate_settings


DEFAULT_SETTINGS_PATH = Path("config/settings.json")
DEFAULT_STATE_PATH = Path("var/data/pan_tilt_limit_calibration.json")
DEFAULT_STATUS_PATH = Path("var/data/vision_fast_face_tracking_loop_status.json")

CONFIRM_ENV_NAME = "CONFIRM_NEXA_FAST_FACE_TRACKING_LOOP"
CONFIRM_VALUE = "RUN_FAST_FACE_TRACKING_LOOP"

MAX_DURATION_SECONDS = 30.0
MAX_STEP_DEGREES = 1.0
MAX_SPEED = 75
MAX_ACCELERATION = 75
CENTER_REQUIRED_MAX_ABS_DEGREES = 1.0


@dataclass(slots=True)
class FaceTarget:
    left: int
    top: int
    right: int
    bottom: int
    confidence: float
    area_ratio: float
    profile: str
    gray_variant: str
    scale_factor: float
    min_neighbors: int

    @property
    def width(self) -> int:
        return max(1, self.right - self.left)

    @property
    def height(self) -> int:
        return max(1, self.bottom - self.top)

    @property
    def area(self) -> int:
        return self.width * self.height

    def center_x_norm(self, frame_width: int) -> float:
        return ((self.left + self.right) / 2.0) / max(1, frame_width)

    def center_y_norm(self, frame_height: int) -> float:
        return ((self.top + self.bottom) / 2.0) / max(1, frame_height)

    def to_dict(self, *, frame_width: int, frame_height: int) -> dict[str, Any]:
        return {
            "box": {
                "left": self.left,
                "top": self.top,
                "right": self.right,
                "bottom": self.bottom,
            },
            "center_x_norm": round(self.center_x_norm(frame_width), 5),
            "center_y_norm": round(self.center_y_norm(frame_height), 5),
            "confidence": round(self.confidence, 4),
            "area_ratio": round(self.area_ratio, 5),
            "metadata": {
                "detector": "opencv_haar_fast_loop",
                "cascade_profile": self.profile,
                "gray_variant": self.gray_variant,
                "scale_factor": self.scale_factor,
                "min_neighbors": self.min_neighbors,
            },
        }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _load_calibration_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(
            f"Missing calibration state: {path}. "
            "Run safe center recovery/calibration before fast face tracking."
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise SystemExit(f"Invalid calibration state JSON: {path}: {error}") from error

    marked = data.get("marked_limits", {})
    required = ["pan_left_x", "pan_right_x", "tilt_min_y", "tilt_max_y"]
    missing = [key for key in required if key not in marked]
    if missing:
        raise SystemExit("Missing marked calibration limits: " + ", ".join(missing))

    return data


def _safe_limits_from_state(state: dict[str, Any]) -> dict[str, float]:
    marked = state.get("marked_limits", {})
    pan_left = _safe_float(marked.get("pan_left_x"), -15.0)
    pan_right = _safe_float(marked.get("pan_right_x"), 15.0)
    tilt_min = _safe_float(marked.get("tilt_min_y"), -8.0)
    tilt_max = _safe_float(marked.get("tilt_max_y"), 8.0)

    return {
        "pan_min_degrees": min(pan_left, pan_right),
        "pan_center_degrees": 0.0,
        "pan_max_degrees": max(pan_left, pan_right),
        "tilt_min_degrees": min(tilt_min, tilt_max),
        "tilt_center_degrees": 0.0,
        "tilt_max_degrees": max(tilt_min, tilt_max),
    }


def _validate_default_readiness(settings_path: Path) -> dict[str, Any]:
    result = validate_settings(load_settings(settings_path))
    if not bool(result.get("ok", False)):
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        raise SystemExit("Default tracking readiness validation failed.")

    if bool(result.get("safe_to_execute_physical_motion", False)):
        raise SystemExit(
            "Refusing because default config reports safe_to_execute_physical_motion=true. "
            "Sprint 11C expects default runtime movement to remain OFF."
        )

    return result


def _require_execute_confirmation(*, execute: bool, understand: bool, confirm_text: str) -> None:
    if not execute:
        return

    if not understand:
        raise SystemExit(
            "Refusing to move. Add --i-understand-this-moves-hardware for this hardware loop."
        )

    if confirm_text != CONFIRM_VALUE:
        raise SystemExit(
            f"Refusing to move. Add --confirm-text {CONFIRM_VALUE} for this hardware loop."
        )

    if os.environ.get(CONFIRM_ENV_NAME, "") != CONFIRM_VALUE:
        raise SystemExit(
            f"Refusing to move. Set {CONFIRM_ENV_NAME}={CONFIRM_VALUE} before this hardware loop."
        )


def _require_state_near_center_for_execute(*, state: dict[str, Any], execute: bool) -> None:
    if not execute:
        return

    current_x = _safe_float(state.get("x"), 0.0)
    current_y = _safe_float(state.get("y"), 0.0)
    if abs(current_x) <= CENTER_REQUIRED_MAX_ABS_DEGREES and abs(current_y) <= CENTER_REQUIRED_MAX_ABS_DEGREES:
        return

    raise SystemExit(
        "Refusing execute because calibration state is not near center. "
        f"Current state is X={current_x} Y={current_y}. "
        "Run safe center recovery first."
    )


def _validate_runtime_limits(
    *,
    duration_seconds: float,
    target_fps: float,
    max_step_degrees: float,
    speed: int,
    acceleration: int,
    command_interval_seconds: float,
) -> None:
    if duration_seconds <= 0.0 or duration_seconds > MAX_DURATION_SECONDS:
        raise SystemExit(
            f"Refusing duration {duration_seconds}. "
            f"Allowed range is >0..{MAX_DURATION_SECONDS} seconds."
        )

    if target_fps <= 0.5 or target_fps > 20.0:
        raise SystemExit("Refusing target FPS outside 0.5..20.0.")

    if max_step_degrees <= 0.0 or max_step_degrees > MAX_STEP_DEGREES:
        raise SystemExit(
            f"Refusing max step {max_step_degrees}. "
            f"Sprint 11C maximum is {MAX_STEP_DEGREES} degree."
        )

    if not (1 <= speed <= MAX_SPEED):
        raise SystemExit(f"Refusing speed {speed}. Allowed range is 1..{MAX_SPEED}.")

    if not (1 <= acceleration <= MAX_ACCELERATION):
        raise SystemExit(f"Refusing acceleration {acceleration}. Allowed range is 1..{MAX_ACCELERATION}.")

    if command_interval_seconds < 0.05:
        raise SystemExit("Refusing command interval below 0.05 seconds.")


def _find_haar_cascade() -> Path:
    filename = "haarcascade_frontalface_default.xml"
    candidates: list[Path] = []

    cv2_data = getattr(cv2, "data", None)
    haar_dir = getattr(cv2_data, "haarcascades", None) if cv2_data is not None else None
    if haar_dir:
        candidates.append(Path(haar_dir) / filename)

    cv2_file = getattr(cv2, "__file__", None)
    if cv2_file:
        cv2_dir = Path(cv2_file).resolve().parent
        candidates.extend(
            [
                cv2_dir / "data" / filename,
                cv2_dir / "haarcascades" / filename,
                cv2_dir.parent / "share" / "opencv4" / "haarcascades" / filename,
                cv2_dir.parent / "share" / "opencv" / "haarcascades" / filename,
            ]
        )

    candidates.extend(
        [
            Path("/usr/share/opencv4/haarcascades") / filename,
            Path("/usr/share/opencv/haarcascades") / filename,
            Path("/usr/local/share/opencv4/haarcascades") / filename,
            Path("/usr/local/share/opencv/haarcascades") / filename,
        ]
    )

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.is_file():
            return candidate

    raise SystemExit("Could not find haarcascade_frontalface_default.xml.")


def _build_gray_variants(frame_bgr: np.ndarray) -> tuple[tuple[str, np.ndarray], ...]:
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

    variants: list[tuple[str, np.ndarray]] = [("prepared", gray)]

    try:
        equalized = cv2.equalizeHist(gray)
        variants.append(("equalized", equalized))
    except Exception:
        pass

    return tuple(variants)


def _profile_sequence() -> tuple[tuple[str, float, int], ...]:
    return (
        ("primary", 1.1, 5),
        ("sweep_1.05_4", 1.05, 4),
        ("sweep_1.05_3", 1.05, 3),
        ("sweep_1.03_3", 1.03, 3),
        ("sweep_1.10_3", 1.10, 3),
    )


def _intersection_over_union(first: FaceTarget, second: FaceTarget) -> float:
    left = max(first.left, second.left)
    top = max(first.top, second.top)
    right = min(first.right, second.right)
    bottom = min(first.bottom, second.bottom)

    if right <= left or bottom <= top:
        return 0.0

    intersection = (right - left) * (bottom - top)
    union = max(1, first.area + second.area - intersection)
    return intersection / union


def _append_unique_target(targets: list[FaceTarget], candidate: FaceTarget) -> None:
    for index, existing in enumerate(targets):
        if _intersection_over_union(existing, candidate) < 0.35:
            continue

        if candidate.area > existing.area or candidate.confidence > existing.confidence:
            targets[index] = candidate
        return

    targets.append(candidate)


def _detect_faces(
    *,
    cascade: Any,
    frame_bgr: np.ndarray,
    min_face_area_ratio: float,
    max_face_area_ratio: float,
) -> list[FaceTarget]:
    frame_height, frame_width = frame_bgr.shape[:2]
    frame_area = max(1, frame_width * frame_height)
    targets: list[FaceTarget] = []

    for gray_label, gray in _build_gray_variants(frame_bgr):
        for profile, scale_factor, min_neighbors in _profile_sequence():
            boxes = cascade.detectMultiScale(
                gray,
                scaleFactor=float(scale_factor),
                minNeighbors=int(min_neighbors),
            )

            for x, y, w, h in boxes:
                x = int(x)
                y = int(y)
                w = int(w)
                h = int(h)
                if w <= 0 or h <= 0:
                    continue

                area_ratio = (w * h) / frame_area
                if area_ratio < min_face_area_ratio or area_ratio > max_face_area_ratio:
                    continue

                aspect_ratio = w / max(1, h)
                if aspect_ratio < 0.65 or aspect_ratio > 1.45:
                    continue

                height_ratio = h / max(1, frame_height)
                confidence = _clamp(0.55 + min(0.20, area_ratio * 18.0) + min(0.15, height_ratio * 1.5), 0.0, 0.95)

                target = FaceTarget(
                    left=max(0, min(frame_width - 1, x)),
                    top=max(0, min(frame_height - 1, y)),
                    right=max(1, min(frame_width, x + w)),
                    bottom=max(1, min(frame_height, y + h)),
                    confidence=confidence,
                    area_ratio=area_ratio,
                    profile=profile,
                    gray_variant=gray_label,
                    scale_factor=float(scale_factor),
                    min_neighbors=int(min_neighbors),
                )
                _append_unique_target(targets, target)

    targets.sort(key=lambda item: (item.area, item.confidence), reverse=True)
    return targets


def _compute_motion_plan(
    *,
    target: FaceTarget | None,
    frame_width: int,
    frame_height: int,
    dead_zone_x: float,
    dead_zone_y: float,
    pan_gain_degrees: float,
    tilt_gain_degrees: float,
    max_step_degrees: float,
) -> dict[str, Any]:
    if target is None:
        return {
            "has_target": False,
            "reason": "no_target",
            "pan_delta_degrees": 0.0,
            "tilt_delta_degrees": 0.0,
            "would_move_pan_tilt": False,
            "target": None,
            "diagnostics": {},
        }

    center_x = target.center_x_norm(frame_width)
    center_y = target.center_y_norm(frame_height)
    offset_x = center_x - 0.5
    offset_y = center_y - 0.5

    raw_pan = offset_x * pan_gain_degrees
    raw_tilt = -offset_y * tilt_gain_degrees

    pan_delta = 0.0 if abs(offset_x) < dead_zone_x else raw_pan
    tilt_delta = 0.0 if abs(offset_y) < dead_zone_y else raw_tilt

    pan_delta = _clamp(pan_delta, -max_step_degrees, max_step_degrees)
    tilt_delta = _clamp(tilt_delta, -max_step_degrees, max_step_degrees)

    would_move = abs(pan_delta) > 0.0001 or abs(tilt_delta) > 0.0001

    return {
        "has_target": True,
        "reason": "recenter_target" if would_move else "target_centered",
        "pan_delta_degrees": round(pan_delta, 4),
        "tilt_delta_degrees": round(tilt_delta, 4),
        "would_move_pan_tilt": would_move,
        "target": target.to_dict(frame_width=frame_width, frame_height=frame_height),
        "diagnostics": {
            "offset_x": round(offset_x, 4),
            "offset_y": round(offset_y, 4),
            "raw_pan_delta_degrees": round(raw_pan, 4),
            "raw_tilt_delta_degrees": round(raw_tilt, 4),
            "dead_zone_x": dead_zone_x,
            "dead_zone_y": dead_zone_y,
        },
    }


def _build_pan_tilt_service(
    *,
    settings: dict[str, Any],
    state: dict[str, Any],
    state_path: Path,
    port: str | None,
    baudrate: int | None,
    max_step_degrees: float,
    speed: int,
    acceleration: int,
    execute: bool,
) -> PanTiltService:
    config = dict(settings.get("pan_tilt", {}))
    config.update(
        {
            "enabled": True,
            "backend": "waveshare_serial",
            "hardware_enabled": bool(execute),
            "motion_enabled": bool(execute),
            "dry_run": not bool(execute),
            "device": str(port or state.get("port") or "/dev/serial0"),
            "baudrate": int(baudrate or state.get("baudrate") or 115200),
            "timeout_seconds": float(config.get("timeout_seconds", 0.2)),
            "protocol": "waveshare_json_serial",
            "startup_policy": "no_motion",
            "calibration_required": True,
            "allow_uncalibrated_motion": False,
            "calibration_state_path": str(state_path),
            "max_step_degrees": float(max_step_degrees),
            "command_speed": int(speed),
            "command_acceleration": int(acceleration),
            "serial_warmup_seconds": 1.0 if execute else 0.05,
            "read_after_write_seconds": 0.0,
            "safe_limits": _safe_limits_from_state(state),
        }
    )
    return PanTiltService(config)


def _open_camera(*, width: int, height: int, warmup_seconds: float):
    from picamera2 import Picamera2

    camera = Picamera2()
    config = camera.create_preview_configuration(
        main={"size": (int(width), int(height)), "format": "RGB888"}
    )
    camera.configure(config)
    camera.start()
    time.sleep(max(0.0, float(warmup_seconds)))
    return camera


def run_fast_tracking_loop(args: argparse.Namespace) -> dict[str, Any]:
    settings_path = Path(args.settings)
    state_path = Path(args.state)
    status_path = Path(args.status_path)

    _validate_runtime_limits(
        duration_seconds=float(args.duration_seconds),
        target_fps=float(args.target_fps),
        max_step_degrees=float(args.max_step_degrees),
        speed=int(args.speed),
        acceleration=int(args.acceleration),
        command_interval_seconds=float(args.command_interval_seconds),
    )
    _require_execute_confirmation(
        execute=bool(args.execute),
        understand=bool(args.i_understand_this_moves_hardware),
        confirm_text=str(args.confirm_text),
    )

    settings = dict(load_settings(settings_path))
    readiness = _validate_default_readiness(settings_path)
    state = _load_calibration_state(state_path)
    _require_state_near_center_for_execute(state=state, execute=bool(args.execute))

    cascade_path = _find_haar_cascade()
    cascade = cv2.CascadeClassifier(str(cascade_path))
    if cascade.empty():
        raise SystemExit(f"Failed to load Haar cascade: {cascade_path}")

    pan_tilt_service = _build_pan_tilt_service(
        settings=settings,
        state=state,
        state_path=state_path,
        port=args.port,
        baudrate=args.baudrate,
        max_step_degrees=float(args.max_step_degrees),
        speed=int(args.speed),
        acceleration=int(args.acceleration),
        execute=bool(args.execute),
    )

    camera = None
    started_at = time.monotonic()
    last_command_at = 0.0
    frame_count = 0
    detection_count = 0
    target_count = 0
    command_count = 0
    no_motion_count = 0
    no_target_count = 0
    error_count = 0
    steps: list[dict[str, Any]] = []
    return_center_result: dict[str, Any] | None = None

    frame_interval = 1.0 / float(args.target_fps)

    try:
        camera = _open_camera(
            width=int(args.width),
            height=int(args.height),
            warmup_seconds=float(args.camera_warmup_seconds),
        )

        while True:
            now = time.monotonic()
            elapsed = now - started_at
            if elapsed >= float(args.duration_seconds):
                break

            loop_started = time.monotonic()

            try:
                frame_rgb = camera.capture_array()
                frame_count += 1

                frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                faces = _detect_faces(
                    cascade=cascade,
                    frame_bgr=frame_bgr,
                    min_face_area_ratio=float(args.min_face_area_ratio),
                    max_face_area_ratio=float(args.max_face_area_ratio),
                )
                detection_count += len(faces)
                target = faces[0] if faces else None
                if target is None:
                    no_target_count += 1
                else:
                    target_count += 1

                plan = _compute_motion_plan(
                    target=target,
                    frame_width=int(args.width),
                    frame_height=int(args.height),
                    dead_zone_x=float(args.dead_zone_x),
                    dead_zone_y=float(args.dead_zone_y),
                    pan_gain_degrees=float(args.pan_gain_degrees),
                    tilt_gain_degrees=float(args.tilt_gain_degrees),
                    max_step_degrees=float(args.max_step_degrees),
                )

                backend_result: dict[str, Any] | None = None
                command_allowed_by_interval = (
                    time.monotonic() - last_command_at
                ) >= float(args.command_interval_seconds)

                if plan["has_target"] and plan["would_move_pan_tilt"] and command_allowed_by_interval:
                    if bool(args.execute):
                        backend_result = pan_tilt_service.move_delta(
                            pan_delta_degrees=float(plan["pan_delta_degrees"]),
                            tilt_delta_degrees=float(plan["tilt_delta_degrees"]),
                        )
                        if bool(backend_result.get("movement_executed", False)):
                            command_count += 1
                            last_command_at = time.monotonic()
                    else:
                        backend_result = {
                            "ok": True,
                            "movement_executed": False,
                            "preview_only": True,
                            "would_move_pan_tilt": True,
                        }
                elif plan["has_target"] and not plan["would_move_pan_tilt"]:
                    no_motion_count += 1

                step = {
                    "frame": frame_count,
                    "elapsed_ms": round(elapsed * 1000.0, 3),
                    "plan": plan,
                    "command_allowed_by_interval": command_allowed_by_interval,
                    "backend_result": backend_result,
                }
                steps.append(step)

                print(
                    "FRAME "
                    f"{frame_count:03d} "
                    f"target={plan['has_target']} "
                    f"reason={plan['reason']} "
                    f"pan={plan['pan_delta_degrees']} "
                    f"tilt={plan['tilt_delta_degrees']} "
                    f"execute={bool(args.execute)} "
                    f"moved={bool(backend_result and backend_result.get('movement_executed'))}"
                )

            except Exception as error:
                error_count += 1
                steps.append(
                    {
                        "frame": frame_count,
                        "elapsed_ms": round((time.monotonic() - started_at) * 1000.0, 3),
                        "error": f"{error.__class__.__name__}: {error}",
                    }
                )
                print(f"FRAME {frame_count:03d} error={error.__class__.__name__}: {error}")

            spent = time.monotonic() - loop_started
            sleep_seconds = frame_interval - spent
            if sleep_seconds > 0.0:
                time.sleep(sleep_seconds)

        if bool(args.execute) and bool(args.return_center):
            return_center_result = pan_tilt_service.center()

        pan_tilt_status = pan_tilt_service.status()

    finally:
        if camera is not None:
            try:
                camera.stop()
                camera.close()
            except Exception:
                pass

        try:
            pan_tilt_service.close()
        except Exception:
            pass

    payload = {
        "ok": target_count > 0 and error_count == 0 and (not bool(args.execute) or command_count > 0 or no_motion_count > 0),
        "execute": bool(args.execute),
        "preview_only": not bool(args.execute),
        "settings_path": str(settings_path),
        "calibration_state_path": str(state_path),
        "status_path": str(status_path),
        "cascade_path": str(cascade_path),
        "width": int(args.width),
        "height": int(args.height),
        "duration_seconds": float(args.duration_seconds),
        "target_fps": float(args.target_fps),
        "elapsed_ms": round((time.monotonic() - started_at) * 1000.0, 3),
        "frame_count": frame_count,
        "detection_count": detection_count,
        "target_count": target_count,
        "no_target_count": no_target_count,
        "no_motion_count": no_motion_count,
        "command_count": command_count,
        "error_count": error_count,
        "return_center": bool(args.return_center),
        "return_center_result": return_center_result,
        "readiness": readiness,
        "pan_tilt_status": pan_tilt_status,
        "steps": steps[-30:],
    }

    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=_json_default),
        encoding="utf-8",
    )
    return payload


def print_summary(payload: dict[str, Any]) -> None:
    print()
    print("NEXA Vision Runtime — FAST real face pan-tilt tracking loop")
    print(f"execute={payload['execute']}")
    print(f"preview_only={payload['preview_only']}")
    print(f"elapsed_ms={payload['elapsed_ms']}")
    print(f"frame_count={payload['frame_count']}")
    print(f"target_count={payload['target_count']}")
    print(f"command_count={payload['command_count']}")
    print(f"no_motion_count={payload['no_motion_count']}")
    print(f"no_target_count={payload['no_target_count']}")
    print(f"error_count={payload['error_count']}")
    print(f"pan_tilt_serial_write_count={payload.get('pan_tilt_status', {}).get('serial_write_count')}")
    print(f"return_center={payload['return_center']}")

    if payload["execute"]:
        print("HARDWARE LOOP: pan-tilt movement was allowed only by explicit gates.")
    else:
        print("PREVIEW LOOP: camera and tracking ran, but hardware movement was blocked.")

    print()
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=_json_default))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run a fast persistent Picamera2 face pan-tilt tracking loop. "
            "Default mode is preview-only and never sends pan-tilt movement."
        )
    )
    parser.add_argument("--settings", default=str(DEFAULT_SETTINGS_PATH))
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--status-path", default=str(DEFAULT_STATUS_PATH))
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--duration-seconds", type=float, default=12.0)
    parser.add_argument("--target-fps", type=float, default=6.0)
    parser.add_argument("--camera-warmup-seconds", type=float, default=0.8)
    parser.add_argument("--port", default=None)
    parser.add_argument("--baudrate", type=int, default=None)
    parser.add_argument("--max-step-degrees", type=float, default=1.0)
    parser.add_argument("--pan-gain-degrees", type=float, default=8.0)
    parser.add_argument("--tilt-gain-degrees", type=float, default=6.0)
    parser.add_argument("--dead-zone-x", type=float, default=0.03)
    parser.add_argument("--dead-zone-y", type=float, default=0.04)
    parser.add_argument("--min-face-area-ratio", type=float, default=0.015)
    parser.add_argument("--max-face-area-ratio", type=float, default=0.55)
    parser.add_argument("--command-interval-seconds", type=float, default=0.20)
    parser.add_argument("--speed", type=int, default=60)
    parser.add_argument("--acceleration", type=int, default=60)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-understand-this-moves-hardware", action="store_true")
    parser.add_argument("--confirm-text", default="")
    parser.add_argument("--return-center", action="store_true")
    args = parser.parse_args(argv)

    payload = run_fast_tracking_loop(args)
    print_summary(payload)
    return 0 if bool(payload.get("ok", False)) else 2


if __name__ == "__main__":
    raise SystemExit(main())
