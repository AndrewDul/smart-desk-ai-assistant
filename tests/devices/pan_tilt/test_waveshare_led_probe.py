from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path("scripts/waveshare_pan_tilt_led_probe.py")


def load_probe_module():
    spec = importlib.util.spec_from_file_location("waveshare_pan_tilt_led_probe", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_led_command_is_12v_switch_command_only() -> None:
    module = load_probe_module()

    command = module.build_led_command(80, io4=True, io5=True)

    assert command == {"T": 132, "IO4": 80, "IO5": 80}
    module.assert_no_motion_command(command)


def test_led_command_clamps_brightness() -> None:
    module = load_probe_module()

    high = module.build_led_command(999, io4=True, io5=False)
    low = module.build_led_command(-10, io4=False, io5=True)

    assert high == {"T": 132, "IO4": 255}
    assert low == {"T": 132, "IO5": 0}


def test_motion_command_guard_blocks_gimbal_commands() -> None:
    module = load_probe_module()

    for command_type in (133, 134, 135, 137, 141):
        try:
            module.assert_no_motion_command({"T": command_type})
        except RuntimeError as error:
            assert f"T={command_type}" in str(error)
        else:
            raise AssertionError(f"Expected movement command T={command_type} to be blocked")


def test_encode_command_adds_newline() -> None:
    module = load_probe_module()

    encoded = module.encode_command({"T": 132, "IO4": 1, "IO5": 0})

    assert encoded == b'{"T":132,"IO4":1,"IO5":0}\n'
