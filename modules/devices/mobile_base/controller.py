from __future__ import annotations

import time
from typing import Protocol

from modules.devices.mobile_base.commands import (
    build_ros_velocity_command,
    build_stop_command,
    build_wheel_velocity_command,
    serialize_json_line,
)
from modules.devices.mobile_base.safety import MobileBaseSafetyPolicy, is_zero_velocity


class LineTransport(Protocol):
    def open(self) -> None: ...
    def write_line(self, line: str) -> None: ...
    def read_available_lines(self, *, duration_sec: float = 0.0) -> list[str]: ...
    def close(self) -> None: ...


class MobileBaseController:
    def __init__(
        self,
        *,
        transport: LineTransport,
        safety_policy: MobileBaseSafetyPolicy | None = None,
        command_profile: str = "ros",
        stop_repeat: int = 3,
        stop_interval_sec: float = 0.04,
        wheel_turn_speed_mps: float = 0.12,
    ) -> None:
        self.transport = transport
        self.safety_policy = safety_policy or MobileBaseSafetyPolicy()
        self.command_profile = str(command_profile or "ros").strip().lower()
        self.stop_repeat = int(stop_repeat)
        self.stop_interval_sec = max(0.0, float(stop_interval_sec))
        self.wheel_turn_speed_mps = abs(float(wheel_turn_speed_mps))
        self._opened = False
        self._last_motion_monotonic: float | None = None
        self.sent_commands: list[dict[str, int | float]] = []

    def open(self) -> None:
        if not self._opened:
            self.transport.open()
            self._opened = True

    def close(self) -> None:
        try:
            if self._opened:
                self.stop(repeat=max(1, self.stop_repeat), reason="controller_close")
        finally:
            self.transport.close()
            self._opened = False

    def __enter__(self) -> "MobileBaseController":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def _send(self, command: dict[str, int | float]) -> str:
        self.safety_policy.assert_command_allowed(command)
        self.open()
        line = serialize_json_line(command)
        self.transport.write_line(line)
        self.sent_commands.append(command)
        self._last_motion_monotonic = None if is_zero_velocity(command) else time.monotonic()
        return line.rstrip("\n")

    def stop(self, *, repeat: int | None = None, reason: str = "stop") -> list[str]:
        del reason
        count = max(1, int(self.stop_repeat if repeat is None else repeat))
        written: list[str] = []

        for index in range(count):
            written.append(self._send(build_stop_command(command_profile=self.command_profile)))
            if self.stop_interval_sec > 0.0 and index < count - 1:
                time.sleep(self.stop_interval_sec)

        return written

    def send_velocity(self, *, linear_x_mps: float, angular_z_rad_s: float) -> str:
        return self._send(
            build_ros_velocity_command(
                linear_x_mps=self.safety_policy.clamp_linear(linear_x_mps),
                angular_z_rad_s=self.safety_policy.clamp_angular(angular_z_rad_s),
            )
        )

    def drive_ros(self, *, linear_x_mps: float, angular_z_rad_s: float) -> str:
        return self.send_velocity(linear_x_mps=linear_x_mps, angular_z_rad_s=angular_z_rad_s)

    def drive_wheel(self, *, left_mps: float, right_mps: float) -> str:
        return self._send(
            build_wheel_velocity_command(
                left_mps=self.safety_policy.clamp_wheel(left_mps),
                right_mps=self.safety_policy.clamp_wheel(right_mps),
            )
        )

    def drive_pwm(self, *, left_pwm: int, right_pwm: int) -> str:
        return self._send(
            {
                "T": 11,
                "L": self.safety_policy.clamp_pwm(left_pwm),
                "R": self.safety_policy.clamp_pwm(right_pwm),
            }
        )

    def drive_forward(self, *, speed_mps: float | None = None) -> str:
        speed = self.safety_policy.default_linear_speed_mps if speed_mps is None else float(speed_mps)
        if self.command_profile == "wheel":
            return self.drive_wheel(left_mps=abs(speed), right_mps=abs(speed))
        return self.drive_ros(linear_x_mps=abs(speed), angular_z_rad_s=0.0)

    def drive_backward(self, *, speed_mps: float | None = None) -> str:
        speed = self.safety_policy.default_linear_speed_mps if speed_mps is None else float(speed_mps)
        if self.command_profile == "wheel":
            return self.drive_wheel(left_mps=-abs(speed), right_mps=-abs(speed))
        return self.drive_ros(linear_x_mps=-abs(speed), angular_z_rad_s=0.0)

    def rotate_left(self, *, speed_rad_s: float | None = None) -> str:
        speed = self.safety_policy.default_angular_speed_rad_s if speed_rad_s is None else float(speed_rad_s)
        if self.command_profile == "wheel":
            turn = self.wheel_turn_speed_mps
            return self.drive_wheel(left_mps=-turn, right_mps=turn)
        return self.drive_ros(linear_x_mps=0.0, angular_z_rad_s=abs(speed))

    def rotate_right(self, *, speed_rad_s: float | None = None) -> str:
        speed = self.safety_policy.default_angular_speed_rad_s if speed_rad_s is None else float(speed_rad_s)
        if self.command_profile == "wheel":
            turn = self.wheel_turn_speed_mps
            return self.drive_wheel(left_mps=turn, right_mps=-turn)
        return self.drive_ros(linear_x_mps=0.0, angular_z_rad_s=-abs(speed))

    def check_deadman(self, *, now_monotonic: float | None = None) -> bool:
        if self.safety_policy.deadman_expired(
            last_motion_monotonic=self._last_motion_monotonic,
            now_monotonic=now_monotonic,
        ):
            self.stop(repeat=1, reason="deadman_timeout")
            return True
        return False

    def read_available_lines(self, *, duration_sec: float = 0.0) -> list[str]:
        return self.transport.read_available_lines(duration_sec=duration_sec)
