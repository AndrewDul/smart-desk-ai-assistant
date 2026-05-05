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

from validate_vision_tracking_execution_readiness import load_settings, validate_settings


DEFAULT_SETTINGS_PATH = Path("config/settings.json")
DEFAULT_STATE_PATH = Path("var/data/pan_tilt_limit_calibration.json")
DEFAULT_STATUS_PATH = Path("var/data/vision_ultra_smooth_face_tracking_status.json")

CONFIRM_ENV_NAME = "CONFIRM_NEXA_ULTRA_SMOOTH_FACE_TRACKING"
CONFIRM_VALUE = "RUN_ULTRA_SMOOTH_FACE_TRACKING"

MAX_DURATION_SECONDS = 30.0
MAX_STEP_DEGREES = 1.0
MAX_SPEED = 95
MAX_ACCELERATION = 95
CENTER_REQUIRED_MAX_ABS_DEGREES = 2.0


@dataclass(slots=True)
class FaceBox:
    left: int
    top: int
    right: int
    bottom: int
    score: float
    source: str
    area_ratio: float = 0.0

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

    def clamp(self, frame_width: int, frame_height: int) -> "FaceBox":
        left = max(0, min(frame_width - 2, int(self.left)))
        top = max(0, min(frame_height - 2, int(self.top)))
        right = max(left + 1, min(frame_width, int(self.right)))
        bottom = max(top + 1, min(frame_height, int(self.bottom)))
        return FaceBox(
            left=left,
            top=top,
            right=right,
            bottom=bottom,
            score=float(self.score),
            source=str(self.source),
            area_ratio=float(self.area_ratio),
        )

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
            "score": round(self.score, 4),
            "source": self.source,
            "area_ratio": round(self.area_ratio, 5),
        }


class PersistentPanTiltSession:
    def __init__(
        self,
        *,
        execute: bool,
        port: str,
        baudrate: int,
        timeout_seconds: float,
        speed: int,
        acceleration: int,
        start_pan: float,
        start_tilt: float,
        safe_limits: dict[str, float],
        warmup_seconds: float,
        min_command_delta_degrees: float,
    ) -> None:
        self.execute = bool(execute)
        self.port = str(port)
        self.baudrate = int(baudrate)
        self.timeout_seconds = float(timeout_seconds)
        self.speed = int(speed)
        self.acceleration = int(acceleration)
        self.pan_angle = float(start_pan)
        self.tilt_angle = float(start_tilt)
        self.safe_limits = dict(safe_limits)
        self.warmup_seconds = float(warmup_seconds)
        self.min_command_delta_degrees = float(min_command_delta_degrees)

        self._serial = None
        self.prepare_sent = False
        self.serial_write_count = 0
        self.command_count = 0

    def __enter__(self) -> "PersistentPanTiltSession":
        if not self.execute:
            return self

        import serial

        self._serial = serial.Serial(self.port, self.baudrate, timeout=self.timeout_seconds)
        time.sleep(max(0.0, self.warmup_seconds))
        self._prepare_once()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._serial is not None:
            try:
                self._send({"T": 135}, pause=0.03)
            except Exception:
                pass
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def _send(self, command: dict[str, Any], *, pause: float = 0.0) -> None:
        line = json.dumps(command, separators=(",", ":")) + "\n"
        if self.execute:
            if self._serial is None:
                raise RuntimeError("Serial session is not open.")
            self._serial.write(line.encode("utf-8"))
            self._serial.flush()
        self.serial_write_count += 1
        if pause > 0.0:
            time.sleep(float(pause))

    def _move_command(self, pan: float, tilt: float) -> dict[str, Any]:
        return {
            "T": 133,
            "X": round(float(pan), 3),
            "Y": round(float(tilt), 3),
            "SPD": int(self.speed),
            "ACC": int(self.acceleration),
        }

    def _prepare_once(self) -> None:
        if self.prepare_sent:
            return

        for command, pause in [
            ({"T": 135}, 0.08),
            ({"T": 137, "s": 0, "y": 0}, 0.08),
            ({"T": 4, "cmd": 2}, 0.10),
            ({"T": 210, "cmd": 1}, 0.12),
            (self._move_command(self.pan_angle, self.tilt_angle), 0.08),
        ]:
            self._send(command, pause=pause)

        self.prepare_sent = True

    def _clamp_pan(self, value: float) -> float:
        return max(
            float(self.safe_limits["pan_min_degrees"]),
            min(float(self.safe_limits["pan_max_degrees"]), float(value)),
        )

    def _clamp_tilt(self, value: float) -> float:
        return max(
            float(self.safe_limits["tilt_min_degrees"]),
            min(float(self.safe_limits["tilt_max_degrees"]), float(value)),
        )

    def move_delta(self, *, pan_delta: float, tilt_delta: float) -> dict[str, Any]:
        target_pan = self._clamp_pan(self.pan_angle + float(pan_delta))
        target_tilt = self._clamp_tilt(self.tilt_angle + float(tilt_delta))

        applied_pan = target_pan - self.pan_angle
        applied_tilt = target_tilt - self.tilt_angle

        if (
            abs(applied_pan) < self.min_command_delta_degrees
            and abs(applied_tilt) < self.min_command_delta_degrees
        ):
            return {
                "ok": True,
                "movement_executed": False,
                "reason": "below_min_command_delta",
                "applied_pan_delta_degrees": round(applied_pan, 4),
                "applied_tilt_delta_degrees": round(applied_tilt, 4),
                "pan_angle": round(self.pan_angle, 4),
                "tilt_angle": round(self.tilt_angle, 4),
            }

        self._send(self._move_command(target_pan, target_tilt), pause=0.0)
        self.pan_angle = target_pan
        self.tilt_angle = target_tilt
        self.command_count += 1

        return {
            "ok": True,
            "movement_executed": bool(self.execute),
            "preview_only": not bool(self.execute),
            "applied_pan_delta_degrees": round(applied_pan, 4),
            "applied_tilt_delta_degrees": round(applied_tilt, 4),
            "target_pan_degrees": round(target_pan, 4),
            "target_tilt_degrees": round(target_tilt, 4),
            "pan_angle": round(self.pan_angle, 4),
            "tilt_angle": round(self.tilt_angle, 4),
            "serial_write_count": self.serial_write_count,
        }

    def center(self) -> dict[str, Any]:
        return self.move_delta(pan_delta=-self.pan_angle, tilt_delta=-self.tilt_angle)

    def status(self) -> dict[str, Any]:
        return {
            "backend": "waveshare_persistent_tracking_session",
            "execute": self.execute,
            "port": self.port,
            "baudrate": self.baudrate,
            "speed": self.speed,
            "acceleration": self.acceleration,
            "pan_angle": round(self.pan_angle, 4),
            "tilt_angle": round(self.tilt_angle, 4),
            "serial_write_count": self.serial_write_count,
            "command_count": self.command_count,
            "prepare_sent": self.prepare_sent,
            "safe_limits": self.safe_limits,
        }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing file: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise SystemExit(f"Invalid JSON in {path}: {error}") from error


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
        raise SystemExit("Refusing because default config allows physical movement.")
    return result


