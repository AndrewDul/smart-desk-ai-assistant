from __future__ import annotations

import json
from typing import Any


def validate_tiny_motion_parameters(
    *,
    degrees: float,
    speed: int,
    acceleration: int,
) -> None:
    """Validate conservative smoke-test motion parameters."""

    if not 0.1 <= float(degrees) <= 10.0:
        raise ValueError("degrees must be between 0.1 and 10.0 for the tiny smoke test")
    if int(speed) <= 0:
        raise ValueError("speed must be greater than 0 because 0 is the fastest mode")
    if int(acceleration) <= 0:
        raise ValueError("acceleration must be greater than 0 because 0 is the fastest mode")


def compact_json_line(command: dict[str, Any]) -> str:
    """Serialize a Waveshare JSON command as one newline-terminated line."""

    return json.dumps(command, separators=(",", ":")) + "\n"


def gimbal_simple_command(
    *,
    x: float,
    y: float,
    speed: int = 80,
    acceleration: int = 80,
) -> dict[str, int | float]:
    """Build a basic Waveshare pan-tilt absolute position command."""

    if int(speed) <= 0:
        raise ValueError("speed must be greater than 0 because 0 is the fastest mode")
    if int(acceleration) <= 0:
        raise ValueError("acceleration must be greater than 0 because 0 is the fastest mode")

    return {
        "T": 133,
        "X": float(x),
        "Y": float(y),
        "SPD": int(speed),
        "ACC": int(acceleration),
    }


def build_tiny_smoke_sequence(
    *,
    degrees: float = 5.0,
    speed: int = 80,
    acceleration: int = 80,
) -> list[dict[str, Any]]:
    """Build right -> center -> left -> center -> up -> center -> down -> center."""

    validate_tiny_motion_parameters(
        degrees=degrees,
        speed=speed,
        acceleration=acceleration,
    )

    step = float(degrees)
    center = gimbal_simple_command(x=0.0, y=0.0, speed=speed, acceleration=acceleration)

    return [
        {"T": 135},
        {"T": 137, "s": 0, "y": 0},
        {"T": 4, "cmd": 2},
        {"T": 210, "cmd": 1},
        center,
        gimbal_simple_command(x=step, y=0.0, speed=speed, acceleration=acceleration),
        center,
        gimbal_simple_command(x=-step, y=0.0, speed=speed, acceleration=acceleration),
        center,
        gimbal_simple_command(x=0.0, y=step, speed=speed, acceleration=acceleration),
        center,
        gimbal_simple_command(x=0.0, y=-step, speed=speed, acceleration=acceleration),
        center,
        {"T": 135},
    ]


__all__ = [
    "build_tiny_smoke_sequence",
    "compact_json_line",
    "gimbal_simple_command",
    "validate_tiny_motion_parameters",
]
