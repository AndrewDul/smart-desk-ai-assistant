#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from validate_vision_tracking_execution_readiness import load_settings, validate_settings


STATE_PATH = Path("var/data/pan_tilt_limit_calibration.json")
DEFAULT_SETTINGS_PATH = Path("config/settings.json")

CONFIRM_ENV_NAME = "CONFIRM_NEXA_PAN_TILT_CENTER_RECOVERY"
CONFIRM_VALUE = "RUN_CENTER_RECOVERY"

MAX_STEP_DEGREES = 2.0
MAX_SPEED = 45
MAX_ACCELERATION = 45
MAX_TOTAL_DELTA_DEGREES = 120.0


def wire_axis_value(value: float) -> int | float:
    rounded = round(float(value), 3)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def compact_json_line(command: dict[str, Any]) -> str:
    return json.dumps(command, separators=(",", ":")) + "\n"


def move_command(x: float, y: float, speed: int, acceleration: int) -> dict[str, Any]:
    return {
        "T": 133,
        "X": wire_axis_value(x),
        "Y": wire_axis_value(y),
        "SPD": int(speed),
        "ACC": int(acceleration),
    }


def load_calibration_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(
            f"Missing calibration state: {path}. "
            "Cannot prepare center recovery without calibration state."
        )

    data = json.loads(path.read_text())
    marked = data.get("marked_limits", {})
    required = [
        "pan_left_x",
        "pan_right_x",
        "tilt_min_y",
        "tilt_max_y",
    ]
    missing = [key for key in required if key not in marked]
    if missing:
        raise SystemExit("Missing marked calibration limits: " + ", ".join(missing))

    return data


def save_centered_state(path: Path, state: dict[str, Any]) -> None:
    updated = dict(state)
    updated["x"] = 0.0
    updated["y"] = 0.0
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_readiness(settings_path: Path) -> dict[str, Any]:
    result = validate_settings(load_settings(settings_path))
    if not bool(result.get("ok", False)):
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        raise SystemExit("Readiness validator failed. Refusing center recovery preparation.")
    return result


def validate_request(*, max_step: float, speed: int, acceleration: int, settle: float) -> None:
    if not (0.1 <= float(max_step) <= MAX_STEP_DEGREES):
        raise SystemExit(f"Refusing max step outside 0.1..{MAX_STEP_DEGREES} degrees.")

    if not (1 <= int(speed) <= MAX_SPEED):
        raise SystemExit(f"Refusing speed {speed}. Allowed range is 1..{MAX_SPEED}.")

    if not (1 <= int(acceleration) <= MAX_ACCELERATION):
        raise SystemExit(
            f"Refusing acceleration {acceleration}. Allowed range is 1..{MAX_ACCELERATION}."
        )

    if not (0.05 <= float(settle) <= 1.0):
        raise SystemExit("Refusing settle outside 0.05..1.0 seconds.")


def marked_limits(state: dict[str, Any]) -> dict[str, float]:
    marked = state["marked_limits"]
    pan_left = float(marked["pan_left_x"])
    pan_right = float(marked["pan_right_x"])
    tilt_min = float(marked["tilt_min_y"])
    tilt_max = float(marked["tilt_max_y"])

    return {
        "pan_min": min(pan_left, pan_right),
        "pan_max": max(pan_left, pan_right),
        "tilt_min": tilt_min,
        "tilt_max": tilt_max,
    }


def ensure_pose_inside_limits(*, state: dict[str, Any], x: float, y: float, label: str) -> None:
    limits = marked_limits(state)
    if not (limits["pan_min"] <= x <= limits["pan_max"]):
        raise SystemExit(
            f"Refusing {label}: X={x} outside pan limits "
            f"{limits['pan_min']}..{limits['pan_max']}."
        )

    if not (limits["tilt_min"] <= y <= limits["tilt_max"]):
        raise SystemExit(
            f"Refusing {label}: Y={y} outside tilt limits "
            f"{limits['tilt_min']}..{limits['tilt_max']}."
        )


