#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import serial

STATE_PATH = Path("var/data/pan_tilt_limit_calibration.json")

DEFAULT_STATE = {
    "port": "/dev/serial0",
    "baudrate": 115200,
    "x": 0.0,
    "y": 0.0,
    "step_degrees": 3.0,
    "speed": 90,
    "acceleration": 90,
    "hard_x_min": -45.0,
    "hard_x_max": 45.0,
    "hard_y_min": -24.0,
    "hard_y_max": 24.0,
    "marked_limits": {},
}


def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        data = json.loads(STATE_PATH.read_text())
        merged = dict(DEFAULT_STATE)
        merged.update(data)
        merged["marked_limits"] = data.get("marked_limits", {})
        return merged
    return dict(DEFAULT_STATE)


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")


def compact_json_line(command: dict[str, Any]) -> str:
    return json.dumps(command, separators=(",", ":")) + "\n"


def wire_axis_value(value: float) -> int | float:
    rounded = round(float(value), 3)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def send_commands(port: str, baudrate: int, commands: list[dict[str, Any]], *, read_seconds: float = 0.35) -> None:
    with serial.Serial(port, baudrate, timeout=0.12) as ser:
        time.sleep(0.8)
        ser.reset_input_buffer()

        for command in commands:
            line = compact_json_line(command)
            print("SEND:", line.strip())
            ser.write(line.encode("utf-8"))
            ser.flush()

            deadline = time.monotonic() + read_seconds
            while time.monotonic() < deadline:
                raw = ser.readline()
                if raw:
                    print("RECV:", raw.decode("utf-8", errors="replace").strip())

            time.sleep(0.25)


def build_prepare_commands() -> list[dict[str, Any]]:
    return [
        {"T": 135},
        {"T": 137, "s": 0, "y": 0},
        {"T": 4, "cmd": 2},
        {"T": 210, "cmd": 1},
    ]


def move_to(state: dict[str, Any], x: float, y: float) -> None:
    if x < state["hard_x_min"] or x > state["hard_x_max"]:
        raise SystemExit(f"Refusing X={x}. Hard X range is {state['hard_x_min']}..{state['hard_x_max']}.")
    if y < state["hard_y_min"] or y > state["hard_y_max"]:
        raise SystemExit(f"Refusing Y={y}. Hard Y range is {state['hard_y_min']}..{state['hard_y_max']}.")

    commands = build_prepare_commands()
    commands.append(
        {
            "T": 133,
            "X": wire_axis_value(x),
            "Y": wire_axis_value(y),
            "SPD": int(state["speed"]),
            "ACC": int(state["acceleration"]),
        }
    )

    send_commands(str(state["port"]), int(state["baudrate"]), commands)
    state["x"] = round(float(x), 3)
    state["y"] = round(float(y), 3)
    save_state(state)

    print()
    print(f"Current commanded position: X={state['x']} Y={state['y']}")
    print(f"State saved to: {STATE_PATH}")


def print_state(state: dict[str, Any]) -> None:
    print(json.dumps(state, indent=2, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe Waveshare pan-tilt limit calibration helper.")
    parser.add_argument("action", choices=[
        "show",
        "init",
        "down",
        "up",
        "left",
        "right",
        "center",
        "stop",
        "unlock",
        "mark-tilt-min",
        "mark-tilt-max",
        "mark-pan-left",
        "mark-pan-right",
    ])
    parser.add_argument("--step", type=float, default=None)
    parser.add_argument("--port", default=None)
    parser.add_argument("--speed", type=int, default=None)
    parser.add_argument("--acceleration", type=int, default=None)
    args = parser.parse_args()

    state = load_state()

    if args.port is not None:
        state["port"] = args.port
    if args.speed is not None:
        state["speed"] = args.speed
    if args.acceleration is not None:
        state["acceleration"] = args.acceleration
    if args.step is not None:
        if not 0.5 <= args.step <= 3.0:
            raise SystemExit("Refusing step outside 0.5..3.0 degrees.")
        state["step_degrees"] = args.step

    step = float(state["step_degrees"])

    if args.action == "show":
        print_state(state)
        return 0

    if args.action == "init":
        print("Initializing safe calibration state and moving to center X=0 Y=0.")
        move_to(state, 0.0, 0.0)
        return 0

    if args.action == "center":
        move_to(state, 0.0, 0.0)
        return 0

    if args.action == "down":
        move_to(state, float(state["x"]), float(state["y"]) - step)
        return 0

    if args.action == "up":
        move_to(state, float(state["x"]), float(state["y"]) + step)
        return 0

    if args.action == "left":
        move_to(state, float(state["x"]) - step, float(state["y"]))
        return 0

    if args.action == "right":
        move_to(state, float(state["x"]) + step, float(state["y"]))
        return 0

    if args.action == "stop":
        send_commands(str(state["port"]), int(state["baudrate"]), [{"T": 135}], read_seconds=0.2)
        return 0

    if args.action == "unlock":
        send_commands(str(state["port"]), int(state["baudrate"]), [{"T": 210, "cmd": 0}], read_seconds=0.2)
        return 0

    if args.action == "mark-tilt-min":
        state["marked_limits"]["tilt_min_y"] = float(state["y"])
        save_state(state)
        print(f"Marked tilt_min_y = {state['y']}")
        print_state(state)
        return 0

    if args.action == "mark-tilt-max":
        state["marked_limits"]["tilt_max_y"] = float(state["y"])
        save_state(state)
        print(f"Marked tilt_max_y = {state['y']}")
        print_state(state)
        return 0

    if args.action == "mark-pan-left":
        state["marked_limits"]["pan_left_x"] = float(state["x"])
        save_state(state)
        print(f"Marked pan_left_x = {state['x']}")
        print_state(state)
        return 0

    if args.action == "mark-pan-right":
        state["marked_limits"]["pan_right_x"] = float(state["x"])
        save_state(state)
        print(f"Marked pan_right_x = {state['x']}")
        print_state(state)
        return 0

    raise SystemExit(f"Unhandled action: {args.action}")


if __name__ == "__main__":
    raise SystemExit(main())
