from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from modules.devices.mobile_base.controller import MobileBaseController
from modules.devices.mobile_base.safety import MobileBaseSafetyError
from modules.runtime.drive_mode.keyboard_mapping import action_from_active_keys, action_from_key_event
@dataclass(frozen=True, slots=True)
class DriveModeStatus:
    ok: bool; action: str; event: str; command: dict[str, int | float] | None = None; stopped: bool = False; exit_requested: bool = False; deadman_stop: bool = False; error: str | None = None
    def as_dict(self) -> dict[str, Any]: return {"ok":self.ok,"action":self.action,"event":self.event,"command":self.command,"stopped":self.stopped,"exit_requested":self.exit_requested,"deadman_stop":self.deadman_stop,"error":self.error}
class DriveModeService:
    def __init__(self, *, controller: MobileBaseController, linear_speed_mps: float = 0.18, angular_speed_rad_s: float = 0.65, wheel_turn_speed_mps: float = 0.26, command_profile: str = "wheel", pwm_drive: int = 135, pwm_turn: int = 150) -> None:
        self.controller=controller; self.linear_speed_mps=float(linear_speed_mps); self.angular_speed_rad_s=float(angular_speed_rad_s); self.wheel_turn_speed_mps=float(wheel_turn_speed_mps); self.command_profile=str(command_profile or "wheel").strip().lower(); self.pwm_drive=int(pwm_drive); self.pwm_turn=int(pwm_turn); self.exit_requested=False
    def process_key_event(self, *, key: str, event: str) -> DriveModeStatus:
        action=action_from_key_event(key)
        if str(event).lower()=="up" and action not in {"exit","emergency_stop"}: return self.stop(event="up", action=action)
        return self.process_action(action=action, event=str(event or "down"))
    def process_active_keys(self, *, keys: list[str], event: str="state") -> DriveModeStatus: return self.process_action(action=action_from_active_keys(keys), event=event)
    def process_action(self, *, action: str, event: str="state") -> DriveModeStatus:
        action=str(action or "stop").strip().lower()
        if action in {"","unknown","stop"}: return self.stop(event=event, action=action or "stop")
        if action=="emergency_stop": return self.stop(event=event, action=action)
        if action=="exit": self.exit_requested=True; status=self.stop(event=event, action=action); return DriveModeStatus(True,"exit",event,stopped=True,exit_requested=True,error=status.error)
        try: return DriveModeStatus(True, action, event, command=self._send_motion(action))
        except MobileBaseSafetyError as error: self.controller.stop(repeat=1); return DriveModeStatus(False, action, event, stopped=True, error=str(error))
    def stop(self, *, event: str="state", action: str="stop") -> DriveModeStatus: self.controller.stop(repeat=1); return DriveModeStatus(True, action, event, stopped=True)
    def check_deadman(self):
        if self.controller.check_deadman(): return DriveModeStatus(True,"deadman_stop","deadman",stopped=True,deadman_stop=True)
        return None
    def _send_motion(self, action: str):
        if self.command_profile=="ros": return self._send_ros(action)
        return self._send_wheel(action)
    def _send_ros(self, action: str):
        x,z={"forward":(self.linear_speed_mps,0.0),"backward":(-self.linear_speed_mps,0.0),"rotate_left":(0.0,self.angular_speed_rad_s),"rotate_right":(0.0,-self.angular_speed_rad_s),"forward_left":(self.linear_speed_mps,self.angular_speed_rad_s),"forward_right":(self.linear_speed_mps,-self.angular_speed_rad_s),"backward_left":(-self.linear_speed_mps,-self.angular_speed_rad_s),"backward_right":(-self.linear_speed_mps,self.angular_speed_rad_s)}.get(action,(0.0,0.0)); return self.controller.drive_ros(linear_x_mps=x, angular_z_rad_s=z)
    def _send_wheel(self, action: str):
        drive=self.linear_speed_mps; turn=self.wheel_turn_speed_mps; soft=min(abs(turn), max(abs(drive)*0.55,0.08)); left,right={"forward":(drive,drive),"backward":(-drive,-drive),"rotate_left":(-turn,turn),"rotate_right":(turn,-turn),"forward_left":(max(0.0,drive-soft),drive),"forward_right":(drive,max(0.0,drive-soft)),"backward_left":(min(0.0,-drive+soft),-drive),"backward_right":(-drive,min(0.0,-drive+soft))}.get(action,(0.0,0.0)); return self.controller.drive_wheel(left_mps=left, right_mps=right)