def build_center_waypoints(*, current_x: float, current_y: float, max_step: float) -> list[tuple[float, float]]:
    total_delta = math.hypot(float(current_x), float(current_y))
    if total_delta == 0.0:
        return [(0.0, 0.0)]

    if total_delta > MAX_TOTAL_DELTA_DEGREES:
        raise SystemExit(
            f"Refusing center recovery total delta {total_delta:.3f}. "
            f"Maximum allowed total delta is {MAX_TOTAL_DELTA_DEGREES} degrees."
        )

    steps = max(1, int(math.ceil(total_delta / float(max_step))))
    waypoints: list[tuple[float, float]] = []

    for index in range(1, steps + 1):
        ratio = index / steps
        x = float(current_x) * (1.0 - ratio)
        y = float(current_y) * (1.0 - ratio)
        waypoints.append((round(x, 3), round(y, 3)))

    if waypoints[-1] != (0.0, 0.0):
        waypoints[-1] = (0.0, 0.0)

    return waypoints


def build_sequence(
    *,
    current_x: float,
    current_y: float,
    max_step: float,
    speed: int,
    acceleration: int,
    settle: float,
) -> list[tuple[str, dict[str, Any], float]]:
    sequence: list[tuple[str, dict[str, Any], float]] = [
        ("stop", {"T": 135}, 0.25),
        ("steady off", {"T": 137, "s": 0, "y": 0}, 0.25),
        ("pan-tilt mode", {"T": 4, "cmd": 2}, 0.35),
        ("torque on", {"T": 210, "cmd": 1}, 0.45),
    ]

    waypoints = build_center_waypoints(
        current_x=current_x,
        current_y=current_y,
        max_step=max_step,
    )

    for index, (x, y) in enumerate(waypoints, start=1):
        sequence.append(
            (
                f"center recovery step {index:03d}/{len(waypoints):03d}",
                move_command(x, y, speed, acceleration),
                settle,
            )
        )

    sequence.append(("final stop", {"T": 135}, 0.25))
    return sequence


def require_execute_confirmation(
    *,
    execute: bool,
    understand: bool,
    physical_position_confirmed: bool,
    area_clear: bool,
    confirm_text: str,
) -> None:
    if not execute:
        return

    if not understand:
        raise SystemExit(
            "Refusing to move. Add --i-understand-this-moves-hardware for center recovery."
        )

    if not physical_position_confirmed:
        raise SystemExit(
            "Refusing to move. Add --i-confirm-physical-position-matches-state after "
            "visually confirming the pan-tilt physical position matches the saved state."
        )

    if not area_clear:
        raise SystemExit(
            "Refusing to move. Add --i-confirm-area-clear after confirming cables, "
            "screen, and surroundings are clear."
        )

    if confirm_text != CONFIRM_VALUE:
        raise SystemExit(
            f"Refusing to move. Add --confirm-text {CONFIRM_VALUE} for center recovery."
        )

    if os.environ.get(CONFIRM_ENV_NAME, "") != CONFIRM_VALUE:
        raise SystemExit(
            f"Refusing to move. Set {CONFIRM_ENV_NAME}={CONFIRM_VALUE} for center recovery."
        )


def send_sequence(
    *,
    port: str,
    baudrate: int,
    sequence: list[tuple[str, dict[str, Any], float]],
) -> None:
    try:
        import serial
    except Exception as error:
        raise SystemExit(f"Missing serial dependency for hardware center recovery: {error}") from error

    with serial.Serial(port, baudrate, timeout=0.12) as ser:
        time.sleep(0.8)
        ser.reset_input_buffer()

        for label, command, pause in sequence:
            line = compact_json_line(command)
            print(f"SEND {label}: {line.strip()}")
            ser.write(line.encode("utf-8"))
            ser.flush()

            deadline = time.monotonic() + 0.25
            while time.monotonic() < deadline:
                raw = ser.readline()
                if raw:
                    print("RECV:", raw.decode("utf-8", errors="replace").strip())

            time.sleep(pause)


