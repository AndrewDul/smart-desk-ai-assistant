from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from modules.shared.logging.logger import get_logger

from .waveshare_protocol import compact_json_line


LOGGER = get_logger(__name__)
SerialFactory = Callable[..., Any]


@dataclass(frozen=True, slots=True)
class PanTiltSafeLimits:
    pan_min_degrees: float
    pan_center_degrees: float
    pan_max_degrees: float
    tilt_min_degrees: float
    tilt_center_degrees: float
    tilt_max_degrees: float

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "PanTiltSafeLimits":
        limits = dict(config.get("safe_limits", {}) or {})
        return cls(
            pan_min_degrees=float(limits.get("pan_min_degrees", -15.0)),
            pan_center_degrees=float(limits.get("pan_center_degrees", 0.0)),
            pan_max_degrees=float(limits.get("pan_max_degrees", 15.0)),
            tilt_min_degrees=float(limits.get("tilt_min_degrees", -8.0)),
            tilt_center_degrees=float(limits.get("tilt_center_degrees", 0.0)),
            tilt_max_degrees=float(limits.get("tilt_max_degrees", 8.0)),
        )

    def validate(self) -> None:
        if not self.pan_min_degrees <= self.pan_center_degrees <= self.pan_max_degrees:
            raise ValueError("Pan safe limits must contain the pan center angle.")
        if not self.tilt_min_degrees <= self.tilt_center_degrees <= self.tilt_max_degrees:
            raise ValueError("Tilt safe limits must contain the tilt center angle.")

    def clamp_pan(self, value: float) -> float:
        return max(self.pan_min_degrees, min(self.pan_max_degrees, float(value)))

    def clamp_tilt(self, value: float) -> float:
        return max(self.tilt_min_degrees, min(self.tilt_max_degrees, float(value)))

    def as_dict(self) -> dict[str, float]:
        return {
            "pan_min_degrees": self.pan_min_degrees,
            "pan_center_degrees": self.pan_center_degrees,
            "pan_max_degrees": self.pan_max_degrees,
            "tilt_min_degrees": self.tilt_min_degrees,
            "tilt_center_degrees": self.tilt_center_degrees,
            "tilt_max_degrees": self.tilt_max_degrees,
        }


@dataclass(frozen=True, slots=True)
class PanTiltRuntimeConfig:
    enabled: bool
    backend: str
    hardware_enabled: bool
    motion_enabled: bool
    dry_run: bool
    device: str
    baudrate: int
    timeout_seconds: float
    protocol: str
    startup_policy: str
    calibration_required: bool
    allow_uncalibrated_motion: bool
    calibration_state_path: str
    max_step_degrees: float
    command_speed: int
    command_acceleration: int
    serial_warmup_seconds: float
    read_after_write_seconds: float
    safe_limits: PanTiltSafeLimits
    command_mode: str = "absolute"

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "PanTiltRuntimeConfig":
        safe_limits = PanTiltSafeLimits.from_config(config)
        safe_limits.validate()

        backend = str(config.get("backend", "disabled")).strip().lower()
        if backend in {"pca9685", "pwm", "legacy", "legacy_pca9685"}:
            LOGGER.warning(
                "Legacy PCA9685 pan/tilt backend requested but blocked for Waveshare safety."
            )
            backend = "disabled"

        if not bool(config.get("enabled", False)):
            backend = "disabled"

        return cls(
            enabled=bool(config.get("enabled", False)),
            backend=backend,
            hardware_enabled=bool(config.get("hardware_enabled", False)),
            motion_enabled=bool(config.get("motion_enabled", False)),
            dry_run=bool(config.get("dry_run", True)),
            device=str(config.get("device", "")).strip(),
            baudrate=int(config.get("baudrate", 115200)),
            timeout_seconds=max(0.01, float(config.get("timeout_seconds", 0.2))),
            protocol=str(config.get("protocol", "waveshare_json_serial")).strip(),
            startup_policy=str(config.get("startup_policy", "no_motion")).strip().lower(),
            calibration_required=bool(config.get("calibration_required", True)),
            allow_uncalibrated_motion=bool(config.get("allow_uncalibrated_motion", False)),
            calibration_state_path=str(
                config.get("calibration_state_path", "var/data/pan_tilt_limit_calibration.json")
            ).strip(),
            max_step_degrees=max(0.1, float(config.get("max_step_degrees", 2.0))),
            command_speed=max(1, int(config.get("command_speed", 45))),
            command_acceleration=max(1, int(config.get("command_acceleration", 45))),
            serial_warmup_seconds=max(
                0.0,
                float(config.get("serial_warmup_seconds", 0.05)),
            ),
            read_after_write_seconds=max(
                0.0,
                float(config.get("read_after_write_seconds", 0.0)),
            ),
            safe_limits=safe_limits,
            command_mode=str(config.get("command_mode", "absolute")).strip().lower(),
        )


