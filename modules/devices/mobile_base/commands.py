from __future__ import annotations

import json
from typing import Any, Mapping

def _round(value: float) -> float:
    return round(float(value), 3)

def build_ros_velocity_command(*, linear_x_mps: float, angular_z_rad_s: float) -> dict[str, float | int]:
    return {"T": 13, "X": _round(linear_x_mps), "Z": _round(angular_z_rad_s)}

def build_wheel_velocity_command(*, left_mps: float, right_mps: float) -> dict[str, float | int]:
    return {"T": 1, "L": _round(left_mps), "R": _round(right_mps)}

def build_stop_command(*, command_profile: str = "ros") -> dict[str, float | int]:
    profile = str(command_profile or "ros").strip().lower()
    if profile == "wheel":
        return build_wheel_velocity_command(left_mps=0.0, right_mps=0.0)
    if profile == "pwm":
        return {"T": 11, "L": 0, "R": 0}
    return build_ros_velocity_command(linear_x_mps=0.0, angular_z_rad_s=0.0)

def serialize_json_line(command: Mapping[str, Any]) -> str:
    return json.dumps(dict(command), separators=(",", ":")) + "\n"
