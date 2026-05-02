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
    read_for(ser, 0.45)
    time.sleep(pause)


def safe_pose(
    *,
    x: float,
    y: float,
    pan_left: float,
    pan_right: float,
    tilt_min: float,
    tilt_max: float,
    speed: int,
    acceleration: int,
) -> dict[str, Any]:
    return move_command(
        clamp(x, pan_left, pan_right),
        clamp(y, tilt_min, tilt_max),
        speed,
        acceleration,
    )


def build_emotion_sequence(
    *,
    emotion: str,
    pan_left: float,
    pan_right: float,
    tilt_min: float,
    tilt_max: float,
    speed: int,
    acceleration: int,
) -> list[tuple[str, dict[str, Any], float]]:
    # Expressive ranges are intentionally much smaller than mechanical limits.
    pan_small = min(10.0, abs(pan_left) * 0.25, abs(pan_right) * 0.25)
    pan_medium = min(18.0, abs(pan_left) * 0.35, abs(pan_right) * 0.35)

    tilt_down_soft = max(tilt_min + 4.0, -12.0)
    tilt_down_strict = max(tilt_min + 5.0, -10.0)
    tilt_up_soft = min(tilt_max - 8.0, 22.0)
    tilt_up_high = min(tilt_max - 10.0, 32.0)

    center = safe_pose(
        x=0.0,
        y=0.0,
        pan_left=pan_left,
        pan_right=pan_right,
        tilt_min=tilt_min,
        tilt_max=tilt_max,
        speed=speed,
        acceleration=acceleration,
    )

    def pose(label: str, x: float, y: float, pause: float, *, local_speed: int | None = None) -> tuple[str, dict[str, Any], float]:
        return (
            label,
            safe_pose(
                x=x,
                y=y,
                pan_left=pan_left,
                pan_right=pan_right,
                tilt_min=tilt_min,
                tilt_max=tilt_max,
                speed=local_speed if local_speed is not None else speed,
                acceleration=acceleration,
            ),
            pause,
        )

    if emotion == "anger":
        return [
            pose("anger focus down", 0.0, tilt_down_strict, 0.55, local_speed=80),
            pose("anger snap right", pan_medium, tilt_down_strict, 0.28, local_speed=90),
            pose("anger snap left", -pan_medium, tilt_down_strict, 0.28, local_speed=90),
            pose("anger snap right small", pan_small, tilt_down_strict, 0.24, local_speed=90),
            pose("anger center hard stare", 0.0, tilt_down_strict, 0.7, local_speed=75),
            pose("anger release center", 0.0, 0.0, 0.8, local_speed=70),
        ]

    if emotion == "fear":
        return [
            pose("fear look up", 0.0, tilt_up_high, 0.45, local_speed=90),
            pose("fear tremble left", -pan_small, tilt_up_soft, 0.20, local_speed=90),
            pose("fear tremble right", pan_small, tilt_up_soft, 0.20, local_speed=90),
            pose("fear tremble left small", -pan_small * 0.55, tilt_up_high, 0.18, local_speed=90),
            pose("fear tremble right small", pan_small * 0.55, tilt_up_high, 0.18, local_speed=90),
            pose("fear freeze", 0.0, tilt_up_soft, 0.8, local_speed=75),
            pose("fear return center", 0.0, 0.0, 0.8, local_speed=70),
        ]

    if emotion == "joy":
        return [
            pose("joy lift", 0.0, min(tilt_max - 12.0, 18.0), 0.45, local_speed=80),
            pose("joy bounce down", 0.0, 6.0, 0.25, local_speed=85),
            pose("joy bounce up", 0.0, min(tilt_max - 12.0, 18.0), 0.25, local_speed=85),
            pose("joy look right", pan_small, 12.0, 0.25, local_speed=80),
            pose("joy look left", -pan_small, 12.0, 0.25, local_speed=80),
            pose("joy happy center", 0.0, 14.0, 0.45, local_speed=75),
            pose("joy return center", 0.0, 0.0, 0.8, local_speed=70),
        ]

    if emotion == "sadness":
        return [
            pose("sad slow drop", 0.0, tilt_down_soft, 1.0, local_speed=55),
            pose("sad slight left", -pan_small * 0.45, tilt_down_soft, 0.8, local_speed=50),
            pose("sad lower", -pan_small * 0.25, max(tilt_min + 3.0, tilt_down_soft - 3.0), 0.9, local_speed=50),
            pose("sad hold", 0.0, tilt_down_soft, 1.0, local_speed=45),
            pose("sad return center slow", 0.0, 0.0, 1.1, local_speed=55),
        ]

    raise SystemExit(f"Unknown emotion: {emotion}")


