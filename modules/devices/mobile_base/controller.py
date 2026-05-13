from __future__ import annotations

import time
from typing import Protocol
from modules.devices.mobile_base.commands import build_ros_velocity_command, build_stop_command, build_wheel_velocity_command, serialize_json_line
from modules.devices.mobile_base.safety import MobileBaseSafetyPolicy, is_zero_velocity

class LineTransport(Protocol):
    def open(self) -> None: ...
    def write_line(self, line: str) -> None: ...
    def read_available_lines(self, *, duration_sec: float = 0.0) -> list[str]: ...
    def close(self) -> None: ...

class MobileBaseController:
    def __init__(self, *, transport: LineTransport, safety_policy: MobileBaseSafetyPolicy | None = None, command_profile: str = "wheel") -> None:
        self.transport = transport; self.safety_policy = safety_policy or MobileBaseSafetyPolicy(); self.command_profile = str(command_profile or "wheel").strip().lower(); self._opened = False; self._last_motion_monotonic = None; self.sent_commands = []
    def open(self) -> None:
        if not self._opened:
            self.transport.open(); self._opened = True
    def close(self) -> None:
        try:
            if self._opened: self.stop(repeat=3)
        finally:
            self.transport.close(); self._opened = False
    def __enter__(self): self.open(); return self
    def __exit__(self, exc_type, exc, tb): self.close()
    def _send(self, command: dict[str, int | float]) -> dict[str, int | float]:
        self.safety_policy.assert_command_allowed(command); self.open(); self.transport.write_line(serialize_json_line(command)); self.sent_commands.append(command); self._last_motion_monotonic = None if is_zero_velocity(command) else time.monotonic(); return command
    def stop(self, *, repeat: int = 1) -> None:
        for _ in range(max(1, int(repeat))): self._send(build_stop_command(command_profile=self.command_profile))
    def drive_ros(self, *, linear_x_mps: float, angular_z_rad_s: float): return self._send(build_ros_velocity_command(linear_x_mps=self.safety_policy.clamp_linear(linear_x_mps), angular_z_rad_s=self.safety_policy.clamp_angular(angular_z_rad_s)))
    def drive_wheel(self, *, left_mps: float, right_mps: float): return self._send(build_wheel_velocity_command(left_mps=self.safety_policy.clamp_wheel(left_mps), right_mps=self.safety_policy.clamp_wheel(right_mps)))
    def drive_pwm(self, *, left_pwm: int, right_pwm: int): return self._send({"T": 11, "L": self.safety_policy.clamp_pwm(left_pwm), "R": self.safety_policy.clamp_pwm(right_pwm)})
    def check_deadman(self) -> bool:
        if self.safety_policy.deadman_expired(last_motion_monotonic=self._last_motion_monotonic): self.stop(repeat=2); return True
        return False
