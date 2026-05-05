#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from modules.devices.pan_tilt import PanTiltService
from modules.devices.vision.tracking import VisionTrackingService
from modules.runtime.contracts import VisionObservation
from validate_vision_tracking_execution_readiness import load_settings, validate_settings


DEFAULT_SETTINGS_PATH = Path("config/settings.json")
DEFAULT_STATE_PATH = Path("var/data/pan_tilt_limit_calibration.json")
DEFAULT_STATUS_PATH = Path("var/data/vision_tracking_single_step_status.json")

CONFIRM_ENV_NAME = "CONFIRM_NEXA_SINGLE_TRACKING_STEP"
CONFIRM_VALUE = "RUN_SINGLE_TRACKING_STEP"

MAX_SINGLE_STEP_DEGREES = 0.5
MAX_SPEED = 60
MAX_ACCELERATION = 60
SYNTHETIC_GAIN_DEGREES = 2.0
CENTER_REQUIRED_MAX_ABS_DEGREES = 1.0

SerialFactory = Callable[..., Any]


class _SyntheticVisionBackend:
    def __init__(self, observation: VisionObservation) -> None:
        self.observation = observation
        self.force_refresh_values: list[bool] = []

    def latest_observation(self, *, force_refresh: bool = False) -> VisionObservation:
        self.force_refresh_values.append(bool(force_refresh))
        return self.observation


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return dict(value)
    return {"value": value}


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(float(lower), min(float(upper), float(value)))