def build_sequence(
    *,
    emotions: list[str],
    pan_left: float,
    pan_right: float,
    tilt_min: float,
    tilt_max: float,
    speed: int,
    acceleration: int,
) -> list[tuple[str, dict[str, Any], float]]:
    sequence: list[tuple[str, dict[str, Any], float]] = [
        ("stop", {"T": 135}, 0.4),
        ("steady off", {"T": 137, "s": 0, "y": 0}, 0.4),
        ("pan-tilt mode", {"T": 4, "cmd": 2}, 0.5),
        ("torque on", {"T": 210, "cmd": 1}, 0.7),
        ("neutral center", move_command(0.0, 0.0, speed, acceleration), 1.0),
    ]

    for emotion in emotions:
        sequence.append((f"emotion start: {emotion}", move_command(0.0, 0.0, speed, acceleration), 0.8))
        sequence.extend(
            build_emotion_sequence(
                emotion=emotion,
                pan_left=pan_left,
                pan_right=pan_right,
                tilt_min=tilt_min,
                tilt_max=tilt_max,
                speed=speed,
                acceleration=acceleration,
            )
        )

    sequence.extend(
        [
            ("final center", move_command(0.0, 0.0, speed, acceleration), 1.0),
            ("final stop", {"T": 135}, 0.4),
        ]
    )
    return sequence


def main() -> int:
    parser = argparse.ArgumentParser(description="Waveshare pan-tilt emotion behavior smoke test.")
    parser.add_argument("--state", default=str(STATE_PATH))
    parser.add_argument("--port", default=None)
    parser.add_argument("--baudrate", type=int, default=None)
    parser.add_argument("--emotion", choices=["all", "anger", "fear", "joy", "sadness"], default="all")
    parser.add_argument("--speed", type=int, default=70)
    parser.add_argument("--acceleration", type=int, default=70)
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

    emotions = ["anger", "fear", "joy", "sadness"] if args.emotion == "all" else [args.emotion]

    sequence = build_sequence(
        emotions=emotions,
        pan_left=pan_left,
        pan_right=pan_right,
        tilt_min=tilt_min,
        tilt_max=tilt_max,
        speed=args.speed,
        acceleration=args.acceleration,
    )

    print("## Waveshare pan-tilt emotion behavior smoke test")
    print(f"port={port}")
    print(f"baudrate={baudrate}")
    print(f"emotions={','.join(emotions)}")
    print(f"pan_left={pan_left}")
    print(f"pan_right={pan_right}")
    print(f"tilt_min={tilt_min}")
    print(f"tilt_max={tilt_max}")
    print(f"speed={args.speed}")
    print(f"acceleration={args.acceleration}")
    print()
    print("Sequence:")
    for index, (label, command, pause) in enumerate(sequence, start=1):
        print(f"{index:02d}. {label}: {json.dumps(command, separators=(',', ':'))} pause={pause}")

    if args.dry_run:
        print()
        print("DRY RUN: no serial port opened and no movement commands sent.")
        return 0

    confirmation = os.environ.get("CONFIRM_PAN_TILT_EMOTION_TEST", "")
    if confirmation != "RUN_EMOTION_TEST":
        raise SystemExit(
            "Refusing to move. Set CONFIRM_PAN_TILT_EMOTION_TEST=RUN_EMOTION_TEST to run the hardware test."
        )

    print()
    print("HARDWARE RUN: emotion behaviors will move the pan-tilt.")
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