class PanTiltBackend(Protocol):
    name: str

    def status(self) -> dict[str, Any]:
        ...

    def center(self) -> dict[str, Any]:
        ...

    def move_direction(self, direction: str) -> dict[str, Any]:
        ...

    def move_delta(self, *, pan_delta_degrees: float, tilt_delta_degrees: float) -> dict[str, Any]:
        ...

    def close(self) -> None:
        ...


class DisabledPanTiltBackend:
    name = "disabled"

    def __init__(self, runtime_config: PanTiltRuntimeConfig) -> None:
        self._config = runtime_config

    def status(self) -> dict[str, Any]:
        return _base_status(
            config=self._config,
            backend=self.name,
            ok=True,
            movement_available=False,
            detail="Pan/tilt is disabled. No hardware commands will be sent.",
        )

    def center(self) -> dict[str, Any]:
        return _blocked_result(self._config, self.name, "Pan/tilt is disabled.")

    def move_direction(self, direction: str) -> dict[str, Any]:
        result = _blocked_result(self._config, self.name, "Pan/tilt is disabled.")
        result["direction"] = str(direction or "").strip().lower()
        return result

    def move_delta(self, *, pan_delta_degrees: float, tilt_delta_degrees: float) -> dict[str, Any]:
        result = _blocked_result(self._config, self.name, "Pan/tilt is disabled.")
        result.update(
            {
                "requested_pan_delta_degrees": round(float(pan_delta_degrees), 4),
                "requested_tilt_delta_degrees": round(float(tilt_delta_degrees), 4),
                "movement_executed": False,
            }
        )
        return result

    def close(self) -> None:
        return None


