from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from typing import Mapping

DEFAULT_MOVEMENT_CONFIRM_ENV = "CONFIRM_NEXA_MOBILE_BASE_MOVE"
DEFAULT_MOVEMENT_CONFIRM_VALUE = "RUN"


class MobileBaseSafetyError(RuntimeError):
    pass


def is_zero_velocity(
    command: Mapping[str, object] | None = None,
    *,
    linear_x_mps: float | None = None,
    angular_z_rad_s: float | None = None,
) -> bool:
    if command is None:
        return abs(float(linear_x_mps or 0.0)) < 1e-9 and abs(float(angular_z_rad_s or 0.0)) < 1e-9

    command_type = int(command.get("T", -1) or -1)
    if command_type == 13:
        return float(command.get("X", 0.0) or 0.0) == 0.0 and float(command.get("Z", 0.0) or 0.0) == 0.0
    if command_type == 1:
        return float(command.get("L", 0.0) or 0.0) == 0.0 and float(command.get("R", 0.0) or 0.0) == 0.0
    if command_type == 11:
        return int(command.get("L", 0) or 0) == 0 and int(command.get("R", 0) or 0) == 0
    return False


@dataclass(slots=True)
class MobileBaseSafetyPolicy:
    movement_enabled: bool = False
    require_movement_confirm_env: bool = True
    movement_confirm_env: str = DEFAULT_MOVEMENT_CONFIRM_ENV
    movement_confirm_value: str = DEFAULT_MOVEMENT_CONFIRM_VALUE
    default_linear_speed_mps: float = 0.04
    default_angular_speed_rad_s: float = 0.18
    max_linear_speed_mps: float = 0.30
    max_angular_speed_rad_s: float = 0.90
    max_wheel_speed_mps: float = 0.20
    max_pwm: int = 180
    max_command_duration_ms: int = 350
    deadman_timeout_ms: int = 260

    def movement_gate_open(self) -> bool:
        return os.environ.get(self.movement_confirm_env) == self.movement_confirm_value

    def assert_stop_is_allowed(self) -> None:
        return None

    def assert_movement_is_allowed(self) -> None:
        if not self.movement_enabled:
            raise MobileBaseSafetyError("Mobile base movement is disabled by safety policy.")
        if self.require_movement_confirm_env and not self.movement_gate_open():
            raise MobileBaseSafetyError(
                f"Mobile base movement env gate is closed. Set {self.movement_confirm_env}={self.movement_confirm_value}."
            )

    def assert_command_allowed(self, command: Mapping[str, object]) -> None:
        if is_zero_velocity(command):
            self.assert_stop_is_allowed()
            return
        self.assert_movement_is_allowed()

    def clamp_linear(self, value: float) -> float:
        return _clamp(float(value), -abs(float(self.max_linear_speed_mps)), abs(float(self.max_linear_speed_mps)), "linear_x_mps")

    def clamp_angular(self, value: float) -> float:
        return _clamp(float(value), -abs(float(self.max_angular_speed_rad_s)), abs(float(self.max_angular_speed_rad_s)), "angular_z_rad_s")

    def clamp_wheel(self, value: float) -> float:
        return _clamp(float(value), -abs(float(self.max_wheel_speed_mps)), abs(float(self.max_wheel_speed_mps)), "wheel_mps")

    def clamp_pwm(self, value: int) -> int:
        number = int(value)
        limit = abs(int(self.max_pwm))
        return max(-limit, min(limit, number))

    def clamp_duration_ms(self, value: int | float) -> int:
        duration = int(value)
        if duration < 0:
            raise MobileBaseSafetyError("duration_ms must not be negative")
        return min(duration, int(self.max_command_duration_ms))

    def validate_velocity_request(self, *, linear_x_mps: float, angular_z_rad_s: float) -> tuple[float, float]:
        linear = self.clamp_linear(linear_x_mps)
        angular = self.clamp_angular(angular_z_rad_s)

        if is_zero_velocity(linear_x_mps=linear, angular_z_rad_s=angular):
            self.assert_stop_is_allowed()
            return 0.0, 0.0

        self.assert_movement_is_allowed()
        return linear, angular

    def deadman_expired(self, *, last_motion_monotonic: float | None, now_monotonic: float | None = None) -> bool:
        if last_motion_monotonic is None:
            return False
        now = time.monotonic() if now_monotonic is None else float(now_monotonic)
        return (now - float(last_motion_monotonic)) >= max(0.001, self.deadman_timeout_ms / 1000.0)


def _clamp(value: float, lower: float, upper: float, field_name: str) -> float:
    if not math.isfinite(value):
        raise MobileBaseSafetyError(f"{field_name} must be finite")
    return max(lower, min(upper, value))
