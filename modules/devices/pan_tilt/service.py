from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any

from modules.shared.logging.logger import get_logger

from .pca9685 import PCA9685, PCA9685Config

LOGGER = get_logger(__name__)


@dataclass(slots=True)
class ServoAxisConfig:
    channel: int
    min_angle: float
    center_angle: float
    max_angle: float


class PanTiltService:
    """
    High-level pan/tilt service for the ArduCam B0283 platform.

    IMPORTANT:
    This build is configured for the user's current mechanical orientation,
    where the physical axes are effectively crossed:

    - logical LEFT/RIGHT is driven by the tilt servo
    - logical UP/DOWN is driven by the pan servo
    """

    STEP_BY_DIRECTION = {
        "left": ("tilt", 1.0),
        "right": ("tilt", -1.0),
        "up": ("pan", -1.0),
        "down": ("pan", 1.0),
    }

    def __init__(self, config: dict[str, Any]) -> None:
        self._lock = threading.RLock()
        self._enabled = bool(config.get("enabled", False))

        self._step_degrees = float(config.get("step_degrees", 14.0))
        self._move_delay_seconds = max(0.0, float(config.get("move_delay_seconds", 0.0)))
        self._settle_seconds = max(0.0, float(config.get("settle_seconds", 0.02)))

        self._motion_duration_seconds = max(
            0.0,
            float(config.get("motion_duration_seconds", 0.32)),
        )
        self._motion_steps = max(1, int(config.get("motion_steps", 12)))
        self._motion_curve = str(config.get("motion_curve", "ease_in_out")).strip().lower()

        self._min_pulse_us = float(config.get("servo_min_pulse_us", 500.0))
        self._max_pulse_us = float(config.get("servo_max_pulse_us", 2500.0))

        self._pan_inverted = bool(config.get("pan_inverted", False))
        self._tilt_inverted = bool(config.get("tilt_inverted", False))

        self._pan = ServoAxisConfig(
            channel=int(config.get("pan_channel", 0)),
            min_angle=float(config.get("pan_min_angle", 58.0)),
            center_angle=float(config.get("pan_center_angle", 90.0)),
            max_angle=float(config.get("pan_max_angle", 118.0)),
        )
        self._tilt = ServoAxisConfig(
            channel=int(config.get("tilt_channel", 1)),
            min_angle=float(config.get("tilt_min_angle", 40.0)),
            center_angle=float(config.get("tilt_center_angle", 90.0)),
            max_angle=float(config.get("tilt_max_angle", 140.0)),
        )

        if not self._enabled:
            raise ValueError("PanTiltService requires enabled=true in config.")

        self._driver = PCA9685(
            PCA9685Config(
                i2c_bus=int(config.get("i2c_bus", 1)),
                i2c_address=int(config.get("i2c_address", 0x40)),
                pwm_frequency_hz=float(config.get("pwm_frequency_hz", 50.0)),
            )
        )

        self._angles = {
            "pan": self._pan.center_angle,
            "tilt": self._tilt.center_angle,
        }

        self.center()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "pan_angle": round(self._angles["pan"], 2),
                "tilt_angle": round(self._angles["tilt"], 2),
                "step_degrees": self._step_degrees,
                "pan_inverted": self._pan_inverted,
                "tilt_inverted": self._tilt_inverted,
                "motion_duration_seconds": self._motion_duration_seconds,
                "motion_steps": self._motion_steps,
                "motion_curve": self._motion_curve,
            }

    def center(self) -> dict[str, Any]:
        with self._lock:
            self._animate_axis_to("pan", self._pan.center_angle)
            self._animate_axis_to("tilt", self._tilt.center_angle)
            return self.status()

    def move_direction(self, direction: str) -> dict[str, Any]:
        normalized = str(direction or "").strip().lower()
        if normalized not in self.STEP_BY_DIRECTION:
            return {
                "ok": False,
                "error": f"Unsupported direction: {direction}",
            }

        axis_name, direction_multiplier = self.STEP_BY_DIRECTION[normalized]
        direction_multiplier = self._apply_axis_inversion(axis_name, direction_multiplier)

        with self._lock:
            current_angle = self._angles[axis_name]
            target_angle = current_angle + (self._step_degrees * direction_multiplier)
            applied_angle = self._animate_axis_to(axis_name, target_angle)

            if self._settle_seconds > 0.0:
                time.sleep(self._settle_seconds)

            result = self.status()
            result.update(
                {
                    "direction": normalized,
                    "axis": axis_name,
                    "applied_angle": round(applied_angle, 2),
                }
            )
            return result

    def _apply_axis_inversion(self, axis_name: str, direction_multiplier: float) -> float:
        if axis_name == "pan" and self._pan_inverted:
            return direction_multiplier * -1.0
        if axis_name == "tilt" and self._tilt_inverted:
            return direction_multiplier * -1.0
        return direction_multiplier

    def _animate_axis_to(self, axis_name: str, target_angle: float) -> float:
        axis = self._axis(axis_name)
        start_angle = float(self._angles[axis_name])
        final_angle = max(axis.min_angle, min(axis.max_angle, float(target_angle)))

        if self._motion_duration_seconds <= 0.0 or self._motion_steps <= 1:
            return self._set_axis_angle(axis_name, final_angle)

        step_sleep = self._motion_duration_seconds / self._motion_steps

        for step_index in range(1, self._motion_steps + 1):
            progress = step_index / self._motion_steps
            eased_progress = self._apply_curve(progress)
            intermediate = start_angle + ((final_angle - start_angle) * eased_progress)
            self._set_axis_angle(axis_name, intermediate)
            if step_sleep > 0.0:
                time.sleep(step_sleep)

        return final_angle

    def _apply_curve(self, progress: float) -> float:
        progress = max(0.0, min(1.0, float(progress)))

        if self._motion_curve == "linear":
            return progress

        if self._motion_curve == "ease_in_out_cubic":
            if progress < 0.5:
                return 4.0 * progress * progress * progress
            return 1.0 - pow(-2.0 * progress + 2.0, 3.0) / 2.0

        # Default: smooth and natural
        return -(math.cos(math.pi * progress) - 1.0) / 2.0

    def _set_axis_angle(self, axis_name: str, target_angle: float) -> float:
        axis = self._axis(axis_name)
        clamped = max(axis.min_angle, min(axis.max_angle, float(target_angle)))
        pulse_us = self._pulse_for_axis(axis, clamped)
        self._driver.set_servo_pulse_us(axis.channel, pulse_us)
        self._angles[axis_name] = clamped

        if self._move_delay_seconds > 0.0:
            time.sleep(self._move_delay_seconds)

        LOGGER.info(
            "PanTilt move: axis=%s channel=%s angle=%.2f pulse_us=%.2f",
            axis_name,
            axis.channel,
            clamped,
            pulse_us,
        )
        return clamped

    def _pulse_for_axis(self, axis: ServoAxisConfig, angle: float) -> float:
        span = axis.max_angle - axis.min_angle
        if span <= 0.0:
            raise ValueError("Servo axis max_angle must be greater than min_angle.")

        ratio = (float(angle) - axis.min_angle) / span
        ratio = max(0.0, min(1.0, ratio))
        return self._min_pulse_us + ((self._max_pulse_us - self._min_pulse_us) * ratio)

    def _axis(self, axis_name: str) -> ServoAxisConfig:
        if axis_name == "pan":
            return self._pan
        if axis_name == "tilt":
            return self._tilt
        raise ValueError(f"Unsupported axis: {axis_name}")

    def close(self) -> None:
        self._driver.close()