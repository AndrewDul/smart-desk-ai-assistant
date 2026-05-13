"""Mobile base device package with compatibility-safe exports."""

from __future__ import annotations

from importlib import import_module
from typing import Iterable


def _export(module_name: str, names: Iterable[str]) -> None:
    try:
        module = import_module(module_name)
    except Exception:
        return

    for name in names:
        if hasattr(module, name):
            globals()[name] = getattr(module, name)


_export(
    "modules.devices.mobile_base.commands",
    [
        "DriveCommand",
        "MobileBaseCommand",
        "build_stop_command",
        "build_forward_command",
        "build_backward_command",
        "build_rotate_left_command",
        "build_rotate_right_command",
        "build_wheel_stop_command",
        "build_wheel_forward_command",
        "build_wheel_backward_command",
        "build_wheel_rotate_left_command",
        "build_wheel_rotate_right_command",
        "build_pwm_stop_command",
    ],
)

_export(
    "modules.devices.mobile_base.serial_transport",
    [
        "DEFAULT_BAUDRATE",
        "DEFAULT_TIMEOUT_SEC",
        "InMemoryLineTransport",
        "PySerialLineTransport",
        "SerialPortCandidate",
        "choose_serial_port",
        "detect_serial_ports",
    ],
)

_export(
    "modules.devices.mobile_base.safety",
    [
        "MobileBaseSafetyPolicy",
    ],
)

_export(
    "modules.devices.mobile_base.controller",
    [
        "MobileBaseController",
    ],
)

__all__ = sorted(name for name in globals() if not name.startswith("_"))