def _require_execute_confirmation(*, execute: bool, understand: bool, confirm_text: str) -> None:
    if not execute:
        return
    if not understand:
        raise SystemExit("Refusing to move. Add --i-understand-this-moves-hardware.")
    if confirm_text != CONFIRM_VALUE:
        raise SystemExit(f"Refusing to move. Add --confirm-text {CONFIRM_VALUE}.")
    if os.environ.get(CONFIRM_ENV_NAME, "") != CONFIRM_VALUE:
        raise SystemExit(f"Refusing to move. Set {CONFIRM_ENV_NAME}={CONFIRM_VALUE}.")


def _require_state_near_center_for_execute(*, state: dict[str, Any], execute: bool) -> None:
    if not execute:
        return
    current_x = _safe_float(state.get("x"), 0.0)
    current_y = _safe_float(state.get("y"), 0.0)
    if abs(current_x) <= CENTER_REQUIRED_MAX_ABS_DEGREES and abs(current_y) <= CENTER_REQUIRED_MAX_ABS_DEGREES:
        return
    raise SystemExit(
        "Refusing execute because calibration state is not near center. "
        f"Current state is X={current_x} Y={current_y}. Run safe center recovery first."
    )


def _find_haar_cascade() -> Path:
    filename = "haarcascade_frontalface_default.xml"
    candidates = [
        Path("/usr/share/opencv4/haarcascades") / filename,
        Path("/usr/share/opencv/haarcascades") / filename,
        Path("/usr/local/share/opencv4/haarcascades") / filename,
        Path("/usr/local/share/opencv/haarcascades") / filename,
    ]

    cv2_data = getattr(cv2, "data", None)
    haar_dir = getattr(cv2_data, "haarcascades", None) if cv2_data is not None else None
    if haar_dir:
        candidates.insert(0, Path(haar_dir) / filename)

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise SystemExit("Could not find haarcascade_frontalface_default.xml.")


