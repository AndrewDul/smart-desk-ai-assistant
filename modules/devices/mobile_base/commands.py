from __future__ import annotations

import json
import math
from typing import Any, Mapping


class MobileBaseCommandError(ValueError):
    pass


def _finite_float(value: float | int, *, field_name: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise MobileBaseCommandError(f"{field_name} must be finite")
    return number


def _round(value: float | int) -> float:
    return round(float(value), 3)


def build_ros_velocity_command(*, linear_x_mps: float, angular_z_rad_s: float) -> dict[str, float | int]:
    return {
        "T": 13,
        "X": _round(_finite_float(linear_x_mps, field_name="linear_x_mps")),
        "Z": _round(_finite_float(angular_z_rad_s, field_name="angular_z_rad_s")),
    }


def build_wheel_velocity_command(*, left_mps: float, right_mps: float) -> dict[str, float | int]:
    return {
        "T": 1,
        "L": _round(_finite_float(left_mps, field_name="left_mps")),
        "R": _round(_finite_float(right_mps, field_name="right_mps")),
    }


def build_stop_command(*, command_profile: str = "ros") -> dict[str, float | int]:
    profile = str(command_profile or "ros").strip().lower()
    if profile == "wheel":
        return build_wheel_velocity_command(left_mps=0.0, right_mps=0.0)
    if profile == "pwm":
        return {"T": 11, "L": 0, "R": 0}
    return build_ros_velocity_command(linear_x_mps=0.0, angular_z_rad_s=0.0)


def build_stop_sequence(*, repeat: int = 3, command_profile: str = "ros") -> list[dict[str, float | int]]:
    count = int(repeat)
    if count < 1 or count > 10:
        raise MobileBaseCommandError("repeat must be between 1 and 10")
    return [build_stop_command(command_profile=command_profile) for _ in range(count)]


def serialize_json_line(command: Mapping[str, Any]) -> str:
    return json.dumps(dict(command), separators=(",", ":")) + "\n"


DriveCommand = dict[str, float | int]
MobileBaseCommand = dict[str, float | int]

build_forward_command = build_ros_velocity_command
build_backward_command = build_ros_velocity_command
build_rotate_left_command = build_ros_velocity_command
build_rotate_right_command = build_ros_velocity_command

def build_wheel_stop_command() -> dict[str, float | int]:
    return build_stop_command(command_profile="wheel")


build_wheel_forward_command = build_wheel_velocity_command
build_wheel_backward_command = build_wheel_velocity_command
build_wheel_rotate_left_command = build_wheel_velocity_command
build_wheel_rotate_right_command = build_wheel_velocity_command


def build_pwm_stop_command() -> dict[str, float | int]:
    return build_stop_command(command_profile="pwm")
