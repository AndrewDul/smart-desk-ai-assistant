from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path("scripts/waveshare_pan_tilt_middle_calibration.py")


def load_module():
    spec = importlib.util.spec_from_file_location("waveshare_pan_tilt_middle_calibration", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_safe_commands() -> None:
    module = load_module()

    assert module.build_command("stop") == {"T": 135}
    assert module.build_command("neutral") == {"T": 141, "X": 0, "Y": 0, "SPD": 0}
    assert module.build_command("unlock_torque") == {"T": 210, "cmd": 0}
    assert module.build_command("lock_torque") == {"T": 210, "cmd": 1}
    assert module.build_command("set_middle", 1) == {"T": 502, "id": 1}
    assert module.build_command("set_middle", 2) == {"T": 502, "id": 2}


def test_set_middle_rejects_invalid_servo_id() -> None:
    module = load_module()

    for servo_id in (None, 0, 3):
        try:
            module.build_command("set_middle", servo_id)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Expected invalid servo_id={servo_id!r} to be rejected")


def test_encoder_rejects_nonzero_ui_movement() -> None:
    module = load_module()

    for command in (
        {"T": 141, "X": 1, "Y": 0, "SPD": 0},
        {"T": 141, "X": 0, "Y": 1, "SPD": 0},
        {"T": 141, "X": 0, "Y": 0, "SPD": 1},
    ):
        try:
            module.encode_command(command)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"Expected command to be rejected: {command}")


def test_encoder_rejects_absolute_movement_command() -> None:
    module = load_module()

    try:
        module.encode_command({"T": 133, "X": 0, "Y": 0, "SPD": 0, "ACC": 0})
    except RuntimeError as error:
        assert "T=133" in str(error)
    else:
        raise AssertionError("Expected T=133 to be rejected")


def test_encoder_allows_calibration_commands() -> None:
    module = load_module()

    assert module.encode_command({"T": 210, "cmd": 0}) == b'{"T":210,"cmd":0}\n'
    assert module.encode_command({"T": 210, "cmd": 1}) == b'{"T":210,"cmd":1}\n'
    assert module.encode_command({"T": 502, "id": 1}) == b'{"T":502,"id":1}\n'
    assert module.encode_command({"T": 135}) == b'{"T":135}\n'
