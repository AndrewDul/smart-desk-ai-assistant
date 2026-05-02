from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from modules.shared.logging.logger import get_logger


LOGGER = get_logger(__name__)


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
    max_step_degrees: float
    safe_limits: PanTiltSafeLimits

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
            max_step_degrees=max(0.1, float(config.get("max_step_degrees", 2.0))),
            safe_limits=safe_limits,
        )


class PanTiltBackend(Protocol):
    name: str

    def status(self) -> dict[str, Any]:
        ...

    def center(self) -> dict[str, Any]:
        ...

    def move_direction(self, direction: str) -> dict[str, Any]:
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

    def close(self) -> None:
        return None


class WaveshareSerialPanTiltBackend:
    name = "waveshare_serial"

    def __init__(self, runtime_config: PanTiltRuntimeConfig) -> None:
        self._config = runtime_config

    def status(self) -> dict[str, Any]:
        device_exists = bool(self._config.device) and Path(self._config.device).exists()
        status = _base_status(
            config=self._config,
            backend=self.name,
            ok=True,
            movement_available=False,
            detail=(
                "Waveshare serial backend is in status-only mode. "
                "No serial writes or movement commands are sent."
            ),
        )
        status.update(
            {
                "device_exists": device_exists,
                "serial_opened": False,
                "serial_write_enabled": False,
            }
        )
        return status

    def center(self) -> dict[str, Any]:
        return _blocked_result(
            self._config,
            self.name,
            "Waveshare serial movement is blocked until calibration enables motion.",
        )

    def move_direction(self, direction: str) -> dict[str, Any]:
        result = _blocked_result(
            self._config,
            self.name,
            "Waveshare serial movement is blocked until calibration enables motion.",
        )
        result["direction"] = str(direction or "").strip().lower()
        return result

    def close(self) -> None:
        return None


class PanTiltService:
    """
    Safe pan/tilt service for NEXA.

    This service intentionally avoids startup motion. The legacy PCA9685 path was removed
    from the active runtime because the current target hardware is the Waveshare serial
    bus-servo pan/tilt platform, not the older ArduCam/PCA9685 PWM platform.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        self._runtime_config = PanTiltRuntimeConfig.from_config(config)
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

    def close(self) -> None:
        self._backend.close()

    def _build_backend(self, runtime_config: PanTiltRuntimeConfig) -> PanTiltBackend:
        if runtime_config.backend == "mock":
            return MockPanTiltBackend(runtime_config)
        if runtime_config.backend == "waveshare_serial":
            return WaveshareSerialPanTiltBackend(runtime_config)
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
        "startup_policy": "no_motion",
        "calibration_required": config.calibration_required,
        "allow_uncalibrated_motion": config.allow_uncalibrated_motion,
        "max_step_degrees": config.max_step_degrees,
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


__all__ = ["PanTiltService", "PanTiltRuntimeConfig", "PanTiltSafeLimits"]
