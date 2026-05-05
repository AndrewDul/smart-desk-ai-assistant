#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
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
from modules.devices.vision.camera_service import CameraService
from modules.devices.vision.tracking import VisionTrackingService
from validate_vision_tracking_execution_readiness import load_settings, validate_settings


DEFAULT_SETTINGS_PATH = Path("config/settings.json")
DEFAULT_STATE_PATH = Path("var/data/pan_tilt_limit_calibration.json")
DEFAULT_STATUS_PATH = Path("var/data/vision_real_face_tracking_loop_status.json")

CONFIRM_ENV_NAME = "CONFIRM_NEXA_REAL_FACE_TRACKING_LOOP"
CONFIRM_VALUE = "RUN_REAL_FACE_TRACKING_LOOP"

MAX_SINGLE_STEP_DEGREES = 1.0
MAX_LOOP_STEPS = 30
MAX_LOOP_SECONDS = 30.0
MAX_SPEED = 70
MAX_ACCELERATION = 70
CENTER_REQUIRED_MAX_ABS_DEGREES = 1.0

ServiceFactory = Callable[[dict[str, Any]], Any]


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


def _load_calibration_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(
            f"Missing calibration state: {path}. "
            "Run pan-tilt safe center recovery/calibration before real face tracking."
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
        raise SystemExit("Default tracking readiness validation failed.")

    if bool(result.get("safe_to_execute_physical_motion", False)):
        raise SystemExit(
            "Refusing because default config reports safe_to_execute_physical_motion=true. "
            "Sprint 11B expects default runtime movement to remain OFF."
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


def _validate_loop_limits(
    *,
    steps: int,
    max_duration_seconds: float,
    interval_seconds: float,
    max_step_degrees: float,
    speed: int,
    acceleration: int,
) -> None:
    if int(steps) <= 0 or int(steps) > MAX_LOOP_STEPS:
        raise SystemExit(f"Refusing steps={steps}. Allowed range is 1..{MAX_LOOP_STEPS}.")

    if float(max_duration_seconds) <= 0.0 or float(max_duration_seconds) > MAX_LOOP_SECONDS:
        raise SystemExit(
            f"Refusing max duration {max_duration_seconds}. "
            f"Allowed range is >0..{MAX_LOOP_SECONDS} seconds."
        )

    if float(interval_seconds) < 0.05:
        raise SystemExit("Refusing interval below 0.05 seconds.")

    if float(max_step_degrees) <= 0.0 or float(max_step_degrees) > MAX_SINGLE_STEP_DEGREES:
        raise SystemExit(
            f"Refusing max step {max_step_degrees}. "
            f"Sprint 11B maximum is {MAX_SINGLE_STEP_DEGREES} degree."
        )

    if not (1 <= int(speed) <= MAX_SPEED):
        raise SystemExit(f"Refusing speed {speed}. Allowed range is 1..{MAX_SPEED}.")

    if not (1 <= int(acceleration) <= MAX_ACCELERATION):
        raise SystemExit(
            f"Refusing acceleration {acceleration}. Allowed range is 1..{MAX_ACCELERATION}."
        )


def _build_vision_config(
    *,
    settings: dict[str, Any],
    width: int,
    height: int,
    backend: str,
    fallback_backend: str,
    hflip: bool,
    vflip: bool,
) -> dict[str, Any]:
    config = copy.deepcopy(settings.get("vision", {}))
    config.update(
        {
            "enabled": True,
            "backend": str(backend),
            "fallback_backend": str(fallback_backend),
            "frame_width": int(width),
            "frame_height": int(height),
            "lazy_start": True,
            "continuous_capture_enabled": False,
            "hflip": bool(hflip),
            "vflip": bool(vflip),
            "face_detection_enabled": True,
            "face_detector_backend": "opencv_haar",
            "face_detector_roi_enabled": False,
            "people_detection_enabled": False,
            "object_detection_enabled": False,
            "behavior_interpretation_enabled": False,
            "scene_understanding_enabled": False,
        }
    )
    return config


def _build_pan_tilt_config(
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
) -> dict[str, Any]:
    config = copy.deepcopy(settings.get("pan_tilt", {}))
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
        }
    )
    return config