def _open_camera(*, width: int, height: int, warmup_seconds: float):
    from picamera2 import Picamera2

    camera = Picamera2()
    config = camera.create_preview_configuration(
        main={"size": (int(width), int(height)), "format": "RGB888"},
        buffer_count=4,
    )
    camera.configure(config)
    camera.start()
    time.sleep(max(0.0, float(warmup_seconds)))
    return camera


def _detect_face(
    *,
    cascade: Any,
    gray: np.ndarray,
    frame_width: int,
    frame_height: int,
    min_face_area_ratio: float,
    max_face_area_ratio: float,
    min_face_size_px: int,
) -> FaceBox | None:
    frame_area = max(1, frame_width * frame_height)
    best: FaceBox | None = None

    profiles = (
        ("fast_1.12_4", 1.12, 4),
        ("fast_1.08_4", 1.08, 4),
        ("fast_1.05_3", 1.05, 3),
    )

    equalized = cv2.equalizeHist(gray)

    for gray_label, source_gray in (("equalized", equalized), ("prepared", gray)):
        for profile, scale_factor, min_neighbors in profiles:
            boxes = cascade.detectMultiScale(
                source_gray,
                scaleFactor=float(scale_factor),
                minNeighbors=int(min_neighbors),
                minSize=(int(min_face_size_px), int(min_face_size_px)),
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

                candidate = FaceBox(
                    left=x,
                    top=y,
                    right=x + w,
                    bottom=y + h,
                    score=0.95,
                    source=f"haar:{profile}:{gray_label}",
                    area_ratio=area_ratio,
                ).clamp(frame_width, frame_height)

                if best is None or candidate.area > best.area:
                    best = candidate

            if best is not None:
                return best

    return best


def _make_template(gray: np.ndarray, box: FaceBox) -> np.ndarray:
    roi = gray[box.top:box.bottom, box.left:box.right]
    if roi.size == 0:
        return np.empty((0, 0), dtype=np.uint8)
    return roi.copy()


def _track_template(
    *,
    gray: np.ndarray,
    previous_box: FaceBox,
    template: np.ndarray,
    search_margin_ratio: float,
    min_score: float,
) -> FaceBox | None:
    if template.size == 0:
        return None

    frame_height, frame_width = gray.shape[:2]
    width = previous_box.width
    height = previous_box.height

    margin_x = int(width * search_margin_ratio)
    margin_y = int(height * search_margin_ratio)

    search_left = max(0, previous_box.left - margin_x)
    search_top = max(0, previous_box.top - margin_y)
    search_right = min(frame_width, previous_box.right + margin_x)
    search_bottom = min(frame_height, previous_box.bottom + margin_y)

    search = gray[search_top:search_bottom, search_left:search_right]
    if search.size == 0:
        return None
    if search.shape[0] < template.shape[0] or search.shape[1] < template.shape[1]:
        return None

    result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, max_value, _, max_location = cv2.minMaxLoc(result)

    if float(max_value) < min_score:
        return None

    left = search_left + int(max_location[0])
    top = search_top + int(max_location[1])
    return FaceBox(
        left=left,
        top=top,
        right=left + template.shape[1],
        bottom=top + template.shape[0],
        score=float(max_value),
        source="template",
        area_ratio=previous_box.area_ratio,
    ).clamp(frame_width, frame_height)


def _compute_motion(
    *,
    face: FaceBox | None,
    frame_width: int,
    frame_height: int,
    smoothed_center: tuple[float, float] | None,
    smoothing_alpha: float,
    dead_zone_x: float,
    dead_zone_y: float,
    pan_gain_degrees: float,
    tilt_gain_degrees: float,
    max_step_degrees: float,
) -> tuple[dict[str, Any], tuple[float, float] | None]:
    if face is None:
        return (
            {
                "has_target": False,
                "reason": "no_target",
                "pan_delta_degrees": 0.0,
                "tilt_delta_degrees": 0.0,
                "would_move_pan_tilt": False,
                "target": None,
                "diagnostics": {},
            },
            smoothed_center,
        )

    center_x = face.center_x_norm(frame_width)
    center_y = face.center_y_norm(frame_height)

    if smoothed_center is None:
        smooth_x, smooth_y = center_x, center_y
    else:
        alpha = _clamp(float(smoothing_alpha), 0.0, 1.0)
        smooth_x = alpha * center_x + (1.0 - alpha) * smoothed_center[0]
        smooth_y = alpha * center_y + (1.0 - alpha) * smoothed_center[1]

    offset_x = smooth_x - 0.5
    offset_y = smooth_y - 0.5

    raw_pan = offset_x * float(pan_gain_degrees)
    raw_tilt = -offset_y * float(tilt_gain_degrees)

    pan_delta = 0.0 if abs(offset_x) < dead_zone_x else raw_pan
    tilt_delta = 0.0 if abs(offset_y) < dead_zone_y else raw_tilt

    pan_delta = _clamp(pan_delta, -max_step_degrees, max_step_degrees)
    tilt_delta = _clamp(tilt_delta, -max_step_degrees, max_step_degrees)

    would_move = abs(pan_delta) > 0.0001 or abs(tilt_delta) > 0.0001

    return (
        {
            "has_target": True,
            "reason": "recenter_target" if would_move else "target_centered",
            "pan_delta_degrees": round(pan_delta, 4),
            "tilt_delta_degrees": round(tilt_delta, 4),
            "would_move_pan_tilt": would_move,
            "target": face.to_dict(frame_width=frame_width, frame_height=frame_height),
            "diagnostics": {
                "center_x_norm": round(center_x, 5),
                "center_y_norm": round(center_y, 5),
                "smooth_x_norm": round(smooth_x, 5),
                "smooth_y_norm": round(smooth_y, 5),
                "offset_x": round(offset_x, 4),
                "offset_y": round(offset_y, 4),
                "raw_pan_delta_degrees": round(raw_pan, 4),
                "raw_tilt_delta_degrees": round(raw_tilt, 4),
            },
        },
        (smooth_x, smooth_y),
    )


def _validate_args(args: argparse.Namespace) -> None:
    if args.duration_seconds <= 0.0 or args.duration_seconds > MAX_DURATION_SECONDS:
        raise SystemExit(f"Refusing duration outside 0..{MAX_DURATION_SECONDS} seconds.")
    if args.target_fps < 1.0 or args.target_fps > 30.0:
        raise SystemExit("Refusing target FPS outside 1..30.")
    if args.max_step_degrees <= 0.0 or args.max_step_degrees > MAX_STEP_DEGREES:
        raise SystemExit(f"Refusing max step above {MAX_STEP_DEGREES} degree.")
    if args.command_interval_seconds < 0.02:
        raise SystemExit("Refusing command interval below 0.02 seconds.")
    if not (1 <= args.speed <= MAX_SPEED):
        raise SystemExit(f"Refusing speed outside 1..{MAX_SPEED}.")
    if not (1 <= args.acceleration <= MAX_ACCELERATION):
        raise SystemExit(f"Refusing acceleration outside 1..{MAX_ACCELERATION}.")


def run(args: argparse.Namespace) -> dict[str, Any]:
    _validate_args(args)
    _require_execute_confirmation(
        execute=bool(args.execute),
        understand=bool(args.i_understand_this_moves_hardware),
        confirm_text=str(args.confirm_text),
    )

    settings_path = Path(args.settings)
    state_path = Path(args.state)
    status_path = Path(args.status_path)

    readiness = _validate_default_readiness(settings_path)
    state = _load_json(state_path)
    _require_state_near_center_for_execute(state=state, execute=bool(args.execute))

    safe_limits = _safe_limits_from_state(state)
    start_pan = _safe_float(state.get("x"), 0.0)
    start_tilt = _safe_float(state.get("y"), 0.0)

    cascade_path = _find_haar_cascade()
    cascade = cv2.CascadeClassifier(str(cascade_path))
    if cascade.empty():
        raise SystemExit(f"Failed to load Haar cascade: {cascade_path}")

    port = str(args.port or state.get("port") or "/dev/serial0")
    baudrate = int(args.baudrate or state.get("baudrate") or 115200)

    frame_interval = 1.0 / float(args.target_fps)
    started_at = time.monotonic()
    last_command_at = 0.0

    camera = None
    tracked_box: FaceBox | None = None
    template: np.ndarray | None = None
    smoothed_center: tuple[float, float] | None = None

    frame_count = 0
    haar_detection_count = 0
    template_tracking_count = 0
    target_count = 0
    no_target_count = 0
    no_motion_count = 0
    command_count = 0
    skipped_by_interval_count = 0
    error_count = 0
    steps: list[dict[str, Any]] = []
    return_center_result: dict[str, Any] | None = None
    session_status: dict[str, Any] = {}

    try:
        camera = _open_camera(
            width=int(args.width),
            height=int(args.height),
            warmup_seconds=float(args.camera_warmup_seconds),
        )

        with PersistentPanTiltSession(
            execute=bool(args.execute),
            port=port,
            baudrate=baudrate,
            timeout_seconds=float(args.timeout_seconds),
            speed=int(args.speed),
            acceleration=int(args.acceleration),
            start_pan=start_pan,
            start_tilt=start_tilt,
            safe_limits=safe_limits,
            warmup_seconds=float(args.serial_warmup_seconds),
            min_command_delta_degrees=float(args.min_command_delta_degrees),
        ) as pan_tilt:
            while True:
                frame_started = time.monotonic()
                elapsed = frame_started - started_at
                if elapsed >= float(args.duration_seconds):
                    break

                try:
                    frame_rgb = camera.capture_array()
                    frame_count += 1

                    gray = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2GRAY)

                    must_detect = (
                        tracked_box is None
                        or template is None
                        or frame_count % max(1, int(args.detect_every_n_frames)) == 0
                    )

                    face: FaceBox | None = None

                    if not must_detect and tracked_box is not None and template is not None:
                        face = _track_template(
                            gray=gray,
                            previous_box=tracked_box,
                            template=template,
                            search_margin_ratio=float(args.search_margin_ratio),
                            min_score=float(args.template_min_score),
                        )
                        if face is not None:
                            template_tracking_count += 1

                    if face is None:
                        face = _detect_face(
                            cascade=cascade,
                            gray=gray,
                            frame_width=int(args.width),
                            frame_height=int(args.height),
                            min_face_area_ratio=float(args.min_face_area_ratio),
                            max_face_area_ratio=float(args.max_face_area_ratio),
                            min_face_size_px=int(args.min_face_size_px),
                        )
                        if face is not None:
                            haar_detection_count += 1

                    if face is not None:
                        target_count += 1
                        tracked_box = face
                        if frame_count % max(1, int(args.template_refresh_every_n_frames)) == 0 or template is None:
                            template = _make_template(gray, face)
                    else:
                        no_target_count += 1
                        tracked_box = None
                        template = None

                    plan, smoothed_center = _compute_motion(
                        face=face,
                        frame_width=int(args.width),
                        frame_height=int(args.height),
                        smoothed_center=smoothed_center,
                        smoothing_alpha=float(args.smoothing_alpha),
                        dead_zone_x=float(args.dead_zone_x),
                        dead_zone_y=float(args.dead_zone_y),
                        pan_gain_degrees=float(args.pan_gain_degrees),
                        tilt_gain_degrees=float(args.tilt_gain_degrees),
                        max_step_degrees=float(args.max_step_degrees),
                    )

                    backend_result: dict[str, Any] | None = None
                    can_send = (time.monotonic() - last_command_at) >= float(args.command_interval_seconds)

                    if plan["has_target"] and plan["would_move_pan_tilt"]:
                        if can_send:
                            backend_result = pan_tilt.move_delta(
                                pan_delta=float(plan["pan_delta_degrees"]),
                                tilt_delta=float(plan["tilt_delta_degrees"]),
                            )
                            if bool(backend_result.get("movement_executed", False)) or bool(backend_result.get("preview_only", False)):
                                command_count += 1
                                last_command_at = time.monotonic()
                        else:
                            skipped_by_interval_count += 1
                    elif plan["has_target"]:
                        no_motion_count += 1

                    if frame_count % max(1, int(args.print_every_n_frames)) == 0:
                        print(
                            "FRAME "
                            f"{frame_count:03d} "
                            f"target={plan['has_target']} "
                            f"source={(face.source if face else None)} "
                            f"pan={plan['pan_delta_degrees']} "
                            f"tilt={plan['tilt_delta_degrees']} "
                            f"cmd={command_count}"
                        )

                    steps.append(
                        {
                            "frame": frame_count,
                            "elapsed_ms": round(elapsed * 1000.0, 3),
                            "plan": plan,
                            "backend_result": backend_result,
                            "can_send": can_send,
                        }
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

                spent = time.monotonic() - frame_started
                sleep_seconds = frame_interval - spent
                if sleep_seconds > 0.0:
                    time.sleep(sleep_seconds)

            if bool(args.execute) and bool(args.return_center):
                return_center_result = pan_tilt.center()

            session_status = pan_tilt.status()

    finally:
        if camera is not None:
            try:
                camera.stop()
                camera.close()
            except Exception:
                pass

    elapsed_total = time.monotonic() - started_at
    observed_fps = frame_count / elapsed_total if elapsed_total > 0 else 0.0

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
        "observed_fps": round(observed_fps, 3),
        "elapsed_ms": round(elapsed_total * 1000.0, 3),
        "frame_count": frame_count,
        "target_count": target_count,
        "haar_detection_count": haar_detection_count,
        "template_tracking_count": template_tracking_count,
        "no_target_count": no_target_count,
        "no_motion_count": no_motion_count,
        "command_count": command_count,
        "skipped_by_interval_count": skipped_by_interval_count,
        "error_count": error_count,
        "return_center": bool(args.return_center),
        "return_center_result": return_center_result,
        "readiness": readiness,
        "pan_tilt_status": session_status,
        "steps": steps[-40:],
    }

    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return payload


