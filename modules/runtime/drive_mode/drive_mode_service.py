from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from modules.devices.mobile_base.controller import MobileBaseController
from modules.devices.mobile_base.safety import MobileBaseSafetyError
from modules.runtime.drive_mode.keyboard_mapping import (
    DriveModeAction,
    action_from_active_keys,
    action_from_key_event,
)


@dataclass(frozen=True, slots=True)
class DriveModeStatus:
    ok: bool
    action: DriveModeAction
    event: str
    command: str | None = None
    stopped: bool = False
    exit_requested: bool = False
    deadman_stop: bool = False
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action.value,
            "event": self.event,
            "command": self.command,
            "stopped": self.stopped,
            "exit_requested": self.exit_requested,
            "deadman_stop": self.deadman_stop,
            "error": self.error,
        }


class DriveModeService:
    def __init__(
        self,
        *,
        controller: MobileBaseController,
        linear_speed_mps: float | None = None,
        angular_speed_rad_s: float | None = None,
        wheel_turn_speed_mps: float = 0.12,
        command_profile: str | None = None,
        pwm_drive: int = 135,
        pwm_turn: int = 150,
    ) -> None:
        self.controller = controller
        policy = getattr(controller, 'safety_policy', None)
        self.linear_speed_mps = float(linear_speed_mps if linear_speed_mps is not None else getattr(policy, 'default_linear_speed_mps', 0.04))
        self.angular_speed_rad_s = float(angular_speed_rad_s if angular_speed_rad_s is not None else getattr(policy, 'default_angular_speed_rad_s', 0.18))
        self.wheel_turn_speed_mps = float(wheel_turn_speed_mps)
        self.command_profile = str(command_profile or controller.command_profile or "ros").strip().lower()
        self.pwm_drive = int(pwm_drive)
        self.pwm_turn = int(pwm_turn)
        self.exit_requested = False
        self.active_action: DriveModeAction | None = None

    def handle_keyboard_event(self, *, event: str, key: str) -> DriveModeStatus:
        return self.process_key_event(key=key, event=event)

    def process_key_event(self, *, key: str, event: str) -> DriveModeStatus:
        action = _coerce_action(action_from_key_event(key))
        normalized_event = str(event or "down").strip().lower()

        if normalized_event == "up" and action not in {DriveModeAction.EXIT, DriveModeAction.EMERGENCY_STOP}:
            return self.stop(event="up", action=action)

        return self.process_action(action=action, event=normalized_event)

    def handle_pressed_keys(self, *, keys: list[str] | tuple[str, ...]) -> DriveModeStatus:
        return self.process_active_keys(keys=list(keys), event="state")

    def process_active_keys(self, *, keys: list[str], event: str = "state") -> DriveModeStatus:
        return self.process_action(action=_coerce_action(action_from_active_keys(keys)), event=event)

    def process_action(self, *, action: str | DriveModeAction, event: str = "state") -> DriveModeStatus:
        drive_action = _coerce_action(action)

        if drive_action is DriveModeAction.UNKNOWN:
            return DriveModeStatus(False, drive_action, event, error="unknown_key")

        if drive_action is DriveModeAction.STOP:
            return self.stop(event=event, action=drive_action)

        if drive_action is DriveModeAction.EMERGENCY_STOP:
            return self.stop(event=event, action=drive_action)

        if drive_action is DriveModeAction.EXIT:
            self.exit_requested = True
            stopped = self.stop(event=event, action=drive_action)
            return DriveModeStatus(
                True,
                DriveModeAction.EXIT,
                event,
                stopped=True,
                exit_requested=True,
                error=stopped.error,
            )

        try:
            command = self._send_motion(drive_action)
        except MobileBaseSafetyError as error:
            self.active_action = None
            try:
                self.controller.stop(repeat=1, reason="drive_mode_motion_error")
            except Exception:
                pass
            return DriveModeStatus(False, drive_action, event, stopped=True, error=str(error))

        self.active_action = drive_action
        return DriveModeStatus(True, drive_action, event, command=command)

    def stop(
        self,
        *,
        event: str = "state",
        action: str | DriveModeAction = DriveModeAction.STOP,
    ) -> DriveModeStatus:
        drive_action = _coerce_action(action)
        self.active_action = None
        self.controller.stop(repeat=1, reason=f"drive_mode_{drive_action.value}")
        return DriveModeStatus(True, drive_action, event, stopped=True)

    def stop_all(self, *, reason: str = "drive_mode_stop_all") -> DriveModeStatus:
        del reason
        return self.stop(event="stop_all", action=DriveModeAction.EMERGENCY_STOP)

    def check_deadman(self, *, now_monotonic: float | None = None) -> DriveModeStatus | None:
        if self.controller.check_deadman(now_monotonic=now_monotonic):
            previous = self.active_action or DriveModeAction.EMERGENCY_STOP
            self.active_action = None
            return DriveModeStatus(True, previous, "deadman", stopped=True, deadman_stop=True)
        return None

    def _send_motion(self, action: DriveModeAction) -> str:
        if self.command_profile == "wheel":
            return self._send_wheel(action)
        return self._send_ros(action)

    def _send_ros(self, action: DriveModeAction) -> str:
        mapping = {
            DriveModeAction.FORWARD: (self.linear_speed_mps, 0.0),
            DriveModeAction.BACKWARD: (-self.linear_speed_mps, 0.0),
            DriveModeAction.ROTATE_LEFT: (0.0, self.angular_speed_rad_s),
            DriveModeAction.ROTATE_RIGHT: (0.0, -self.angular_speed_rad_s),
            DriveModeAction.FORWARD_LEFT: (self.linear_speed_mps, self.angular_speed_rad_s),
            DriveModeAction.FORWARD_RIGHT: (self.linear_speed_mps, -self.angular_speed_rad_s),
            DriveModeAction.BACKWARD_LEFT: (-self.linear_speed_mps, self.angular_speed_rad_s),
            DriveModeAction.BACKWARD_RIGHT: (-self.linear_speed_mps, -self.angular_speed_rad_s),
        }
        linear, angular = mapping[action]
        return self.controller.drive_ros(linear_x_mps=linear, angular_z_rad_s=angular)

    def _send_wheel(self, action: DriveModeAction) -> str:
        drive = abs(self.linear_speed_mps)
        turn = abs(self.wheel_turn_speed_mps)
        mapping = {
            DriveModeAction.FORWARD: (drive, drive),
            DriveModeAction.BACKWARD: (-drive, -drive),
            DriveModeAction.ROTATE_LEFT: (-turn, turn),
            DriveModeAction.ROTATE_RIGHT: (turn, -turn),
            DriveModeAction.FORWARD_LEFT: (drive - turn, drive + turn),
            DriveModeAction.FORWARD_RIGHT: (drive + turn, drive - turn),
            DriveModeAction.BACKWARD_LEFT: (-drive + turn, -drive - turn),
            DriveModeAction.BACKWARD_RIGHT: (-drive - turn, -drive + turn),
        }
        left, right = mapping[action]
        return self.controller.drive_wheel(left_mps=left, right_mps=right)


def _coerce_action(action: str | DriveModeAction) -> DriveModeAction:
    if isinstance(action, DriveModeAction):
        return action

    normalized = str(action or "").strip().lower()
    for item in DriveModeAction:
        if item.value == normalized:
            return item
    return DriveModeAction.UNKNOWN