def _build_tracking_config(
    *,
    settings: dict[str, Any],
    status_path: Path,
    execute: bool,
    max_step_degrees: float,
    pan_gain_degrees: float,
    tilt_gain_degrees: float,
    dead_zone_x: float,
    dead_zone_y: float,
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
        "dead_zone_x": float(dead_zone_x),
        "dead_zone_y": float(dead_zone_y),
        "pan_gain_degrees": float(pan_gain_degrees),
        "tilt_gain_degrees": float(tilt_gain_degrees),
        "max_step_degrees": float(max_step_degrees),
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
        "max_allowed_pan_delta_degrees": float(max_step_degrees),
        "max_allowed_tilt_delta_degrees": float(max_step_degrees),
    }
    return config


def _target_summary(plan_payload: dict[str, Any]) -> dict[str, Any]:
    target = plan_payload.get("target")
    if not isinstance(target, dict):
        return {
            "has_target": False,
            "target_type": None,
            "confidence": 0.0,
            "center_x_norm": None,
            "center_y_norm": None,
        }

    return {
        "has_target": True,
        "target_type": target.get("target_type"),
        "confidence": target.get("confidence"),
        "center_x_norm": target.get("center_x_norm"),
        "center_y_norm": target.get("center_y_norm"),
        "box": target.get("box"),
    }


def _is_motion_required(adapter_payload: dict[str, Any]) -> bool:
    return str(adapter_payload.get("status", "")) not in {
        "no_pan_tilt_motion_required",
        "no_motion_required",
        "no_target",
    }


def _is_backend_executed(adapter_payload: dict[str, Any]) -> bool:
    return bool(adapter_payload.get("backend_command_executed", False))


