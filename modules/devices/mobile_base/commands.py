from __future__ import annotations

import json
import math
from typing import Any


ROS_VELOCITY_COMMAND_TYPE = 13


class MobileBaseCommandError(ValueError):
    """Raised when a mobile base command cannot be built safely."""


def _safe_float(value: float, *, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise MobileBaseCommandError(f"{field_name} must be a finite number")
    return number


def build_ros_velocity_command(
    *,
    linear_x_mps: float,
    angular_z_rad_s: float,
) -> dict[str, int | float]:
    """
    Build a Waveshare ROS-style chassis velocity command.

    The command is intentionally tiny and explicit because the first hardware
    sprint only needs a safe STOP command. Movement commands must be added later
    behind a dedicated safety policy and an explicit hardware gate.
    """

    return {
        "T": ROS_VELOCITY_COMMAND_TYPE,
        "X": round(_safe_float(linear_x_mps, field_name="linear_x_mps"), 4),
        "Z": round(_safe_float(angular_z_rad_s, field_name="angular_z_rad_s"), 4),
    }


def build_stop_command() -> dict[str, int | float]:
    """Build a zero-velocity chassis command used as STOP."""

    return build_ros_velocity_command(linear_x_mps=0.0, angular_z_rad_s=0.0)


def build_stop_sequence(*, repeat: int = 3) -> list[dict[str, int | float]]:
    """
    Build a repeated STOP sequence.

    Repeating STOP makes the smoke test safer on a noisy serial link without
    introducing any movement command.
    """

    if int(repeat) < 1:
        raise MobileBaseCommandError("repeat must be at least 1")
    if int(repeat) > 10:
        raise MobileBaseCommandError("repeat must not be greater than 10")
    return [build_stop_command() for _ in range(int(repeat))]


def serialize_json_line(command: dict[str, Any]) -> str:
    """Serialize a command as compact JSON with a newline terminator."""

    if not isinstance(command, dict):
        raise MobileBaseCommandError("command must be a dictionary")
    if "T" not in command:
        raise MobileBaseCommandError("command must contain a T command type")
    return json.dumps(command, separators=(",", ":")) + "\n"


__all__ = [
    "MobileBaseCommandError",
    "ROS_VELOCITY_COMMAND_TYPE",
    "build_ros_velocity_command",
    "build_stop_command",
    "build_stop_sequence",
    "serialize_json_line",
]
