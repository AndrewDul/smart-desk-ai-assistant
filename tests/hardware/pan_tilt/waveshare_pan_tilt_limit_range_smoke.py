#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

import serial

STATE_PATH = Path("var/data/pan_tilt_limit_calibration.json")


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing calibration file: {path}")

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
        raise SystemExit("Missing marked limits: " + ", ".join(missing))

    return data


def wire_axis_value(value: float) -> int | float:
    rounded = round(float(value), 3)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def command_line(command: dict[str, Any]) -> str:
    return json.dumps(command, separators=(",", ":")) + "\n"


def read_for(ser: serial.Serial, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        raw = ser.readline()
        if raw:
            print("RECV:", raw.decode("utf-8", errors="replace").strip())


def send_command(ser: serial.Serial, label: str, command: dict[str, Any], pause: float) -> None:
    line = command_line(command)
    print(f"SEND {label}:", line.strip())
    ser.write(line.encode("utf-8"))
    ser.flush()
    read_for(ser, 0.8)
    time.sleep(pause)


def move_command(x: float, y: float, speed: int, acceleration: int) -> dict[str, Any]:
    return {
        "T": 133,
        "X": wire_axis_value(x),
        "Y": wire_axis_value(y),
        "SPD": int(speed),
        "ACC": int(acceleration),
    }


def build_sequence(
    *,
    pan_left: float,
    pan_right: float,
    tilt_min: float,
    tilt_max: float,
    speed: int,
    acceleration: int,
    settle: float,
) -> list[tuple[str, dict[str, Any], float]]:
    center = move_command(0.0, 0.0, speed, acceleration)

    return [
        ("stop", {"T": 135}, 0.4),
        ("steady off", {"T": 137, "s": 0, "y": 0}, 0.4),
        ("pan-tilt mode", {"T": 4, "cmd": 2}, 0.5),
        ("torque on", {"T": 210, "cmd": 1}, 0.7),

        ("center", center, settle),

        ("right limit", move_command(pan_right, 0.0, speed, acceleration), settle),
        ("center", center, settle),

        ("left limit", move_command(pan_left, 0.0, speed, acceleration), settle),
        ("center", center, settle),

        ("up limit", move_command(0.0, tilt_max, speed, acceleration), settle),
        ("center", center, settle),

        ("down limit", move_command(0.0, tilt_min, speed, acceleration), settle),
        ("center", center, settle),

        ("right up diagonal", move_command(pan_right, tilt_max, speed, acceleration), settle),
        ("center", center, settle),

        ("right down diagonal", move_command(pan_right, tilt_min, speed, acceleration), settle),
        ("center", center, settle),

        ("left up diagonal", move_command(pan_left, tilt_max, speed, acceleration), settle),
        ("center", center, settle),

        ("left down diagonal", move_command(pan_left, tilt_min, speed, acceleration), settle),
        ("center", center, settle),

        ("final stop", {"T": 135}, 0.4),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Waveshare pan-tilt calibrated limit range smoke test.")
    parser.add_argument("--state", default=str(STATE_PATH))
    parser.add_argument("--port", default=None)
    parser.add_argument("--baudrate", type=int, default=None)
    parser.add_argument("--speed", type=int, default=70)
    parser.add_argument("--acceleration", type=int, default=70)
    parser.add_argument("--settle", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    state = load_state(Path(args.state))
    marked = state["marked_limits"]

    port = args.port or state.get("port", "/dev/serial0")
    baudrate = int(args.baudrate or state.get("baudrate", 115200))

    pan_left = float(marked["pan_left_x"])
    pan_right = float(marked["pan_right_x"])
    tilt_min = float(marked["tilt_min_y"])
    tilt_max = float(marked["tilt_max_y"])

    sequence = build_sequence(
        pan_left=pan_left,
        pan_right=pan_right,
        tilt_min=tilt_min,
        tilt_max=tilt_max,
        speed=args.speed,
        acceleration=args.acceleration,
        settle=args.settle,
    )

    print("## Waveshare pan-tilt calibrated limit range smoke test")
    print(f"port={port}")
    print(f"baudrate={baudrate}")
    print(f"pan_left={pan_left}")
    print(f"pan_right={pan_right}")
    print(f"tilt_min={tilt_min}")
    print(f"tilt_max={tilt_max}")
    print(f"speed={args.speed}")
    print(f"acceleration={args.acceleration}")
    print()
    print("Sequence:")
    for index, (label, command, _) in enumerate(sequence, start=1):
        print(f"{index:02d}. {label}: {json.dumps(command, separators=(',', ':'))}")

    if args.dry_run:
        print()
        print("DRY RUN: no serial port opened and no movement commands sent.")
        return 0

    confirmation = os.environ.get("CONFIRM_PAN_TILT_LIMIT_TEST", "")
    if confirmation != "RUN_LIMIT_TEST":
        raise SystemExit(
            "Refusing to move. Set CONFIRM_PAN_TILT_LIMIT_TEST=RUN_LIMIT_TEST to run the hardware test."
        )

    print()
    print("HARDWARE RUN: calibrated limits will be tested.")
    print("Keep your hand near the pan-tilt power switch.")
    print("Turn power off immediately if cables pull or the screen is at risk.")
    print()

    with serial.Serial(port, baudrate, timeout=0.15) as ser:
        time.sleep(1.0)
        ser.reset_input_buffer()

        for label, command, pause in sequence:
            send_command(ser, label, command, pause)

    print("Done. Final command was stop after returning to center.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
