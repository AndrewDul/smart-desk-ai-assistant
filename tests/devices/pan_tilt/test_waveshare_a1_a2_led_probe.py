from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path("scripts/waveshare_a1_a2_led_probe.py")


def load_probe_module():
    spec = importlib.util.spec_from_file_location("waveshare_a1_a2_led_probe", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_motor_pwm_command_left() -> None:
    module = load_probe_module()

    command = module.build_motor_pwm_command(channel="L", pwm=35)

    assert command == {"T": 11, "L": 35, "R": 0}


def test_build_motor_pwm_command_right() -> None:
    module = load_probe_module()

    command = module.build_motor_pwm_command(channel="R", pwm=-35)

    assert command == {"T": 11, "L": 0, "R": -35}


def test_pwm_is_clamped() -> None:
    module = load_probe_module()

    high = module.build_motor_pwm_command(channel="L", pwm=999)
    low = module.build_motor_pwm_command(channel="R", pwm=-999)

    assert high == {"T": 11, "L": 255, "R": 0}
    assert low == {"T": 11, "L": 0, "R": -255}


def test_gimbal_commands_are_blocked() -> None:
    module = load_probe_module()

    for command_type in (133, 134, 135, 137, 141):
        try:
            module.assert_not_gimbal_command({"T": command_type})
        except RuntimeError as error:
            assert f"T={command_type}" in str(error)
        else:
            raise AssertionError(f"Expected gimbal command T={command_type} to be blocked")


def test_stop_command() -> None:
    module = load_probe_module()

    assert module.build_stop_command() == {"T": 11, "L": 0, "R": 0}