def print_preview(
    *,
    settings_path: Path,
    state_path: Path,
    port: str,
    baudrate: int,
    current_x: float,
    current_y: float,
    max_step: float,
    speed: int,
    acceleration: int,
    sequence: list[tuple[str, dict[str, Any], float]],
    execute: bool,
) -> None:
    print("NEXA Vision Runtime — safe pan-tilt center recovery")
    print(f"settings={settings_path}")
    print(f"calibration_state={state_path}")
    print(f"port={port}")
    print(f"baudrate={baudrate}")
    print(f"current_x={current_x}")
    print(f"current_y={current_y}")
    print("target_x=0.0")
    print("target_y=0.0")
    print(f"max_step={max_step}")
    print(f"speed={speed}")
    print(f"acceleration={acceleration}")
    print(f"execute={execute}")
    print()
    print("Sequence:")
    for index, (label, command, pause) in enumerate(sequence, start=1):
        print(
            f"{index:03d}. {label}: "
            f"{json.dumps(command, separators=(',', ':'))} pause={pause:.2f}s"
        )

    print()
    if execute:
        print("HARDWARE CENTER RECOVERY: commands will be sent after all confirmations.")
        print("Keep your hand near the pan-tilt power switch.")
        print("Turn power off immediately if cables pull or the screen is at risk.")
    else:
        print("PREVIEW ONLY: no serial port opened and no movement commands sent.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Manual safe Waveshare pan-tilt center recovery script for NEXA Vision Runtime. "
            "Default mode is preview only and never opens the serial port."
        )
    )
    parser.add_argument("--settings", default=str(DEFAULT_SETTINGS_PATH))
    parser.add_argument("--state", default=str(STATE_PATH))
    parser.add_argument("--port", default=None)
    parser.add_argument("--baudrate", type=int, default=None)
    parser.add_argument("--max-step", type=float, default=2.0)
    parser.add_argument("--speed", type=int, default=35)
    parser.add_argument("--acceleration", type=int, default=35)
    parser.add_argument("--settle", type=float, default=0.15)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-understand-this-moves-hardware", action="store_true")
    parser.add_argument("--i-confirm-physical-position-matches-state", action="store_true")
    parser.add_argument("--i-confirm-area-clear", action="store_true")
    parser.add_argument("--confirm-text", default="")
    args = parser.parse_args(argv)

    settings_path = Path(args.settings)
    state_path = Path(args.state)

    validate_readiness(settings_path)
    validate_request(
        max_step=args.max_step,
        speed=args.speed,
        acceleration=args.acceleration,
        settle=args.settle,
    )
    require_execute_confirmation(
        execute=bool(args.execute),
        understand=bool(args.i_understand_this_moves_hardware),
        physical_position_confirmed=bool(args.i_confirm_physical_position_matches_state),
        area_clear=bool(args.i_confirm_area_clear),
        confirm_text=str(args.confirm_text),
    )

    state = load_calibration_state(state_path)
    current_x = float(state.get("x", 0.0))
    current_y = float(state.get("y", 0.0))

    ensure_pose_inside_limits(state=state, x=current_x, y=current_y, label="current pose")
    ensure_pose_inside_limits(state=state, x=0.0, y=0.0, label="center pose")

    port = str(args.port or state.get("port", "/dev/serial0"))
    baudrate = int(args.baudrate or state.get("baudrate", 115200))

    sequence = build_sequence(
        current_x=current_x,
        current_y=current_y,
        max_step=float(args.max_step),
        speed=int(args.speed),
        acceleration=int(args.acceleration),
        settle=float(args.settle),
    )

    print_preview(
        settings_path=settings_path,
        state_path=state_path,
        port=port,
        baudrate=baudrate,
        current_x=current_x,
        current_y=current_y,
        max_step=float(args.max_step),
        speed=int(args.speed),
        acceleration=int(args.acceleration),
        sequence=sequence,
        execute=bool(args.execute),
    )

    if not args.execute:
        return 0

    send_sequence(port=port, baudrate=baudrate, sequence=sequence)
    save_centered_state(state_path, state)
    print(f"Done. Center recovery completed. Updated state saved to: {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