class MockPanTiltBackend:
    name = "mock"

    _DIRECTION_STEP = {
        "left": ("pan", -1.0),
        "right": ("pan", 1.0),
        "up": ("tilt", 1.0),
        "down": ("tilt", -1.0),
    }

    def __init__(self, runtime_config: PanTiltRuntimeConfig) -> None:
        self._config = runtime_config
        self._pan_angle = runtime_config.safe_limits.pan_center_degrees
        self._tilt_angle = runtime_config.safe_limits.tilt_center_degrees

    def status(self) -> dict[str, Any]:
        status = _base_status(
            config=self._config,
            backend=self.name,
            ok=True,
            movement_available=self._config.motion_enabled,
            detail="Mock pan/tilt backend is active. No hardware commands will be sent.",
        )
        status.update(
            {
                "pan_angle": round(self._pan_angle, 3),
                "tilt_angle": round(self._tilt_angle, 3),
                "serial_opened": False,
                "serial_write_enabled": False,
            }
        )
        return status

    def center(self) -> dict[str, Any]:
        if not self._config.motion_enabled:
            return _blocked_result(self._config, self.name, "Mock motion is disabled.")

        self._pan_angle = self._config.safe_limits.pan_center_degrees
        self._tilt_angle = self._config.safe_limits.tilt_center_degrees
        result = self.status()
        result["centered"] = True
        return result

    def move_direction(self, direction: str) -> dict[str, Any]:
        normalized = str(direction or "").strip().lower()
        if normalized not in self._DIRECTION_STEP:
            return {
                "ok": False,
                "backend": self.name,
                "error": f"Unsupported direction: {direction}",
            }

        if not self._config.motion_enabled:
            result = _blocked_result(self._config, self.name, "Mock motion is disabled.")
            result["direction"] = normalized
            return result

        axis, multiplier = self._DIRECTION_STEP[normalized]
        step = self._config.max_step_degrees * multiplier

        if axis == "pan":
            self._pan_angle = self._config.safe_limits.clamp_pan(self._pan_angle + step)
        else:
            self._tilt_angle = self._config.safe_limits.clamp_tilt(self._tilt_angle + step)

        result = self.status()
        result.update(
            {
                "direction": normalized,
                "axis": axis,
                "applied_angle": round(
                    self._pan_angle if axis == "pan" else self._tilt_angle,
                    3,
                ),
            }
        )
        return result

    def move_delta(self, *, pan_delta_degrees: float, tilt_delta_degrees: float) -> dict[str, Any]:
        if not self._config.motion_enabled:
            return _blocked_result(self._config, self.name, "Mock motion is disabled.")

        requested_pan = float(pan_delta_degrees)
        requested_tilt = float(tilt_delta_degrees)
        applied_pan = _clamp_delta(requested_pan, self._config.max_step_degrees)
        applied_tilt = _clamp_delta(requested_tilt, self._config.max_step_degrees)
        self._pan_angle = self._config.safe_limits.clamp_pan(self._pan_angle + applied_pan)
        self._tilt_angle = self._config.safe_limits.clamp_tilt(self._tilt_angle + applied_tilt)

        result = self.status()
        result.update(
            {
                "ok": True,
                "movement_executed": True,
                "requested_pan_delta_degrees": round(requested_pan, 4),
                "requested_tilt_delta_degrees": round(requested_tilt, 4),
                "applied_pan_delta_degrees": round(applied_pan, 4),
                "applied_tilt_delta_degrees": round(applied_tilt, 4),
                "pan_angle": round(self._pan_angle, 3),
                "tilt_angle": round(self._tilt_angle, 3),
            }
        )
        return result

    def close(self) -> None:
        return None