def run_real_face_tracking_loop(
    *,
    settings_path: Path,
    state_path: Path,
    status_path: Path,
    width: int,
    height: int,
    backend: str,
    fallback_backend: str,
    hflip: bool,
    vflip: bool,
    steps: int,
    interval_seconds: float,
    max_duration_seconds: float,
    port: str | None,
    baudrate: int | None,
    max_step_degrees: float,
    pan_gain_degrees: float,
    tilt_gain_degrees: float,
    dead_zone_x: float,
    dead_zone_y: float,
    speed: int,
    acceleration: int,
    execute: bool,
    understand: bool,
    confirm_text: str,
    return_center: bool,
    camera_service_factory: ServiceFactory | None = None,
    pan_tilt_service_factory: ServiceFactory | None = None,
) -> dict[str, Any]:
    _validate_loop_limits(
        steps=steps,
        max_duration_seconds=max_duration_seconds,
        interval_seconds=interval_seconds,
        max_step_degrees=max_step_degrees,
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

    vision_config = _build_vision_config(
        settings=settings,
        width=width,
        height=height,
        backend=backend,
        fallback_backend=fallback_backend,
        hflip=hflip,
        vflip=vflip,
    )
    pan_tilt_config = _build_pan_tilt_config(
        settings=settings,
        state=state,
        state_path=state_path,
        port=port,
        baudrate=baudrate,
        max_step_degrees=max_step_degrees,
        speed=speed,
        acceleration=acceleration,
        execute=bool(execute),
    )
    tracking_config = _build_tracking_config(
        settings=settings,
        status_path=status_path,
        execute=bool(execute),
        max_step_degrees=max_step_degrees,
        pan_gain_degrees=pan_gain_degrees,
        tilt_gain_degrees=tilt_gain_degrees,
        dead_zone_x=dead_zone_x,
        dead_zone_y=dead_zone_y,
    )

    camera_factory = camera_service_factory or CameraService
    pan_tilt_factory = pan_tilt_service_factory or PanTiltService

    camera_service = camera_factory(vision_config)
    pan_tilt_service = pan_tilt_factory(pan_tilt_config)
    tracking_service = VisionTrackingService(
        vision_backend=camera_service,
        pan_tilt_backend=pan_tilt_service,
        config=tracking_config,
    )

    started_at = time.monotonic()
    step_payloads: list[dict[str, Any]] = []
    target_count = 0
    backend_command_count = 0
    no_motion_count = 0
    no_target_count = 0
    error_count = 0
    return_center_result: dict[str, Any] | None = None

    try:
        start_method = getattr(camera_service, "start", None)
        if callable(start_method):
            start_method()

        for step_index in range(1, int(steps) + 1):
            elapsed = time.monotonic() - started_at
            if elapsed > float(max_duration_seconds):
                break

            try:
                plan = tracking_service.plan_once(force_refresh=True)
                execution = tracking_service.latest_execution_result()
                adapter_result = tracking_service.latest_pan_tilt_adapter_result()

                plan_payload = _as_dict(plan)
                execution_payload = _as_dict(execution)
                adapter_payload = _as_dict(adapter_result)
                target = _target_summary(plan_payload)

                if bool(plan_payload.get("has_target", False)):
                    target_count += 1
                else:
                    no_target_count += 1

                if _is_backend_executed(adapter_payload):
                    backend_command_count += 1
                elif not _is_motion_required(adapter_payload):
                    no_motion_count += 1

                step_payload = {
                    "step": step_index,
                    "elapsed_ms": round((time.monotonic() - started_at) * 1000.0, 3),
                    "target_summary": target,
                    "plan": plan_payload,
                    "execution_result": execution_payload,
                    "pan_tilt_adapter_result": adapter_payload,
                }
                step_payloads.append(step_payload)

                print(
                    "STEP "
                    f"{step_index}/{steps} "
                    f"target={target['has_target']} "
                    f"reason={plan_payload.get('reason')} "
                    f"pan={plan_payload.get('pan_delta_degrees')} "
                    f"tilt={plan_payload.get('tilt_delta_degrees')} "
                    f"adapter={adapter_payload.get('status')} "
                    f"backend_executed={adapter_payload.get('backend_command_executed')}"
                )

            except Exception as error:
                error_count += 1
                step_payloads.append(
                    {
                        "step": step_index,
                        "elapsed_ms": round((time.monotonic() - started_at) * 1000.0, 3),
                        "error": f"{error.__class__.__name__}: {error}",
                    }
                )
                print(f"STEP {step_index}/{steps} error={error.__class__.__name__}: {error}")

            if step_index < int(steps):
                time.sleep(max(0.0, float(interval_seconds)))

        if bool(execute) and bool(return_center):
            center_method = getattr(pan_tilt_service, "center", None)
            if callable(center_method):
                return_center_result = _as_dict(center_method())

        camera_status = (
            camera_service.status()
            if callable(getattr(camera_service, "status", None))
            else {}
        )
        pan_tilt_status = (
            pan_tilt_service.status()
            if callable(getattr(pan_tilt_service, "status", None))
            else {}
        )
        tracking_status = tracking_service.status()

    finally:
        close_camera = getattr(camera_service, "close", None)
        if callable(close_camera):
            close_camera()

        close_pan_tilt = getattr(pan_tilt_service, "close", None)
        if callable(close_pan_tilt):
            close_pan_tilt()

    ok = target_count > 0 and error_count == 0
    if bool(execute):
        ok = ok and (backend_command_count > 0 or no_motion_count > 0)

    return {
        "ok": ok,
        "execute": bool(execute),
        "preview_only": not bool(execute),
        "settings_path": str(settings_path),
        "calibration_state_path": str(state_path),
        "status_path": str(status_path),
        "elapsed_ms": round((time.monotonic() - started_at) * 1000.0, 3),
        "steps_requested": int(steps),
        "steps_completed": len(step_payloads),
        "target_count": target_count,
        "no_target_count": no_target_count,
        "backend_command_count": backend_command_count,
        "no_motion_count": no_motion_count,
        "error_count": error_count,
        "return_center": bool(return_center),
        "return_center_result": return_center_result,
        "readiness": readiness,
        "camera_status": camera_status,
        "pan_tilt_status": pan_tilt_status,
        "vision_tracking_status": tracking_status,
        "steps": step_payloads,
    }


def print_summary(payload: dict[str, Any]) -> None:
    print()
    print("NEXA Vision Runtime — short real face tracking loop")
    print(f"execute={payload['execute']}")
    print(f"preview_only={payload['preview_only']}")
    print(f"steps_completed={payload['steps_completed']}/{payload['steps_requested']}")
    print(f"target_count={payload['target_count']}")
    print(f"backend_command_count={payload['backend_command_count']}")
    print(f"no_motion_count={payload['no_motion_count']}")
    print(f"no_target_count={payload['no_target_count']}")
    print(f"error_count={payload['error_count']}")
    print(f"elapsed_ms={payload['elapsed_ms']}")
    print(f"camera_backend={payload.get('camera_status', {}).get('backend')}")
    print(f"camera_error={payload.get('camera_status', {}).get('last_error')}")
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
            "Run a short gated real face tracking loop. "
            "Default mode is preview-only and never sends pan-tilt movement."
        )
    )
    parser.add_argument("--settings", default=str(DEFAULT_SETTINGS_PATH))
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--status-path", default=str(DEFAULT_STATUS_PATH))
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--backend", default="picamera2")
    parser.add_argument("--fallback-backend", default="opencv")
    parser.add_argument("--hflip", action="store_true")
    parser.add_argument("--vflip", action="store_true")
    parser.add_argument("--steps", type=int, default=12)
    parser.add_argument("--interval-seconds", type=float, default=0.35)
    parser.add_argument("--max-duration-seconds", type=float, default=20.0)
    parser.add_argument("--port", default=None)
    parser.add_argument("--baudrate", type=int, default=None)
    parser.add_argument("--max-step-degrees", type=float, default=1.0)
    parser.add_argument("--pan-gain-degrees", type=float, default=8.0)
    parser.add_argument("--tilt-gain-degrees", type=float, default=6.0)
    parser.add_argument("--dead-zone-x", type=float, default=0.03)
    parser.add_argument("--dead-zone-y", type=float, default=0.04)
    parser.add_argument("--speed", type=int, default=55)
    parser.add_argument("--acceleration", type=int, default=55)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-understand-this-moves-hardware", action="store_true")
    parser.add_argument("--confirm-text", default="")
    parser.add_argument("--return-center", action="store_true")
    args = parser.parse_args(argv)

    payload = run_real_face_tracking_loop(
        settings_path=Path(args.settings),
        state_path=Path(args.state),
        status_path=Path(args.status_path),
        width=int(args.width),
        height=int(args.height),
        backend=str(args.backend),
        fallback_backend=str(args.fallback_backend),
        hflip=bool(args.hflip),
        vflip=bool(args.vflip),
        steps=int(args.steps),
        interval_seconds=float(args.interval_seconds),
        max_duration_seconds=float(args.max_duration_seconds),
        port=args.port,
        baudrate=args.baudrate,
        max_step_degrees=float(args.max_step_degrees),
        pan_gain_degrees=float(args.pan_gain_degrees),
        tilt_gain_degrees=float(args.tilt_gain_degrees),
        dead_zone_x=float(args.dead_zone_x),
        dead_zone_y=float(args.dead_zone_y),
        speed=int(args.speed),
        acceleration=int(args.acceleration),
        execute=bool(args.execute),
        understand=bool(args.i_understand_this_moves_hardware),
        confirm_text=str(args.confirm_text),
        return_center=bool(args.return_center),
    )
    print_summary(payload)

    if not bool(payload.get("ok", False)):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
