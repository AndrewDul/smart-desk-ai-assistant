from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path("scripts/waveshare_pan_tilt_servo_calibration.py")


def load_module():
    spec = importlib.util.spec_from_file_location(
        "waveshare_pan_tilt_servo_calibration",
        SCRIPT_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_set_pan_id_command_is_official_persistent_id_write() -> None:
    module = load_module()
    assert module.build_commands("set_pan_id_2") == [{"T": 501, "raw": 1, "new": 2}]


def test_save_middle_both_uses_tilt_id_1_and_pan_id_2() -> None:
    module = load_module()
    assert module.build_commands("save_middle_both") == [
        {"T": 502, "id": 1},
        {"T": 502, "id": 2},
    ]


def test_calibration_actions_never_include_motion_commands() -> None:
    module = load_module()
    for action in [
        "set_pan_id_2",
        "unlock_torque",
        "lock_torque",
        "save_middle_tilt",
        "save_middle_pan",
        "save_middle_both",
    ]:
        commands = module.build_commands(action)
        assert all(command["T"] not in {133, 134, 141} for command in commands)


def test_set_pan_id_requires_single_servo_and_persistent_confirmations() -> None:
    module = load_module()
    assert module.required_confirmations("set_pan_id_2") == [
        "confirm_12v_power_on",
        "confirm_single_pan_servo_connected",
        "confirm_persistent_servo_write",
    ]


def test_middle_write_requires_manual_center_confirmation() -> None:
    module = load_module()
    assert module.required_confirmations("save_middle_both") == [
        "confirm_12v_power_on",
        "confirm_manually_centered",
        "confirm_persistent_servo_write",
    ]