class WaveshareSerialPanTiltBackend:
    name = "waveshare_serial"

    def __init__(
        self,
        runtime_config: PanTiltRuntimeConfig,
        *,
        serial_factory: SerialFactory | None = None,
    ) -> None:
        self._config = runtime_config
        self._serial_factory = serial_factory
        self._serial_port: Any | None = None
        self._pan_angle = runtime_config.safe_limits.pan_center_degrees
        self._tilt_angle = runtime_config.safe_limits.tilt_center_degrees
        self._serial_write_count = 0
        self._controller_prepared = False
        self._latest_telemetry: dict[str, Any] | None = None
        self._telemetry_updated_at = 0.0
        self._load_initial_position_from_calibration_state()

    def status(self) -> dict[str, Any]:
        device_exists = bool(self._config.device) and Path(self._config.device).exists()
        calibration_status = self._calibration_status()
        serial_write_enabled = self._serial_write_enabled(
            device_exists=device_exists,
            calibration_ready=calibration_status["calibration_ready"],
        )
        status = _base_status(
            config=self._config,
            backend=self.name,
            ok=True,
            movement_available=serial_write_enabled,
            detail=(
                "Waveshare serial backend is hardware-capable but safety-gated."
                if serial_write_enabled
                else "Waveshare serial movement is blocked by runtime safety gates."
            ),
        )
        status.update(
            {
                "device_exists": device_exists,
                "serial_opened": False,
                "serial_write_enabled": serial_write_enabled,
                "serial_write_count": self._serial_write_count,
                "controller_prepared": self._controller_prepared,
                "pan_angle": round(self._pan_angle, 3),
                "tilt_angle": round(self._tilt_angle, 3),
                **self._telemetry_status(),
                **calibration_status,
            }
        )
        return status

    def center(self) -> dict[str, Any]:
        self._maybe_refresh_telemetry_before_motion()
        return self._move_absolute(
            target_pan_degrees=self._config.safe_limits.pan_center_degrees,
            target_tilt_degrees=self._config.safe_limits.tilt_center_degrees,
            reason="center",
        )

    def move_direction(self, direction: str) -> dict[str, Any]:
        result = _blocked_result(
            self._config,
            self.name,
            "Waveshare serial direction movement is blocked; use move_delta with safety gates.",
        )
        result["direction"] = str(direction or "").strip().lower()
        return result

    def move_delta(self, *, pan_delta_degrees: float, tilt_delta_degrees: float) -> dict[str, Any]:
        self._maybe_refresh_telemetry_before_motion()

        requested_pan = float(pan_delta_degrees)
        requested_tilt = float(tilt_delta_degrees)
        applied_pan = _clamp_delta(requested_pan, self._config.max_step_degrees)
        applied_tilt = _clamp_delta(requested_tilt, self._config.max_step_degrees)

        target_pan = self._config.safe_limits.clamp_pan(self._pan_angle + applied_pan)
        target_tilt = self._config.safe_limits.clamp_tilt(self._tilt_angle + applied_tilt)
        effective_pan_delta = target_pan - self._pan_angle
        effective_tilt_delta = target_tilt - self._tilt_angle

        common = {
            "requested_pan_delta_degrees": round(requested_pan, 4),
            "requested_tilt_delta_degrees": round(requested_tilt, 4),
            "applied_pan_delta_degrees": round(effective_pan_delta, 4),
            "applied_tilt_delta_degrees": round(effective_tilt_delta, 4),
            "target_pan_degrees": round(target_pan, 4),
            "target_tilt_degrees": round(target_tilt, 4),
            "movement_executed": False,
        }

        if abs(effective_pan_delta) == 0.0 and abs(effective_tilt_delta) == 0.0:
            result = self.status()
            result.update(common)
            result["detail"] = "No pan/tilt movement required after safe-limit clamping."
            return result

        status = self.status()
        if not bool(status.get("serial_write_enabled", False)):
            message = "Waveshare serial movement is blocked by runtime safety gates."
            result = dict(status)
            result.update(common)
            result.update(
                {
                    "ok": False,
                    "movement_available": False,
                    "movement_executed": False,
                    "detail": message,
                    "error": message,
                    "missing_safety_gates": self._missing_safety_gates(status),
                }
            )
            return result

        command = _waveshare_move_command(
            x=target_pan,
            y=target_tilt,
            speed=self._config.command_speed,
            acceleration=self._config.command_acceleration,
            command_mode=self._config.command_mode,
        )
        commands = _build_waveshare_runtime_sequence(
            target_command=command,
            current_pan_degrees=self._pan_angle,
            current_tilt_degrees=self._tilt_angle,
            speed=self._config.command_speed,
            acceleration=self._config.command_acceleration,
            include_prepare=not self._controller_prepared,
        )

        try:
            self._send_commands(commands)
            self._controller_prepared = True
        except Exception as error:
            result = self.status()
            result.update(common)
            result.update(
                {
                    "ok": False,
                    "movement_executed": False,
                    "error": f"{error.__class__.__name__}: {error}",
                    "detail": "Waveshare serial command failed before state update.",
                }
            )
            return result

        self._pan_angle = target_pan
        self._tilt_angle = target_tilt
        result = self.status()
        result.update(common)
        result.update(
            {
                "ok": True,
                "movement_available": True,
                "movement_executed": True,
                "command_count": len(commands),
                "detail": "Waveshare serial move_delta executed.",
            }
        )
        return result

    def close(self) -> None:
        serial_port = self._serial_port
        self._serial_port = None
        if serial_port is None:
            return None

        close = getattr(serial_port, "close", None)
        if callable(close):
            try:
                close()
            except Exception as error:
                LOGGER.debug("Failed to close Waveshare serial port cleanly: %s", error)
        return None

    def _move_absolute(
        self,
        *,
        target_pan_degrees: float,
        target_tilt_degrees: float,
        reason: str,
    ) -> dict[str, Any]:
        target_pan = self._config.safe_limits.clamp_pan(float(target_pan_degrees))
        target_tilt = self._config.safe_limits.clamp_tilt(float(target_tilt_degrees))

        current_pan = float(self._pan_angle)
        current_tilt = float(self._tilt_angle)

        effective_pan_delta = target_pan - current_pan
        effective_tilt_delta = target_tilt - current_tilt

        common = {
            "absolute_move_reason": reason,
            "requested_target_pan_degrees": round(float(target_pan_degrees), 4),
            "requested_target_tilt_degrees": round(float(target_tilt_degrees), 4),
            "target_pan_degrees": round(target_pan, 4),
            "target_tilt_degrees": round(target_tilt, 4),
            "applied_pan_delta_degrees": round(effective_pan_delta, 4),
            "applied_tilt_delta_degrees": round(effective_tilt_delta, 4),
            "movement_executed": False,
        }

        if abs(effective_pan_delta) < 0.0001 and abs(effective_tilt_delta) < 0.0001:
            result = self.status()
            result.update(common)
            result["detail"] = "No pan/tilt absolute movement required."
            return result

        status = self.status()
        if not bool(status.get("serial_write_enabled", False)):
            message = "Waveshare serial absolute movement is blocked by runtime safety gates."
            result = dict(status)
            result.update(common)
            result.update(
                {
                    "ok": False,
                    "movement_available": False,
                    "movement_executed": False,
                    "detail": message,
                    "error": message,
                    "missing_safety_gates": self._missing_safety_gates(status),
                }
            )
            return result

        command = _waveshare_move_command(
            x=target_pan,
            y=target_tilt,
            speed=self._config.command_speed,
            acceleration=self._config.command_acceleration,
            command_mode=self._config.command_mode,
        )
        commands = _build_waveshare_runtime_sequence(
            target_command=command,
            current_pan_degrees=current_pan,
            current_tilt_degrees=current_tilt,
            speed=self._config.command_speed,
            acceleration=self._config.command_acceleration,
            include_prepare=not self._controller_prepared,
        )

        try:
            self._send_commands(commands)
            self._controller_prepared = True
        except Exception as error:
            result = self.status()
            result.update(common)
            result.update(
                {
                    "ok": False,
                    "movement_executed": False,
                    "error": f"{error.__class__.__name__}: {error}",
                    "detail": "Waveshare serial absolute command failed before state update.",
                }
            )
            return result

        self._pan_angle = target_pan
        self._tilt_angle = target_tilt

        result = self.status()
        result.update(common)
        result.update(
            {
                "ok": True,
                "movement_available": True,
                "movement_executed": True,
                "command_count": len(commands),
                "detail": "Waveshare serial absolute move executed.",
            }
        )
        return result

    def _telemetry_status(self) -> dict[str, Any]:
        if self._latest_telemetry is None:
            return {
                "telemetry_available": False,
                "telemetry_age_seconds": None,
                "latest_telemetry": None,
            }

        return {
            "telemetry_available": True,
            "telemetry_age_seconds": round(max(0.0, time.monotonic() - self._telemetry_updated_at), 3),
            "latest_telemetry": dict(self._latest_telemetry),
        }

    def _maybe_refresh_telemetry_before_motion(self) -> None:
        if self._serial_factory is not None:
            return
        if not self._config.device or not Path(self._config.device).exists():
            return

        now = time.monotonic()
        if self._latest_telemetry is not None and now - self._telemetry_updated_at < 0.75:
            return

        try:
            self._refresh_telemetry_from_serial(read_seconds=0.25)
        except Exception as error:
            LOGGER.debug("Pan/tilt telemetry refresh failed before motion: %s", error)

    def _refresh_telemetry_from_serial(self, *, read_seconds: float) -> None:
        ser = self._get_serial_for_command()

        reset = getattr(ser, "reset_input_buffer", None)
        if callable(reset):
            reset()

        line = compact_json_line({"T": 130})
        ser.write(line.encode("utf-8"))
        flush = getattr(ser, "flush", None)
        if callable(flush):
            flush()

        self._drain_serial(ser, read_seconds=read_seconds)

        if self._serial_factory is not None:
            close = getattr(ser, "close", None)
            if callable(close):
                close()

    def _update_telemetry_from_line(self, raw_line: Any) -> None:
        if raw_line is None:
            return

        if isinstance(raw_line, bytes):
            text = raw_line.decode("utf-8", errors="replace").strip()
        else:
            text = str(raw_line).strip()

        if not text:
            return

        try:
            payload = json.loads(text)
        except Exception:
            return

        if not isinstance(payload, dict):
            return

        if "pan" not in payload and "tilt" not in payload:
            return

        if "pan" in payload:
            self._pan_angle = float(payload["pan"])
        if "tilt" in payload:
            self._tilt_angle = float(payload["tilt"])

        self._latest_telemetry = dict(payload)
        self._telemetry_updated_at = time.monotonic()

    def _load_initial_position_from_calibration_state(self) -> None:
        path = Path(self._config.calibration_state_path)
        if not path.exists():
            return
        try:
            payload = json.loads(path.read_text())
            self._pan_angle = self._config.safe_limits.clamp_pan(
                float(payload.get("x", self._pan_angle))
            )
            self._tilt_angle = self._config.safe_limits.clamp_tilt(
                float(payload.get("y", self._tilt_angle))
            )
        except Exception as error:
            LOGGER.warning("Failed to load pan/tilt calibration state: %s", error)

    def _calibration_status(self) -> dict[str, Any]:
        if not self._config.calibration_required:
            return {
                "calibration_ready": True,
                "calibration_required": False,
                "calibration_state_path": self._config.calibration_state_path,
                "calibration_block_reason": "calibration_not_required",
            }

        if self._config.allow_uncalibrated_motion:
            return {
                "calibration_ready": True,
                "calibration_required": True,
                "calibration_state_path": self._config.calibration_state_path,
                "calibration_block_reason": "uncalibrated_motion_allowed_by_config",
            }

        path = Path(self._config.calibration_state_path)
        if not path.exists():
            return {
                "calibration_ready": False,
                "calibration_required": True,
                "calibration_state_path": self._config.calibration_state_path,
                "calibration_block_reason": "missing_calibration_state",
            }

        try:
            payload = json.loads(path.read_text())
        except Exception as error:
            return {
                "calibration_ready": False,
                "calibration_required": True,
                "calibration_state_path": self._config.calibration_state_path,
                "calibration_block_reason": f"invalid_calibration_state:{error.__class__.__name__}",
            }

        marked = payload.get("marked_limits", {})
        required = {"pan_left_x", "pan_right_x", "tilt_min_y", "tilt_max_y"}
        missing = sorted(required.difference(marked)) if isinstance(marked, dict) else sorted(required)
        return {
            "calibration_ready": not missing,
            "calibration_required": True,
            "calibration_state_path": self._config.calibration_state_path,
            "calibration_block_reason": "" if not missing else "missing_marked_limits",
            "missing_calibration_limits": missing,
        }

    def _serial_write_enabled(self, *, device_exists: bool, calibration_ready: bool) -> bool:
        return bool(
            self._config.enabled
            and self._config.backend == self.name
            and self._config.hardware_enabled
            and self._config.motion_enabled
            and not self._config.dry_run
            and self._config.protocol == "waveshare_json_serial"
            and bool(self._config.device)
            and device_exists
            and calibration_ready
        )

    def _missing_safety_gates(self, status: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        if not self._config.enabled:
            missing.append("pan_tilt.enabled")
        if self._config.backend != self.name:
            missing.append("pan_tilt.backend")
        if not self._config.hardware_enabled:
            missing.append("pan_tilt.hardware_enabled")
        if not self._config.motion_enabled:
            missing.append("pan_tilt.motion_enabled")
        if self._config.dry_run:
            missing.append("pan_tilt.dry_run=false")
        if self._config.protocol != "waveshare_json_serial":
            missing.append("pan_tilt.protocol")
        if not self._config.device:
            missing.append("pan_tilt.device")
        if not bool(status.get("device_exists", False)):
            missing.append("pan_tilt.device_exists")
        if not bool(status.get("calibration_ready", False)):
            missing.append("pan_tilt.calibration_ready")
        return missing

    def _send_commands(self, commands: list[tuple[str, dict[str, Any], float, float]]) -> None:
        ser = self._get_serial_for_command()

        warmup_seconds = self._config.serial_warmup_seconds
        if not self._controller_prepared:
            warmup_seconds = max(warmup_seconds, 0.05)
        else:
            warmup_seconds = max(warmup_seconds, 0.0)

        if warmup_seconds > 0.0:
            time.sleep(warmup_seconds)

        # Do not reset the input buffer for every movement command.
        # Keeping telemetry available helps the backend stay synchronized with hardware.

        for label, command, pause_seconds, read_seconds in commands:
            line = compact_json_line(command)
            ser.write(line.encode("utf-8"))
            flush = getattr(ser, "flush", None)
            if callable(flush):
                flush()
            self._serial_write_count += 1
            self._drain_serial(ser, read_seconds=read_seconds)
            if pause_seconds > 0.0:
                time.sleep(pause_seconds)

        if self._serial_factory is not None:
            close = getattr(ser, "close", None)
            if callable(close):
                close()

    def _get_serial_for_command(self) -> Any:
        if self._serial_factory is not None:
            return self._open_serial()

        if self._serial_port is not None:
            is_open = getattr(self._serial_port, "is_open", True)
            if bool(is_open):
                return self._serial_port

        self._serial_port = self._open_serial()
        return self._serial_port

    def _open_serial(self) -> Any:
        if self._serial_factory is not None:
            return self._serial_factory(
                self._config.device,
                self._config.baudrate,
                timeout=self._config.timeout_seconds,
            )

        try:
            import serial
        except Exception as error:
            raise RuntimeError(f"pyserial is required for Waveshare pan-tilt movement: {error}") from error

        return serial.Serial(
            self._config.device,
            self._config.baudrate,
            timeout=self._config.timeout_seconds,
        )

    def _drain_serial(self, ser: Any, *, read_seconds: float | None = None) -> None:
        duration = self._config.read_after_write_seconds if read_seconds is None else float(read_seconds)
        if duration <= 0.0:
            return
        readline = getattr(ser, "readline", None)
        if not callable(readline):
            return
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            raw_line = readline()
            if raw_line:
                self._update_telemetry_from_line(raw_line)



class PanTiltService:
    """
    Safe pan/tilt service for NEXA.

    This service intentionally avoids startup motion. The legacy PCA9685 path was removed
    from the active runtime because the current target hardware is the Waveshare serial
    bus-servo pan/tilt platform, not the older ArduCam/PCA9685 PWM platform.
    """

    def __init__(self, config: dict[str, Any], *, serial_factory: SerialFactory | None = None) -> None:
        self._runtime_config = PanTiltRuntimeConfig.from_config(config)
        self._serial_factory = serial_factory
        self._backend = self._build_backend(self._runtime_config)

        if self._runtime_config.startup_policy != "no_motion":
            LOGGER.warning(
                "Ignoring pan/tilt startup_policy=%s. Safe runtime forces no_motion.",
                self._runtime_config.startup_policy,
            )

        LOGGER.info(
            "Pan/tilt service initialized safely. backend=%s enabled=%s "
            "hardware_enabled=%s motion_enabled=%s dry_run=%s",
            self._backend.name,
            self._runtime_config.enabled,
            self._runtime_config.hardware_enabled,
            self._runtime_config.motion_enabled,
            self._runtime_config.dry_run,
        )

    @property
    def backend_name(self) -> str:
        return self._backend.name

    def status(self) -> dict[str, Any]:
        return self._backend.status()

    def center(self) -> dict[str, Any]:
        return self._backend.center()

    def move_direction(self, direction: str) -> dict[str, Any]:
        return self._backend.move_direction(direction)

    def move_delta(self, *, pan_delta_degrees: float, tilt_delta_degrees: float) -> dict[str, Any]:
        return self._backend.move_delta(
            pan_delta_degrees=pan_delta_degrees,
            tilt_delta_degrees=tilt_delta_degrees,
        )

    def close(self) -> None:
        self._backend.close()

    def _build_backend(self, runtime_config: PanTiltRuntimeConfig) -> PanTiltBackend:
        if runtime_config.backend == "mock":
            return MockPanTiltBackend(runtime_config)
        if runtime_config.backend == "waveshare_serial":
            return WaveshareSerialPanTiltBackend(
                runtime_config,
                serial_factory=self._serial_factory,
            )
        return DisabledPanTiltBackend(runtime_config)


def _base_status(
    *,
    config: PanTiltRuntimeConfig,
    backend: str,
    ok: bool,
    movement_available: bool,
    detail: str,
) -> dict[str, Any]:
    return {
        "ok": ok,
        "backend": backend,
        "enabled": config.enabled,
        "hardware_enabled": config.hardware_enabled,
        "motion_enabled": config.motion_enabled,
        "dry_run": config.dry_run,
        "movement_available": movement_available,
        "device": config.device,
        "baudrate": config.baudrate,
        "timeout_seconds": config.timeout_seconds,
        "protocol": config.protocol,
        "command_mode": config.command_mode,
        "startup_policy": "no_motion",
        "calibration_required": config.calibration_required,
        "allow_uncalibrated_motion": config.allow_uncalibrated_motion,
        "calibration_state_path": config.calibration_state_path,
        "max_step_degrees": config.max_step_degrees,
        "command_speed": config.command_speed,
        "command_acceleration": config.command_acceleration,
        "serial_warmup_seconds": config.serial_warmup_seconds,
        "read_after_write_seconds": config.read_after_write_seconds,
        "safe_limits": config.safe_limits.as_dict(),
        "detail": detail,
    }


def _blocked_result(
    config: PanTiltRuntimeConfig,
    backend: str,
    message: str,
) -> dict[str, Any]:
    result = _base_status(
        config=config,
        backend=backend,
        ok=False,
        movement_available=False,
        detail=message,
    )
    result["error"] = message
    return result


def _clamp_delta(value: float, max_abs_value: float) -> float:
    limit = abs(float(max_abs_value))
    return max(-limit, min(limit, float(value)))


def _wire_axis_value(value: float) -> int | float:
    rounded = round(float(value), 3)
    if rounded.is_integer():
        return int(rounded)
    return rounded


def _waveshare_move_command(
    *,
    x: float,
    y: float,
    speed: int,
    acceleration: int,
    command_mode: str = "absolute",
) -> dict[str, Any]:
    mode = str(command_mode or "").strip().lower()
    wire_x = _wire_axis_value(x)
    wire_y = _wire_axis_value(y)

    if mode in {"gimbal_move", "smooth", "smooth_gimbal", "t134"}:
        command_speed = max(1, int(speed))
        return {
            "T": 134,
            "X": wire_x,
            "Y": wire_y,
            "SX": command_speed,
            "SY": command_speed,
        }

    return {
        "T": 133,
        "X": wire_x,
        "Y": wire_y,
        "SPD": int(speed),
        "ACC": int(acceleration),
    }


def _build_waveshare_runtime_sequence(
    *,
    target_command: dict[str, Any],
    current_pan_degrees: float,
    current_tilt_degrees: float,
    speed: int,
    acceleration: int,
    include_prepare: bool,
) -> list[tuple[str, dict[str, Any], float, float]]:
    sequence: list[tuple[str, dict[str, Any], float, float]] = []

    if include_prepare:
        sequence.extend(
            [
                ("stop", {"T": 135}, 0.05, 0.0),
                ("steady off", {"T": 137, "s": 0, "y": 0}, 0.05, 0.0),
                ("pan-tilt mode", {"T": 4, "cmd": 2}, 0.08, 0.0),
                ("torque on", {"T": 210, "cmd": 1}, 0.12, 0.0),
            ]
        )

    sequence.append(("target", target_command, 0.0, 0.08))
    return sequence


__all__ = ["PanTiltService", "PanTiltRuntimeConfig", "PanTiltSafeLimits"]
