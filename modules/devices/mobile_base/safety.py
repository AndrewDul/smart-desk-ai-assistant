from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Mapping

DEFAULT_MOVEMENT_CONFIRM_ENV = "CONFIRM_NEXA_MOBILE_BASE_MOVE"
DEFAULT_MOVEMENT_CONFIRM_VALUE = "RUN"

class MobileBaseSafetyError(RuntimeError):
    pass

def is_zero_velocity(command: Mapping[str, object]) -> bool:
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
    movement_confirm_env: str = DEFAULT_MOVEMENT_CONFIRM_ENV
    movement_confirm_value: str = DEFAULT_MOVEMENT_CONFIRM_VALUE
    max_linear_speed_mps: float = 0.30
    max_angular_speed_rad_s: float = 0.90
    max_wheel_speed_mps: float = 0.35
    max_pwm: int = 180
    deadman_timeout_ms: int = 260

    def movement_gate_open(self) -> bool:
        return os.environ.get(self.movement_confirm_env) == self.movement_confirm_value

    def assert_command_allowed(self, command: Mapping[str, object]) -> None:
        if is_zero_velocity(command):
            return
        if not self.movement_enabled:
            raise MobileBaseSafetyError("Mobile base movement is disabled by safety policy.")
        if not self.movement_gate_open():
            raise MobileBaseSafetyError(f"Mobile base movement env gate is closed. Set {self.movement_confirm_env}={self.movement_confirm_value}.")

    def clamp_linear(self, value: float) -> float:
        limit = abs(float(self.max_linear_speed_mps)); return max(-limit, min(limit, float(value)))
    def clamp_angular(self, value: float) -> float:
        limit = abs(float(self.max_angular_speed_rad_s)); return max(-limit, min(limit, float(value)))
    def clamp_wheel(self, value: float) -> float:
        limit = abs(float(self.max_wheel_speed_mps)); return max(-limit, min(limit, float(value)))
    def clamp_pwm(self, value: int) -> int:
        limit = abs(int(self.max_pwm)); return max(-limit, min(limit, int(value)))
    def deadman_expired(self, *, last_motion_monotonic: float | None) -> bool:
        if last_motion_monotonic is None:
            return False
        return (time.monotonic() - float(last_motion_monotonic)) >= max(0.001, self.deadman_timeout_ms / 1000.0)
