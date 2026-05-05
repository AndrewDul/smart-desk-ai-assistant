#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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

CONFIRM_ENV_NAME = "CONFIRM_NEXA_TINY_PAN_TILT_SMOKE"
CONFIRM_VALUE = "RUN_TINY_PAN_TILT_SMOKE"

MAX_TINY_DELTA_DEGREES = 0.5
MAX_SPEED = 60
MAX_ACCELERATION = 60


def wire_axis_value(value: float) -> int | float:
    rounded = round(float(value), 3)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def compact_json_line(command: dict[str, Any]) -> str:
    return json.dumps(command, separators=(",", ":")) + "\n"


def clamp(value: float, lower: float, upper: float) -> float:
    return min(max(float(value), float(lower)), float(upper))


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
            "Run calibration before any hardware smoke movement."
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


def validate_readiness(settings_path: Path) -> dict[str, Any]:
    result = validate_settings(load_settings(settings_path))
    if not bool(result.get("ok", False)):
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
        raise SystemExit("Readiness validator failed. Refusing hardware smoke preparation.")
    return result


def validate_tiny_request(
    *,
    pan_delta: float,
    tilt_delta: float,
    speed: int,
    acceleration: int,
    settle: float,
) -> None:
    if abs(float(pan_delta)) > MAX_TINY_DELTA_DEGREES:
        raise SystemExit(
            f"Refusing pan delta {pan_delta}. Maximum tiny pan delta is "
            f"{MAX_TINY_DELTA_DEGREES} degree."
        )

    if abs(float(tilt_delta)) > MAX_TINY_DELTA_DEGREES:
        raise SystemExit(
            f"Refusing tilt delta {tilt_delta}. Maximum tiny tilt delta is "
            f"{MAX_TINY_DELTA_DEGREES} degree."
        )

    if abs(float(pan_delta)) == 0.0 and abs(float(tilt_delta)) == 0.0:
        raise SystemExit("Refusing zero movement smoke request.")

    if not (1 <= int(speed) <= MAX_SPEED):
        raise SystemExit(f"Refusing speed {speed}. Allowed range is 1..{MAX_SPEED}.")

    if not (1 <= int(acceleration) <= MAX_ACCELERATION):
        raise SystemExit(
            f"Refusing acceleration {acceleration}. Allowed range is 1..{MAX_ACCELERATION}."
        )

    if not (0.2 <= float(settle) <= 2.0):
        raise SystemExit("Refusing settle outside 0.2..2.0 seconds.")


def build_sequence(
    *,
    target_x: float,
    target_y: float,
    speed: int,
    acceleration: int,
    settle: float,
) -> list[tuple[str, dict[str, Any], float]]:
    center = move_command(0.0, 0.0, speed, acceleration)
    target = move_command(target_x, target_y, speed, acceleration)

    return [
        ("stop", {"T": 135}, 0.25),
        ("steady off", {"T": 137, "s": 0, "y": 0}, 0.25),
        ("pan-tilt mode", {"T": 4, "cmd": 2}, 0.35),
        ("torque on", {"T": 210, "cmd": 1}, 0.45),
        ("center", center, settle),
        ("tiny tracking target", target, settle),
        ("return center", center, settle),
        ("final stop", {"T": 135}, 0.25),
    ]


def target_within_marked_limits(*, state: dict[str, Any], target_x: float, target_y: float) -> bool:
    marked = state["marked_limits"]
    pan_left = float(marked["pan_left_x"])
    pan_right = float(marked["pan_right_x"])
    tilt_min = float(marked["tilt_min_y"])
    tilt_max = float(marked["tilt_max_y"])

    lower_pan = min(pan_left, pan_right)
    upper_pan = max(pan_left, pan_right)

    return lower_pan <= target_x <= upper_pan and tilt_min <= target_y <= tilt_max


def require_state_near_center_for_execute(*, state: dict[str, Any], execute: bool) -> None:
    if not execute:
        return

    current_x = float(state.get("x", 0.0))
    current_y = float(state.get("y", 0.0))

    if abs(current_x) <= MAX_TINY_DELTA_DEGREES and abs(current_y) <= MAX_TINY_DELTA_DEGREES:
        return

    raise SystemExit(
        "Refusing execute because calibration state is not near center. "
        f"Current state is X={current_x} Y={current_y}. "
        "Run a safe manual center step first, then re-run preview."
    )