def _load_calibration_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(
            f"Missing calibration state: {path}. "
            "Run pan-tilt calibration/center recovery before this runtime step."
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


def _validate_default_readiness(settings_path: Path) -> dict[str, Any]:
    result = validate_settings(load_settings(settings_path))
    if not bool(result.get("ok", False)):
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        raise SystemExit(
            "Default tracking readiness validation failed. "
            "Refusing to prepare a hardware runtime step."
        )
    return result


def _validate_single_step_request(
    *,
    pan_delta: float,
    tilt_delta: float,
    speed: int,
    acceleration: int,
) -> None:
    if abs(float(pan_delta)) > MAX_SINGLE_STEP_DEGREES:
        raise SystemExit(
            f"Refusing pan delta {pan_delta}. Maximum single-step pan delta is "
            f"{MAX_SINGLE_STEP_DEGREES} degree."
        )

    if abs(float(tilt_delta)) > MAX_SINGLE_STEP_DEGREES:
        raise SystemExit(
            f"Refusing tilt delta {tilt_delta}. Maximum single-step tilt delta is "
            f"{MAX_SINGLE_STEP_DEGREES} degree."
        )

    if abs(float(pan_delta)) == 0.0 and abs(float(tilt_delta)) == 0.0:
        raise SystemExit("Refusing zero movement tracking step.")

    if not (1 <= int(speed) <= MAX_SPEED):
        raise SystemExit(f"Refusing speed {speed}. Allowed range is 1..{MAX_SPEED}.")

    if not (1 <= int(acceleration) <= MAX_ACCELERATION):
        raise SystemExit(
            f"Refusing acceleration {acceleration}. Allowed range is 1..{MAX_ACCELERATION}."
        )


def _require_execute_confirmation(*, execute: bool, understand: bool, confirm_text: str) -> None:
    if not execute:
        return

    if not understand:
        raise SystemExit(
            "Refusing to move. Add --i-understand-this-moves-hardware for this hardware step."
        )

    if confirm_text != CONFIRM_VALUE:
        raise SystemExit(
            f"Refusing to move. Add --confirm-text {CONFIRM_VALUE} for this hardware step."
        )

    if os.environ.get(CONFIRM_ENV_NAME, "") != CONFIRM_VALUE:
        raise SystemExit(
            f"Refusing to move. Set {CONFIRM_ENV_NAME}={CONFIRM_VALUE} for this hardware step."
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
        "Run safe center recovery first, then re-run preview."
    )


def _target_within_marked_limits(*, state: dict[str, Any], target_x: float, target_y: float) -> bool:
    marked = state["marked_limits"]
    pan_left = _safe_float(marked.get("pan_left_x"))
    pan_right = _safe_float(marked.get("pan_right_x"))
    tilt_min = _safe_float(marked.get("tilt_min_y"))
    tilt_max = _safe_float(marked.get("tilt_max_y"))
    lower_pan = min(pan_left, pan_right)
    upper_pan = max(pan_left, pan_right)
    lower_tilt = min(tilt_min, tilt_max)
    upper_tilt = max(tilt_min, tilt_max)
    return lower_pan <= target_x <= upper_pan and lower_tilt <= target_y <= upper_tilt


def _build_synthetic_face_observation(
    *,
    pan_delta: float,
    tilt_delta: float,
    frame_width: int = 1280,
    frame_height: int = 720,
) -> VisionObservation:
    center_x_norm = _clamp(0.5 + (float(pan_delta) / SYNTHETIC_GAIN_DEGREES), 0.1, 0.9)
    center_y_norm = _clamp(0.5 - (float(tilt_delta) / SYNTHETIC_GAIN_DEGREES), 0.1, 0.9)

    box_width = 160
    box_height = 160
    center_x_px = int(round(center_x_norm * frame_width))
    center_y_px = int(round(center_y_norm * frame_height))
    left = int(_clamp(center_x_px - (box_width / 2), 0, frame_width - box_width))
    top = int(_clamp(center_y_px - (box_height / 2), 0, frame_height - box_height))
    right = left + box_width
    bottom = top + box_height

    return VisionObservation(
        detected=True,
        user_present=True,
        labels=["face"],
        confidence=0.9,
        metadata={
            "frame_width": frame_width,
            "frame_height": frame_height,
            "perception": {
                "faces": [
                    {
                        "confidence": 0.95,
                        "bounding_box": {
                            "left": left,
                            "top": top,
                            "right": right,
                            "bottom": bottom,
                        },
                        "metadata": {
                            "source": "synthetic_single_tracking_step",
                            "requested_pan_delta_degrees": round(float(pan_delta), 4),
                            "requested_tilt_delta_degrees": round(float(tilt_delta), 4),
                        },
                    }
                ],
                "people": [],
            },
        },
    )


def _build_pan_tilt_config(
    *,
    settings: dict[str, Any],
    state_path: Path,
    port: str,
    baudrate: int,
    speed: int,
    acceleration: int,
    execute: bool,
    serial_warmup_seconds: float,
    read_after_write_seconds: float,
) -> dict[str, Any]:
    config = copy.deepcopy(settings.get("pan_tilt", {}))
    config.update(
        {
            "enabled": True,
            "backend": "waveshare_serial",
            "hardware_enabled": bool(execute),
            "motion_enabled": bool(execute),
            "dry_run": not bool(execute),
            "device": str(port),
            "baudrate": int(baudrate),
            "timeout_seconds": float(config.get("timeout_seconds", 0.2)),
            "protocol": "waveshare_json_serial",
            "startup_policy": "no_motion",
            "calibration_required": True,
            "allow_uncalibrated_motion": False,
            "calibration_state_path": str(state_path),
            "max_step_degrees": MAX_SINGLE_STEP_DEGREES,
            "command_speed": int(speed),
            "command_acceleration": int(acceleration),
            "serial_warmup_seconds": float(serial_warmup_seconds),
            "read_after_write_seconds": float(read_after_write_seconds),
        }
    )
    return config


def _build_tracking_config(
    *,
    settings: dict[str, Any],
    status_path: Path,
    execute: bool,
) -> dict[str, Any]:
    config = copy.deepcopy(settings.get("vision_tracking", {}))
    config.update(
        {
            "enabled": True,
            "persist_status": True,
            "status_path": str(status_path),
        }
    )
    config["policy"] = {
        "enabled": True,
        "dead_zone_x": 0.0,
        "dead_zone_y": 0.0,
        "pan_gain_degrees": SYNTHETIC_GAIN_DEGREES,
        "tilt_gain_degrees": SYNTHETIC_GAIN_DEGREES,
        "max_step_degrees": MAX_SINGLE_STEP_DEGREES,
        "limit_margin_degrees": 1.0,
        "base_yaw_assist_edge_threshold": 0.42,
    }
    config["motion_executor"] = {
        "dry_run": True,
        "movement_execution_enabled": False,
        "pan_tilt_movement_execution_enabled": False,
        "base_yaw_assist_execution_enabled": False,
        "base_forward_backward_movement_enabled": False,
    }
    config["pan_tilt_adapter"] = {
        "dry_run": not bool(execute),
        "backend_command_execution_enabled": bool(execute),
        "runtime_hardware_execution_enabled": bool(execute),
        "physical_movement_confirmed": bool(execute),
        "require_calibrated_limits": True,
        "require_no_motion_startup_policy": True,
        "max_allowed_pan_delta_degrees": MAX_SINGLE_STEP_DEGREES,
        "max_allowed_tilt_delta_degrees": MAX_SINGLE_STEP_DEGREES,
    }
    return config


def run_single_tracking_step(
    *,
    settings_path: Path,
    state_path: Path,
    status_path: Path,
    port: str | None,
    baudrate: int | None,
    pan_delta: float,
    tilt_delta: float,
    speed: int,
    acceleration: int,
    serial_warmup_seconds: float,
    read_after_write_seconds: float,
    execute: bool,
    understand: bool,
    confirm_text: str,
    serial_factory: SerialFactory | None = None,
) -> dict[str, Any]:
    _validate_single_step_request(
        pan_delta=pan_delta,
        tilt_delta=tilt_delta,
        speed=speed,
        acceleration=acceleration,
    )
    _require_execute_confirmation(
        execute=bool(execute),
        understand=bool(understand),
        confirm_text=str(confirm_text),
    )

    settings = dict(load_settings(settings_path))
    readiness = _validate_default_readiness(settings_path)
    state = _load_calibration_state(state_path)
    _require_state_near_center_for_execute(state=state, execute=bool(execute))

    current_x = _safe_float(state.get("x"), 0.0)
    current_y = _safe_float(state.get("y"), 0.0)
    target_x = current_x + float(pan_delta)
    target_y = current_y + float(tilt_delta)
    if not _target_within_marked_limits(state=state, target_x=target_x, target_y=target_y):
        raise SystemExit(
            f"Refusing target X={target_x} Y={target_y}. "
            "Target is outside marked calibration limits."
        )

    pan_tilt_settings = settings.get("pan_tilt", {})
    pan_tilt_config = _build_pan_tilt_config(
        settings=settings,
        state_path=state_path,
        port=str(port or state.get("port") or pan_tilt_settings.get("device") or "/dev/serial0"),
        baudrate=int(baudrate or state.get("baudrate") or pan_tilt_settings.get("baudrate") or 115200),
        speed=int(speed),
        acceleration=int(acceleration),
        execute=bool(execute),
        serial_warmup_seconds=float(serial_warmup_seconds),
        read_after_write_seconds=float(read_after_write_seconds),
    )
    tracking_config = _build_tracking_config(
        settings=settings,
        status_path=status_path,
        execute=bool(execute),
    )

    observation = _build_synthetic_face_observation(
        pan_delta=float(pan_delta),
        tilt_delta=float(tilt_delta),
    )
    vision_backend = _SyntheticVisionBackend(observation)
    pan_tilt_backend = PanTiltService(
        pan_tilt_config,
        serial_factory=serial_factory,
    )
    tracking_service = VisionTrackingService(
        vision_backend=vision_backend,
        pan_tilt_backend=pan_tilt_backend,
        config=tracking_config,
    )

    plan = tracking_service.plan_once(force_refresh=False)
    execution = tracking_service.latest_execution_result()
    adapter_result = tracking_service.latest_pan_tilt_adapter_result()
    pan_tilt_status = pan_tilt_backend.status()
    tracking_status = tracking_service.status()

    adapter_payload = _as_dict(adapter_result)
    executed = bool(adapter_payload.get("backend_command_executed", False))
    ok = bool(executed) if execute else True

    return {
        "ok": ok,
        "execute": bool(execute),
        "preview_only": not bool(execute),
        "settings_path": str(settings_path),
        "calibration_state_path": str(state_path),
        "status_path": str(status_path),
        "requested_pan_delta_degrees": round(float(pan_delta), 4),
        "requested_tilt_delta_degrees": round(float(tilt_delta), 4),
        "target_x_degrees": round(target_x, 4),
        "target_y_degrees": round(target_y, 4),
        "readiness": readiness,
        "vision_backend_force_refresh_values": vision_backend.force_refresh_values,
        "plan": _as_dict(plan),
        "execution_result": _as_dict(execution),
        "pan_tilt_adapter_result": adapter_payload,
        "pan_tilt_status": pan_tilt_status,
        "vision_tracking_status": tracking_status,
    }


def print_summary(payload: dict[str, Any]) -> None:
    print("NEXA Vision Runtime — single runtime-gated pan-tilt tracking step")
    print(f"execute={payload['execute']}")
    print(f"preview_only={payload['preview_only']}")
    print(f"settings={payload['settings_path']}")
    print(f"calibration_state={payload['calibration_state_path']}")
    print(f"status_path={payload['status_path']}")
    print(
        "requested_delta="
        f"pan:{payload['requested_pan_delta_degrees']} "
        f"tilt:{payload['requested_tilt_delta_degrees']}"
    )
    adapter = payload.get("pan_tilt_adapter_result", {})
    print(f"adapter_status={adapter.get('status')}")
    print(f"backend_command_executed={adapter.get('backend_command_executed')}")
    print()
    if payload["execute"]:
        print("HARDWARE STEP: command execution was allowed only by explicit in-memory gates.")
    else:
        print("PREVIEW ONLY: no serial port opened and no hardware movement commands sent.")
    print()
    print(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True, default=_json_default))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run one controlled NEXA VisionTrackingService pan-tilt step. "
            "Default mode is preview only and never opens the serial port."
        )
    )
    parser.add_argument("--settings", default=str(DEFAULT_SETTINGS_PATH))
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--status-path", default=str(DEFAULT_STATUS_PATH))
    parser.add_argument("--port", default=None)
    parser.add_argument("--baudrate", type=int, default=None)
    parser.add_argument("--pan-delta", type=float, default=0.25)
    parser.add_argument("--tilt-delta", type=float, default=0.0)
    parser.add_argument("--speed", type=int, default=45)
    parser.add_argument("--acceleration", type=int, default=45)
    parser.add_argument("--serial-warmup-seconds", type=float, default=0.05)
    parser.add_argument("--read-after-write-seconds", type=float, default=0.0)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-understand-this-moves-hardware", action="store_true")
    parser.add_argument("--confirm-text", default="")
    args = parser.parse_args(argv)

    payload = run_single_tracking_step(
        settings_path=Path(args.settings),
        state_path=Path(args.state),
        status_path=Path(args.status_path),
        port=args.port,
        baudrate=args.baudrate,
        pan_delta=float(args.pan_delta),
        tilt_delta=float(args.tilt_delta),
        speed=int(args.speed),
        acceleration=int(args.acceleration),
        serial_warmup_seconds=float(args.serial_warmup_seconds),
        read_after_write_seconds=float(args.read_after_write_seconds),
        execute=bool(args.execute),
        understand=bool(args.i_understand_this_moves_hardware),
        confirm_text=str(args.confirm_text),
    )
    print_summary(payload)

    if args.execute and not bool(payload.get("ok", False)):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
