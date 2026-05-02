from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path("scripts/waveshare_pan_tilt_tiny_side_jog.py")


def load_probe_module():
    spec = importlib.util.spec_from_file_location("waveshare_pan_tilt_tiny_side_jog", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_side_jog_command_forces_y_zero() -> None:
    module = load_probe_module()

    command = module.build_side_jog_command(x=-1, speed=60)

    assert command == {"T": 141, "X": -1, "Y": 0, "SPD": 60}


def test_side_jog_speed_is_clamped_to_safe_limit() -> None:
    module = load_probe_module()

    command = module.build_side_jog_command(x=1, speed=999)

    assert command == {"T": 141, "X": 1, "Y": 0, "SPD": 120}


def test_encoder_blocks_vertical_movement() -> None:
    module = load_probe_module()

    try:
        module.encode_command({"T": 141, "X": 0, "Y": 1, "SPD": 60})
    except RuntimeError as error:
        assert "vertical" in str(error).lower()
    else:
        raise AssertionError("Expected vertical movement to be blocked")


def test_encoder_blocks_non_stop_non_ui_commands() -> None:
    module = load_probe_module()

    for command_type in (11, 132, 133, 134, 137):
        try:
            module.encode_command({"T": command_type})
        except RuntimeError as error:
            assert f"T={command_type}" in str(error)
        else:
            raise AssertionError(f"Expected T={command_type} to be blocked")


def test_stop_command_is_allowed() -> None:
    module = load_probe_module()

    assert module.encode_command({"T": 135}) == b'{"T":135}\n'