def require_execute_confirmation(*, execute: bool, understand: bool, confirm_text: str) -> None:
    if not execute:
        return

    if not understand:
        raise SystemExit(
            "Refusing to move. Add --i-understand-this-moves-hardware for hardware smoke."
        )

    if confirm_text != CONFIRM_VALUE:
        raise SystemExit(
            f"Refusing to move. Add --confirm-text {CONFIRM_VALUE} for hardware smoke."
        )

    if os.environ.get(CONFIRM_ENV_NAME, "") != CONFIRM_VALUE:
        raise SystemExit(
            f"Refusing to move. Set {CONFIRM_ENV_NAME}={CONFIRM_VALUE} for hardware smoke."
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
        raise SystemExit(f"Missing serial dependency for hardware smoke: {error}") from error

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
    target_x: float,
    target_y: float,
    speed: int,
    acceleration: int,
    sequence: list[tuple[str, dict[str, Any], float]],
    execute: bool,
) -> None:
    print("NEXA Vision Runtime — tiny pan-tilt tracking smoke")
    print(f"settings={settings_path}")
    print(f"calibration_state={state_path}")
    print(f"port={port}")
    print(f"baudrate={baudrate}")
    print(f"target_x={target_x}")
    print(f"target_y={target_y}")
    print(f"speed={speed}")
    print(f"acceleration={acceleration}")
    print(f"execute={execute}")
    print()
    print("Sequence:")
    for index, (label, command, pause) in enumerate(sequence, start=1):
        print(
            f"{index:02d}. {label}: "
            f"{json.dumps(command, separators=(',', ':'))} pause={pause:.2f}s"
        )

    print()
    if execute:
        print("HARDWARE SMOKE: commands will be sent after all explicit confirmations.")
        print("Keep your hand near the pan-tilt power switch.")
        print("Turn power off immediately if cables pull or the screen is at risk.")
    else:
        print("PREVIEW ONLY: no serial port opened and no movement commands sent.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Manual tiny Waveshare pan-tilt smoke script for NEXA Vision Runtime. "
            "Default mode is preview only and never opens the serial port."
        )
    )
    parser.add_argument("--settings", default=str(DEFAULT_SETTINGS_PATH))
    parser.add_argument("--state", default=str(STATE_PATH))
    parser.add_argument("--port", default=None)
    parser.add_argument("--baudrate", type=int, default=None)
    parser.add_argument("--pan-delta", type=float, default=0.25)
    parser.add_argument("--tilt-delta", type=float, default=0.0)
    parser.add_argument("--speed", type=int, default=45)
    parser.add_argument("--acceleration", type=int, default=45)
    parser.add_argument("--settle", type=float, default=0.6)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--i-understand-this-moves-hardware", action="store_true")
    parser.add_argument("--confirm-text", default="")
    args = parser.parse_args(argv)

    settings_path = Path(args.settings)
    state_path = Path(args.state)

    validate_readiness(settings_path)
    validate_tiny_request(
        pan_delta=args.pan_delta,
        tilt_delta=args.tilt_delta,
        speed=args.speed,
        acceleration=args.acceleration,
        settle=args.settle,
    )
    require_execute_confirmation(
        execute=bool(args.execute),
        understand=bool(args.i_understand_this_moves_hardware),
        confirm_text=str(args.confirm_text),
    )

    state = load_calibration_state(state_path)
    port = str(args.port or state.get("port", "/dev/serial0"))
    baudrate = int(args.baudrate or state.get("baudrate", 115200))

    target_x = float(args.pan_delta)
    target_y = float(args.tilt_delta)

    if not target_within_marked_limits(state=state, target_x=target_x, target_y=target_y):
        raise SystemExit(
            f"Refusing target X={target_x} Y={target_y}. "
            "Target is outside marked calibration limits."
        )

    require_state_near_center_for_execute(state=state, execute=bool(args.execute))

    sequence = build_sequence(
        target_x=target_x,
        target_y=target_y,
        speed=int(args.speed),
        acceleration=int(args.acceleration),
        settle=float(args.settle),
    )

    print_preview(
        settings_path=settings_path,
        state_path=state_path,
        port=port,
        baudrate=baudrate,
        target_x=target_x,
        target_y=target_y,
        speed=int(args.speed),
        acceleration=int(args.acceleration),
        sequence=sequence,
        execute=bool(args.execute),
    )

    if not args.execute:
        return 0

    send_sequence(port=port, baudrate=baudrate, sequence=sequence)
    print("Done. Tiny pan-tilt smoke sequence completed and final stop was sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