def print_summary(payload: dict[str, Any]) -> None:
    print()
    print("NEXA Vision Runtime — ULTRA smooth face pan-tilt tracking loop")
    print(f"execute={payload['execute']}")
    print(f"preview_only={payload['preview_only']}")
    print(f"elapsed_ms={payload['elapsed_ms']}")
    print(f"frame_count={payload['frame_count']}")
    print(f"observed_fps={payload['observed_fps']}")
    print(f"target_count={payload['target_count']}")
    print(f"haar_detection_count={payload['haar_detection_count']}")
    print(f"template_tracking_count={payload['template_tracking_count']}")
    print(f"command_count={payload['command_count']}")
    print(f"no_motion_count={payload['no_motion_count']}")
    print(f"no_target_count={payload['no_target_count']}")
    print(f"skipped_by_interval_count={payload['skipped_by_interval_count']}")
    print(f"error_count={payload['error_count']}")
    print(f"serial_write_count={payload.get('pan_tilt_status', {}).get('serial_write_count')}")
    print(f"return_center={payload['return_center']}")

    if payload["execute"]:
        print("HARDWARE LOOP: persistent serial + ROI tracker was allowed only by explicit gates.")
    else:
        print("PREVIEW LOOP: ROI tracking ran, but hardware serial was not opened.")

    print()
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run ultra-smooth ROI face tracking with persistent pan-tilt serial session."
    )
    parser.add_argument("--settings", default=str(DEFAULT_SETTINGS_PATH))
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--status-path", default=str(DEFAULT_STATUS_PATH))
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--duration-seconds", type=float, default=12.0)
    parser.add_argument("--target-fps", type=float, default=20.0)
    parser.add_argument("--camera-warmup-seconds", type=float, default=0.5)
    parser.add_argument("--port", default=None)
    parser.add_argument("--baudrate", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=0.03)
    parser.add_argument("--serial-warmup-seconds", type=float, default=0.25)
    parser.add_argument("--max-step-degrees", type=float, default=0.55)
    parser.add_argument("--pan-gain-degrees", type=float, default=9.0)
    parser.add_argument("--tilt-gain-degrees", type=float, default=7.0)
    parser.add_argument("--dead-zone-x", type=float, default=0.018)
    parser.add_argument("--dead-zone-y", type=float, default=0.025)
    parser.add_argument("--smoothing-alpha", type=float, default=0.72)
    parser.add_argument("--min-face-area-ratio", type=float, default=0.006)
    parser.add_argument("--max-face-area-ratio", type=float, default=0.65)
    parser.add_argument("--min-face-size-px", type=int, default=22)
    parser.add_argument("--detect-every-n-frames", type=int, default=10)
    parser.add_argument("--template-refresh-every-n-frames", type=int, default=5)
    parser.add_argument("--search-margin-ratio", type=float, default=1.2)
    parser.add_argument("--template-min-score", type=float, default=0.42)
    parser.add_argument("--command-interval-seconds", type=float, default=0.045)
    parser.add_argument("--min-command-delta-degrees", type=float, default=0.035)
    parser.add_argument("--speed", type=int, default=90)
    parser.add_argument("--acceleration", type=int, default=90)
    parser.add_argument("--print-every-n-frames", type=int, default=6)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-understand-this-moves-hardware", action="store_true")
    parser.add_argument("--confirm-text", default="")
    parser.add_argument("--return-center", action="store_true")
    args = parser.parse_args(argv)

    payload = run(args)
    print_summary(payload)
    return 0 if bool(payload.get("ok", False)) else 2


if __name__ == "__main__":
    raise SystemExit(main())
