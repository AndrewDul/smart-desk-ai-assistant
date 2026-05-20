from __future__ import annotations

import os
from typing import Any

from modules.devices.mobile_base import (
    DEFAULT_BAUDRATE,
    DEFAULT_TIMEOUT_SEC,
    DryRunSerialTransport,
    MobileBaseController,
    MobileBaseSafetyPolicy,
    PySerialLineTransport,
    choose_serial_port,
)
from modules.runtime.contracts import RuntimeBackendStatus

from .fallbacks import NullMobilityBackend


class RuntimeBuilderMobilityMixin:
    """
    Build the mobility backend with explicit fallback handling.
    """

    def _build_mobility(
        self,
        config: dict[str, object],
    ) -> tuple[Any, RuntimeBackendStatus]:
        if not bool(config.get("enabled", False)):
            return (
                NullMobilityBackend(),
                RuntimeBackendStatus(
                    component="mobility",
                    ok=True,
                    selected_backend="null_mobility",
                    detail="Mobility disabled in config.",
                ),
            )

        try:
            dry_run = bool(config.get("dry_run", False))
            env_port = os.environ.get("NEXA_MOBILE_BASE_SERIAL_PORT", "").strip()
            if dry_run:
                selected_port = str(config.get("port") or "dry-run:auto")
                transport = DryRunSerialTransport()
            else:
                # NEXA_MOBILE_BASE_SERIAL_PORT overrides settings when multiple
                # serial devices exist (e.g. pan-tilt UART + mobile base USB).
                # Without this, choose_serial_port("auto") raises RuntimeError
                # when pyserial enumerates more than one port, silently falling
                # back to NullMobilityBackend and blocking yaw assist entirely.
                raw_port = env_port if env_port else str(config.get("port") or "auto")
                selected_port = choose_serial_port(raw_port)
                transport = PySerialLineTransport(
                    port=selected_port,
                    baudrate=int(config.get("baudrate", DEFAULT_BAUDRATE)),
                    timeout_sec=float(config.get("timeout_seconds", DEFAULT_TIMEOUT_SEC)),
                )

            safety_policy = MobileBaseSafetyPolicy(
                movement_enabled=bool(config.get("movement_enabled", False)),
                require_movement_confirm_env=bool(
                    config.get("require_movement_confirm_env", True)
                ),
                max_linear_speed_mps=float(config.get("max_linear_speed", 0.3)),
                max_angular_speed_rad_s=float(config.get("max_turn_speed", 0.5)),
                default_angular_speed_rad_s=float(config.get("default_turn_speed", 0.18)),
            )

            backend = MobileBaseController(
                transport=transport,
                safety_policy=safety_policy,
                command_profile=str(config.get("command_profile", "ros")),
                stop_repeat=int(config.get("stop_repeat", 1)),
                stop_interval_sec=float(config.get("stop_interval_seconds", 0.0)),
                wheel_turn_speed_mps=float(config.get("wheel_turn_speed_mps", 0.12)),
            )
            return (
                backend,
                RuntimeBackendStatus(
                    component="mobility",
                    ok=True,
                    selected_backend="mobile_base_controller",
                    detail="Mobility backend loaded successfully.",
                    metadata={
                        "dry_run": dry_run,
                        "selected_port": selected_port,
                        "env_port_override": env_port if env_port else None,
                        "command_profile": str(config.get("command_profile", "ros")),
                        "movement_enabled": bool(config.get("movement_enabled", False)),
                    },
                ),
            )
        except Exception as error:
            env_port_used = os.environ.get("NEXA_MOBILE_BASE_SERIAL_PORT", "").strip()
            hint = (
                " Set NEXA_MOBILE_BASE_SERIAL_PORT=/dev/ttyACM0 (or the correct port) "
                "if auto-detection fails due to multiple serial devices."
                if not env_port_used
                else ""
            )
            return (
                NullMobilityBackend(),
                RuntimeBackendStatus(
                    component="mobility",
                    ok=False,
                    selected_backend="null_mobility",
                    detail=f"Mobility backend failed. Using null mobility. Error: {error}{hint}",
                    fallback_used=True,
                ),
            )


__all__ = ["RuntimeBuilderMobilityMixin"]
